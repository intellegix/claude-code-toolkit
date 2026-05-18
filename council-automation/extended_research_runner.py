"""Extended Research Runner — exhaustive multi-pass artifact verification.

Standalone async orchestrator invoked by the /extended-research slash command.
Spawned with `&` so Claude Code returns immediately; loops 5-40 Perplexity
research_query passes, writes ledger.json + passes.jsonl + report.md to a
per-run workdir, terminates on AND-gate convergence or hard cap.

Design rationale: 5 design passes (2026-05-18) — see
~/.claude/commands/extended-research.md for full architecture.

Key behaviors:
- Forced-JSON output from Perplexity; jsonschema-validated; PARSE-FAILED on miss
- AND-gate convergence: 3 zero-finding + 3 zero-contradiction + all-LOW × 2 + adversarial_count >= ceil(N/2)
- Forced-ADVERSARIAL injection when convergence would fire but adversarial deficit blocks
- POSTMORTEM event-triggered (after all HIGH/MED have >= 1 TARGETED_PROBE), fires once
- FRESH_OBSERVER at pass 8 / 14 / 20, sees frozen Claude-generated 2k-token summary only
- ANALOGOUS findings: effective_severity = min(raw_severity, MEDIUM) for convergence gate
- TARGETED_PROBE upsert: dedup ledger findings on ID; preserve history in findings_history[]
- last_heartbeat_ts written before every pass; stale detection by status command
- Windows-safe atomic ledger writes (same-directory tempfile + os.replace)
- Trailing-prose-tolerant JSON parser (regex extract first, then json.loads)
- submission_lock with 180s timeout (re-uses ~/.claude/council-automation/submission_lock.py)
- SIGINT → INTERRUPTED marker + ledger snapshot; --resume continues from interrupted_at_pass + 1
- SHA-256 artifact hash on Pass 1; --resume compares and warns on drift
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Optional deps loaded lazily so the runner can fail with a clear message
# if requirements.txt wasn't installed.
try:
    import jsonschema  # type: ignore
except ImportError:
    print("[ERROR] jsonschema not installed. Run: pip install -r requirements.txt", file=sys.stderr, flush=True)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
COUNCIL_AUTOMATION_DIR = Path(__file__).parent
COUNCIL_QUERY_SCRIPT = COUNCIL_AUTOMATION_DIR / "council_query.py"

ARTIFACT_TEXT_TOKEN_CAP = 8000          # max tokens for {{ARTIFACT_TEXT}} injection
FRESH_OBSERVER_SUMMARY_CAP = 2000       # Claude-generated summary cap
FRESH_OBSERVER_TOTAL_CAP = 4000         # summary + finding titles list combined
FRESH_OBSERVER_SCHEDULE = (8, 14, 20)   # pass numbers (and every 6 after)
RESEARCH_QUERY_TIMEOUT_S = 360          # per-pass wall timeout
SUBMISSION_LOCK_TIMEOUT_S = 180         # raised from 30s per Pass 4 review
HEARTBEAT_STALE_THRESHOLD_S = 300       # 5 min; status command flags stale
STRUCTURAL_UNRESOLVABLE_THRESHOLD = 3   # HIGH findings persisting >= 3 passes get this tag

# Convergence AND-gate thresholds
CONVERGENCE_ZERO_FINDING_PASSES = 3
CONVERGENCE_ZERO_CONTRADICTION_PASSES = 3
CONVERGENCE_ALL_LOW_PASSES = 2


# ---------------------------------------------------------------------------
# JSON Schema for forced-output Perplexity responses
# ---------------------------------------------------------------------------
RESPONSE_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": [
        "pass_type",
        "findings",
        "contradictions",
        "options",
        "verdict_hint",
        "raw_evidence_summary",
    ],
    "properties": {
        "pass_type": {
            "type": "string",
            "enum": [
                "DECOMPOSE", "CRITIQUE", "ADVERSARIAL", "OPTIONS_SWEEP",
                "TARGETED_PROBE", "FRESH_OBSERVER", "POSTMORTEM",
                "INTEGRATION", "FINAL_VERDICT",
            ],
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "severity", "claim", "phase", "source"],
                "properties": {
                    "id": {"type": "string", "pattern": "^F[0-9]{3,4}$"},
                    "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW", "INFO"]},
                    "claim": {"type": "string", "minLength": 5, "maxLength": 1000},
                    "phase": {"type": "string"},
                    "source": {"type": "string"},
                    "source_flag": {
                        "type": "string",
                        "enum": ["PRIMARY", "SECONDARY", "ANALOGOUS", "INFERRED"],
                    },
                    "prior_finding_id": {"type": "string"},
                },
                "additionalProperties": True,
            },
        },
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "options": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["option_id", "label", "pros", "cons"],
                "properties": {
                    "option_id": {"type": "string"},
                    "label": {"type": "string"},
                    "pros": {"type": "array", "items": {"type": "string"}},
                    "cons": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "additionalProperties": True,
            },
        },
        "verdict_hint": {"type": "string"},
        "raw_evidence_summary": {"type": "string", "minLength": 10},
        "domain_postmortem_note": {"type": "string"},
        "fresh_observer_re_raises": {"type": "array", "items": {"type": "string"}},
        "phases": {  # DECOMPOSE only — required for phase-scoped artifact injection
            "type": "array",
            "items": {
                "type": "object",
                "required": ["label"],
                "properties": {
                    "label": {"type": "string"},
                    "line_start": {"type": "integer", "minimum": 1},
                    "line_end": {"type": "integer", "minimum": 1},
                },
                "additionalProperties": True,
            },
        },
    },
    "additionalProperties": True,
}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def log(msg: str, level: str = "INFO") -> None:
    """Append timestamped line to stdout (which the launcher redirects to runner.log)."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [{level}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Ledger (atomic write, Windows-safe)
# ---------------------------------------------------------------------------
def write_ledger_atomic(ledger: dict, workdir: Path) -> None:
    """Write ledger.json atomically using a same-directory tempfile.

    os.replace requires same-filesystem move on Windows; using
    tempfile.NamedTemporaryFile with dir=workdir keeps src/dst on the
    same filesystem (the workdir's drive). Falls back to shutil.move if
    os.replace fails for any reason (e.g., antivirus locking the tmp).
    """
    final_path = workdir / "ledger.json"
    tmp = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(workdir),
        prefix=".ledger_",
        suffix=".tmp",
        delete=False,
    )
    try:
        json.dump(ledger, tmp, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        try:
            os.replace(tmp.name, final_path)
        except OSError:
            shutil.move(tmp.name, final_path)
    except OSError as e:
        # Disk full or permission — emergency fallback to /tmp
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except OSError:
            pass
        emergency = Path(tempfile.gettempdir()) / f"extended-research-emergency-{ledger.get('slug', 'unknown')}-ledger.json"
        with open(emergency, "w", encoding="utf-8") as f:
            json.dump(ledger, f, indent=2)
        log(f"[CRITICAL] Disk write to workdir failed: {e}. Ledger emergency-written to {emergency}", "ERROR")
        sys.exit(13)


def load_ledger(workdir: Path) -> dict:
    return json.loads((workdir / "ledger.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# JSON parsing — trailing-prose tolerant
# ---------------------------------------------------------------------------
def extract_json(text: str) -> dict | None:
    """Extract the first balanced JSON object from text. Tolerates prose
    before/after, code-fence wrapping, and leading whitespace. Returns None
    if no parseable JSON object found.
    """
    if not text or not text.strip():
        return None
    # Try direct parse first (happy path: response is already pure JSON)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip code fences
    stripped = re.sub(r"```(?:json)?\s*", "", text)
    stripped = re.sub(r"```\s*$", "", stripped, flags=re.MULTILINE)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # Find first { ... balanced } in the text
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        return None
    return None


def validate_response(obj: dict | None) -> tuple[bool, str | None]:
    """Validate parsed Perplexity response against schema. Returns (ok, error_str)."""
    if obj is None:
        return False, "no JSON object extracted from response"
    try:
        jsonschema.validate(obj, RESPONSE_SCHEMA)
        return True, None
    except jsonschema.ValidationError as e:
        return False, f"schema validation failed: {e.message} at {list(e.absolute_path)}"


# ---------------------------------------------------------------------------
# Artifact helpers
# ---------------------------------------------------------------------------
def read_artifact(workdir: Path) -> tuple[str, str]:
    """Read artifact.txt (with header), return (full_text_body, sha256_from_header)."""
    raw = (workdir / "artifact.txt").read_text(encoding="utf-8")
    # Header format: HASH:sha256:...\nVERSION:1\n---\n<body>
    m = re.match(r"HASH:sha256:([0-9a-f]{64})\s*\nVERSION:\d+\s*\n---\s*\n(.*)$", raw, re.DOTALL)
    if not m:
        # No header — treat whole file as body, recompute hash
        body = raw
        return body, hashlib.sha256(body.encode("utf-8")).hexdigest()
    return m.group(2), m.group(1)


def truncate_to_token_budget(text: str, token_cap: int) -> str:
    """Approximate token-cap truncation using ~4 chars/token heuristic.

    Not perfect tokenization but adequate for prompt-budget safety. Cuts
    at paragraph boundaries when possible, otherwise at the cap.
    """
    char_cap = token_cap * 4
    if len(text) <= char_cap:
        return text
    cut = text[:char_cap]
    # Prefer cutting at last paragraph break
    last_para = cut.rfind("\n\n")
    if last_para > char_cap * 0.7:
        cut = cut[:last_para]
    return cut + f"\n\n[... TRUNCATED at ~{token_cap} tokens for prompt budget ...]"


def slice_artifact_by_phase(body: str, line_start: int | None, line_end: int | None) -> str:
    """Return the artifact slice for a TARGETED_PROBE on a specific phase.

    If phase line bounds are missing or invalid, falls back to the
    truncated full artifact (won't blow the token budget).
    """
    lines = body.splitlines()
    if line_start and line_end and 1 <= line_start <= line_end <= len(lines):
        slice_lines = lines[line_start - 1:line_end]
        slice_text = "\n".join(slice_lines)
        # Header for clarity in the prompt
        return f"[Phase slice: lines {line_start}-{line_end} of {len(lines)}]\n{slice_text}"
    return truncate_to_token_budget(body, ARTIFACT_TEXT_TOKEN_CAP)


# ---------------------------------------------------------------------------
# Effective severity (ANALOGOUS cap)
# ---------------------------------------------------------------------------
SEVERITY_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}


def effective_severity(finding: dict) -> str:
    """ANALOGOUS-sourced findings cap at MEDIUM for convergence gate purposes.

    Raw severity is preserved on the finding object for human review;
    this function computes the convergence-relevant value.
    """
    raw = finding.get("severity", "INFO")
    source_flag = finding.get("source_flag", "PRIMARY")
    if source_flag == "ANALOGOUS" and SEVERITY_ORDER.get(raw, 0) > SEVERITY_ORDER["MEDIUM"]:
        return "MEDIUM"
    return raw


# ---------------------------------------------------------------------------
# Ledger merge — upsert findings by ID, preserve history
# ---------------------------------------------------------------------------
def upsert_findings(ledger: dict, new_findings: list[dict], pass_num: int) -> int:
    """Merge new findings into ledger.findings, deduplicating by id.

    On collision: the prior finding moves to findings_history[] with a
    `superseded_at_pass` annotation; the new finding takes its slot.
    Returns count of net-new findings (excluding updates of existing IDs).
    """
    existing_by_id = {f["id"]: f for f in ledger.setdefault("findings", [])}
    history = ledger.setdefault("findings_history", [])
    net_new = 0
    for nf in new_findings:
        fid = nf["id"]
        nf.setdefault("first_seen_pass", pass_num)
        nf.setdefault("last_updated_pass", pass_num)
        nf.setdefault("source_flag", "PRIMARY")
        nf.setdefault("status", "OPEN")
        if fid in existing_by_id:
            # Update — move old to history
            prior = existing_by_id[fid]
            prior_snapshot = dict(prior)
            prior_snapshot["superseded_at_pass"] = pass_num
            history.append(prior_snapshot)
            # Preserve first_seen_pass from the original
            nf["first_seen_pass"] = prior.get("first_seen_pass", pass_num)
            existing_by_id[fid] = nf
        else:
            existing_by_id[fid] = nf
            net_new += 1
    # STRUCTURAL-UNRESOLVABLE auto-tag: HIGH findings present >= 3 consecutive passes unresolved
    for f in existing_by_id.values():
        if f.get("severity") == "HIGH" and f.get("status") == "OPEN":
            age = pass_num - f.get("first_seen_pass", pass_num)
            if age >= STRUCTURAL_UNRESOLVABLE_THRESHOLD - 1 and not f.get("structural_unresolvable"):
                f["structural_unresolvable"] = True
    ledger["findings"] = list(existing_by_id.values())
    return net_new


def next_finding_id(ledger: dict) -> str:
    """Return the next F### identifier (sequential, padded)."""
    existing = ledger.get("findings", []) + ledger.get("findings_history", [])
    nums = []
    for f in existing:
        m = re.match(r"^F(\d{3,4})$", f.get("id", ""))
        if m:
            nums.append(int(m.group(1)))
    nxt = max(nums) + 1 if nums else 1
    return f"F{nxt:03d}"


# ---------------------------------------------------------------------------
# research_query invocation — subprocess to council_query.py
# ---------------------------------------------------------------------------
def call_research_query(prompt: str, invocation_id: str) -> tuple[str | None, str | None]:
    """Invoke council_query.py with research mode. Returns (stdout, error_or_None).

    Uses subprocess so the runner is independent of any Perplexity SDK
    state; council_query.py owns the Playwright session.
    """
    if not COUNCIL_QUERY_SCRIPT.exists():
        return None, f"council_query.py not found at {COUNCIL_QUERY_SCRIPT}"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    cmd = [
        sys.executable,
        str(COUNCIL_QUERY_SCRIPT),
        "--mode", "browser",
        "--perplexity-mode", "research",
        "--invocation-id", invocation_id,
        prompt,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=RESEARCH_QUERY_TIMEOUT_S,
            env=env,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            stderr_tail = (result.stderr or "")[-500:]
            return None, f"council_query.py exited {result.returncode}: {stderr_tail}"
        return result.stdout, None
    except subprocess.TimeoutExpired:
        return None, f"council_query.py timed out after {RESEARCH_QUERY_TIMEOUT_S}s"
    except OSError as e:
        return None, f"subprocess error: {e}"


# ---------------------------------------------------------------------------
# Prompt templates — JSON-output constrained
# ---------------------------------------------------------------------------
JSON_SUFFIX_TEMPLATE = """\

---
OUTPUT CONSTRAINTS — STRICT:
You MUST respond with a single valid JSON object conforming to this schema.
No markdown. No prose before or after. The very first character of your response must be `{` and the last must be `}`.

Required top-level fields: pass_type, findings, contradictions, options, verdict_hint, raw_evidence_summary.

Schema essentials:
- pass_type: must be exactly "{pass_type}"
- findings: array of objects, each with:
    id (string matching ^F[0-9]{{3,4}}$, sequential starting at "{next_id}"),
    severity ("HIGH" | "MEDIUM" | "LOW" | "INFO"),
    claim (5-1000 chars),
    phase (string),
    source (string),
    source_flag ("PRIMARY" | "SECONDARY" | "ANALOGOUS" | "INFERRED")
- contradictions: array of strings (one per detected contradiction)
- options: array of objects with option_id, label, pros[], cons[], optional confidence (0.0-1.0)
- verdict_hint: short string summarizing the pass result
- raw_evidence_summary: 50-2000 char narrative of what you found

If no direct domain literature exists, set source_flag="ANALOGOUS" and explain in raw_evidence_summary.
"""


def jsuf(pass_type: str, next_id: str) -> str:
    return JSON_SUFFIX_TEMPLATE.format(pass_type=pass_type, next_id=next_id)


def build_prompt_decompose(artifact_body: str, next_id: str) -> str:
    full = truncate_to_token_budget(artifact_body, ARTIFACT_TEXT_TOKEN_CAP * 2)  # DECOMPOSE gets bigger budget
    return f"""You are a research decomposition engine. Break the following artifact into 2-6 distinct, independently-researchable phases.

ARTIFACT:
{full}

TASK:
1. Identify 2-6 core phases (research domains, sub-systems, or logical sections). Each phase must be specific enough that a targeted research query could verify it independently.
2. For each phase, also output line_start and line_end (1-indexed line numbers in the artifact body above) so the orchestrator can extract just that slice for TARGETED_PROBE passes.
3. For each phase, produce one HIGH-severity finding naming the central unresolved question or empirical gap.
4. Note any immediately-visible internal contradictions in the artifact.

Output the schema's phases[] array with {{label, line_start, line_end}} entries (in addition to findings[]).
Set verdict_hint to "DECOMPOSE_OK" if 2+ phases found.
{jsuf("DECOMPOSE", next_id)}"""


def build_prompt_critique(artifact_body: str, prior_findings: list[dict], next_id: str) -> str:
    full = truncate_to_token_budget(artifact_body, ARTIFACT_TEXT_TOKEN_CAP)
    pf_json = json.dumps([{"id": f["id"], "claim": f["claim"], "phase": f["phase"]} for f in prior_findings], indent=2)
    return f"""You are a rigorous peer reviewer with web-search access.

ARTIFACT:
{full}

PRIOR FINDINGS (from DECOMPOSE):
{pf_json}

TASK:
1. For each prior finding, search literature for supporting AND contradicting evidence.
2. Identify logical gaps, unsupported assumptions, missing citations in the artifact.
3. Severity: HIGH if a gap invalidates a core claim, MEDIUM if it weakens, LOW if tangential.
4. Populate contradictions[] with specific clashes between artifact claims and external evidence.
5. verdict_hint: "NEEDS_ADVERSARIAL"

Do not speculate. Use source_flag="ANALOGOUS" when only loosely-related literature exists.
{jsuf("CRITIQUE", next_id)}"""


def build_prompt_adversarial(artifact_body: str, prior_findings: list[dict], next_id: str) -> str:
    full = truncate_to_token_budget(artifact_body, ARTIFACT_TEXT_TOKEN_CAP)
    pf_json = json.dumps([{"id": f["id"], "claim": f["claim"], "severity": f["severity"]} for f in prior_findings], indent=2)
    return f"""You are a hostile expert trying to invalidate the artifact's conclusions. Build the STRONGEST possible case against it. Not balanced — adversarial.

ARTIFACT:
{full}

ALL PRIOR FINDINGS:
{pf_json}

TASK:
1. Mount the 3 strongest possible attacks against the artifact's core claims. Each attack = one HIGH-severity finding.
2. Provide the specific evidence or logical principle behind each attack.
3. For prior findings unresolved over multiple passes, note structural_unresolvable=true in the finding object.
4. Populate contradictions[] with claims your adversarial evidence directly undermines.
5. Be maximally hostile but evidence-grounded. Do NOT fabricate sources.
6. verdict_hint: "ADVERSARIAL_COMPLETE"

This pass is required for AND-gate convergence (adversarial_count >= ceil(N/2)).
{jsuf("ADVERSARIAL", next_id)}"""


def build_prompt_options_sweep(artifact_body: str, findings: list[dict], next_id: str) -> str:
    full = truncate_to_token_budget(artifact_body, ARTIFACT_TEXT_TOKEN_CAP)
    unresolved = [f for f in findings if f.get("status") == "OPEN" and f.get("severity") in ("HIGH", "MEDIUM")]
    f_json = json.dumps([{"id": f["id"], "claim": f["claim"]} for f in unresolved], indent=2)
    return f"""You are an options analyst. Enumerate distinct solution paths for the artifact's central decisions.

ARTIFACT:
{full}

UNRESOLVED FINDINGS:
{f_json}

TASK:
1. Enumerate 3-6 distinct, meaningfully-different options. No overlap. "Do nothing" is valid if genuinely viable.
2. For each option: option_id, label, pros[] (2-4), cons[] (2-4), confidence (0.0-1.0).
3. ANALOGOUS-sourced options cap at confidence=0.6.
4. Note option-specific HIGH-severity risks in findings[].
5. verdict_hint: "OPTIONS_READY"
{jsuf("OPTIONS_SWEEP", next_id)}"""


def build_prompt_targeted_probe(target_finding: dict, phase_slice: str, next_id: str) -> str:
    tf_json = json.dumps(target_finding, indent=2)
    return f"""You are a precision investigator. ONE finding needs deep verification.

TARGET FINDING:
{tf_json}

ARTIFACT SLICE (the relevant phase only):
{phase_slice}

TASK:
1. Focus entirely on the target finding. Search for 3-5 independent sources confirming or refuting its claim.
2. Produce ONE finding with id="{target_finding['id']}" (same as target — this is an UPDATE).
3. Update severity based on evidence: confirmed by 2+ PRIMARY sources -> stays or lowers; refuted -> severity=LOW with refutation in claim text; evidence genuinely absent -> source_flag="INFERRED", severity=MEDIUM.
4. verdict_hint: "PROBE_RESOLVED" if claim addressed, "NEEDS_ADVERSARIAL" if opens new questions.

One finding. One target. No scope creep.
{jsuf("TARGETED_PROBE", next_id)}"""


def build_prompt_fresh_observer(fresh_summary: str, finding_titles: list[str], next_id: str) -> str:
    titles_str = "\n".join(f"- {t}" for t in finding_titles) if finding_titles else "(none yet)"
    return f"""You are a FRESH reviewer who has NOT seen the prior research conversation. You receive only this summary + the titles of issues already raised.

ARTIFACT SUMMARY (Claude-generated, frozen):
{fresh_summary}

FINDING TITLES ALREADY RAISED (do NOT re-raise these):
{titles_str}

TASK:
1. Read only the summary and titles. Do not reconstruct the prior thread.
2. Identify NET-NEW findings — issues NOT in the titles list.
3. CRITICAL: if you find yourself about to re-raise a listed finding, OMIT it and add its title to fresh_observer_re_raises[].
4. If you find nothing genuinely new, return findings=[] and explain in raw_evidence_summary.
5. verdict_hint: "CONVERGENCE_LIKELY" if nothing new; "NEEDS_TARGETED_PROBE" if novel HIGH found.

Trust your independent read — your value is exactly that you are NOT anchored.
{jsuf("FRESH_OBSERVER", next_id)}"""


def build_prompt_postmortem(domain: str, all_findings: list[dict], next_id: str) -> str:
    unresolved = [f for f in all_findings if f.get("status") == "OPEN" and f.get("severity") in ("HIGH", "MEDIUM")]
    uf_json = json.dumps([{"id": f["id"], "claim": f["claim"]} for f in unresolved], indent=2)
    return f"""You are a domain postmortem analyst.

ARTIFACT DOMAIN: {domain}

UNRESOLVED FINDINGS:
{uf_json}

TASK:
1. Search for documented public postmortems in this exact domain.
2. If found: cite specific papers/reports/case studies. Produce findings tagged with source_flag="PRIMARY" or "SECONDARY".
3. If no direct postmortem literature exists: set verdict_hint="DOMAIN-POSTMORTEM-UNAVAILABLE" and explain in domain_postmortem_note: (a) why direct postmortem is impossible, (b) which analogous domain you substitute, (c) confidence penalty applied. All findings in this case must have source_flag="ANALOGOUS".
4. Identify <=3 systematic research gaps that left HIGH findings unresolved.
5. Do not re-litigate resolved findings.

Postmortem findings are informational. They do not re-open the convergence gate.
{jsuf("POSTMORTEM", next_id)}"""


def build_prompt_integration(artifact_body: str, all_findings: list[dict], all_contradictions: list[str], next_id: str) -> str:
    full = truncate_to_token_budget(artifact_body, ARTIFACT_TEXT_TOKEN_CAP)
    f_json = json.dumps([{"id": f["id"], "claim": f["claim"], "phase": f["phase"], "severity": f["severity"], "status": f.get("status", "OPEN")} for f in all_findings], indent=2)
    c_json = json.dumps(all_contradictions, indent=2)
    return f"""You are a synthesis engine. Integrate all findings into a coherent unified picture.

ALL FINDINGS:
{f_json}

CONTRADICTION LOG:
{c_json}

ARTIFACT:
{full}

TASK:
1. Group all HIGH/MED findings by phase. Per-phase synthesis (2-4 sentences each) in raw_evidence_summary.
2. Produce findings tagged structural_unresolvable=true for any HIGH unresolved across multiple passes.
3. For each contradiction pair, determine which side is better-supported; mark the weaker side LOW.
4. ANALOGOUS findings get lower-confidence weighting; do not treat as equivalent to PRIMARY.
5. Populate options[] if alternatives remain for unresolved items.
6. verdict_hint: "FINAL_VERDICT_READY" if <= 2 HIGH unresolved; else "NEEDS_ADVERSARIAL".

Be conservative — do not over-resolve.
{jsuf("INTEGRATION", next_id)}"""


def build_prompt_final_verdict(all_findings: list[dict], all_options: list[dict], adversarial_count: int, next_id: str) -> str:
    f_json = json.dumps([{"id": f["id"], "claim": f["claim"], "severity": f["severity"], "status": f.get("status", "OPEN"), "structural_unresolvable": f.get("structural_unresolvable", False)} for f in all_findings], indent=2)
    o_json = json.dumps(all_options, indent=2)
    return f"""You are the final adjudicator. You have all evidence. Produce a definitive verdict.

ALL FINDINGS:
{f_json}

OPTIONS ENUMERATED ACROSS RUN:
{o_json}

ADVERSARIAL PASSES COMPLETED: {adversarial_count}

TASK:
1. Per research phase, output a phase-verdict finding: CONFIRMED / REFUTED / INCONCLUSIVE / STRUCTURAL-UNRESOLVABLE.
2. For HIGH findings tagged structural_unresolvable=true, include with claim prefixed "STRUCTURAL-UNRESOLVABLE: ".
3. Populate options[] with the ranked final options (best to worst), including confidence scores. ANALOGOUS-sourced cap at 0.6.
4. raw_evidence_summary must include: total findings reviewed, adversarial_pass_count, convergence basis (which gate condition closed it).
5. verdict_hint: "FINAL_VERDICT_READY".

Terminal pass. No hedging. Name structural unresolvables clearly.
{jsuf("FINAL_VERDICT", next_id)}"""


# ---------------------------------------------------------------------------
# Convergence gate
# ---------------------------------------------------------------------------
def check_convergence(ledger: dict) -> tuple[bool, str, bool]:
    """Returns (converged, reason, adversarial_deficit_blocking).

    adversarial_deficit_blocking is True iff conditions 1-3 are satisfied
    but adversarial_count is short — triggers forced-ADVERSARIAL injection.
    """
    pass_log = ledger.get("pass_log", [])
    if len(pass_log) < CONVERGENCE_ZERO_FINDING_PASSES:
        return False, "too few passes", False

    n_phases = max(1, len(ledger.get("phases", [])))
    required_adversarial = max(1, math.ceil(n_phases / 2))
    adv_count = sum(1 for p in pass_log if p.get("pass_type") == "ADVERSARIAL" and p.get("status") == "COMPLETED")

    # Last K passes' findings_count (net-new)
    recent_finding_counts = [p.get("net_new_findings", 0) for p in pass_log[-CONVERGENCE_ZERO_FINDING_PASSES:]]
    recent_contradiction_counts = [p.get("net_new_contradictions", 0) for p in pass_log[-CONVERGENCE_ZERO_CONTRADICTION_PASSES:]]

    cond_findings = len(recent_finding_counts) >= CONVERGENCE_ZERO_FINDING_PASSES and all(c == 0 for c in recent_finding_counts)
    cond_contradictions = len(recent_contradiction_counts) >= CONVERGENCE_ZERO_CONTRADICTION_PASSES and all(c == 0 for c in recent_contradiction_counts)

    # All open findings have effective_severity == LOW for last 2 passes
    open_findings = [f for f in ledger.get("findings", []) if f.get("status") == "OPEN"]
    all_low = all(effective_severity(f) == "LOW" for f in open_findings)
    # We approximate "for 2 consecutive passes" by requiring all_low NOW (last pass already wrote findings)
    cond_all_low = all_low

    cond_adversarial = adv_count >= required_adversarial

    if cond_findings and cond_contradictions and cond_all_low:
        if cond_adversarial:
            return True, f"AND-gate satisfied (adv={adv_count}/{required_adversarial})", False
        else:
            return False, f"adversarial deficit (have {adv_count}, need {required_adversarial})", True

    return False, f"zero-find streak={sum(1 for c in recent_finding_counts if c==0)}/{CONVERGENCE_ZERO_FINDING_PASSES}, all_low={all_low}, adv={adv_count}/{required_adversarial}", False


# ---------------------------------------------------------------------------
# Pass-type selector
# ---------------------------------------------------------------------------
def select_next_pass_type(ledger: dict, pass_num: int) -> tuple[str, dict | None]:
    """Pick the next pass type. Returns (pass_type, target_finding_or_None).

    Schedule rules:
    - Passes 1-4 fixed: DECOMPOSE / CRITIQUE / ADVERSARIAL / OPTIONS_SWEEP
    - FRESH_OBSERVER at scheduled positions (8, 14, 20, ...)
    - POSTMORTEM event-trigger: once, when all HIGH/MED have >= 1 TARGETED_PROBE
    - INTEGRATION reserved for second-to-last
    - FINAL_VERDICT reserved for last
    - Adversarial deficit at convergence -> forced ADVERSARIAL
    - Default: TARGETED_PROBE on highest-severity open finding never-probed-or-least-probed
    """
    if pass_num == 1:
        return "DECOMPOSE", None
    if pass_num == 2:
        return "CRITIQUE", None
    if pass_num == 3:
        return "ADVERSARIAL", None
    if pass_num == 4:
        return "OPTIONS_SWEEP", None

    # Fresh observer at scheduled positions
    fresh_due = pass_num == 8 or (pass_num > 8 and (pass_num - 8) % 6 == 0)
    if fresh_due and not _has_recent_pass(ledger, "FRESH_OBSERVER", lookback=2):
        return "FRESH_OBSERVER", None

    # Postmortem event-trigger
    if not _ledger_has_pass(ledger, "POSTMORTEM"):
        if _all_high_med_have_targeted_probe(ledger):
            return "POSTMORTEM", None

    # Check convergence — if blocked only by adversarial deficit, force ADVERSARIAL
    converged, reason, adv_deficit = check_convergence(ledger)
    if adv_deficit:
        return "ADVERSARIAL", None

    # Reserved final passes — only assign when we know max_passes
    max_passes = ledger.get("max_passes")
    if max_passes and pass_num == max_passes - 1:
        return "INTEGRATION", None
    if max_passes and pass_num == max_passes:
        return "FINAL_VERDICT", None

    # Default: TARGETED_PROBE on highest-priority open finding
    target = _pick_probe_target(ledger)
    if target is None:
        # Nothing left to probe — go straight to integration
        return "INTEGRATION", None
    return "TARGETED_PROBE", target


def _has_recent_pass(ledger: dict, pass_type: str, lookback: int = 2) -> bool:
    pl = ledger.get("pass_log", [])[-lookback:]
    return any(p.get("pass_type") == pass_type for p in pl)


def _ledger_has_pass(ledger: dict, pass_type: str) -> bool:
    return any(p.get("pass_type") == pass_type and p.get("status") == "COMPLETED" for p in ledger.get("pass_log", []))


def _all_high_med_have_targeted_probe(ledger: dict) -> bool:
    open_hm = [f for f in ledger.get("findings", []) if f.get("status") == "OPEN" and f.get("severity") in ("HIGH", "MEDIUM")]
    if not open_hm:
        return True
    probed_ids = set()
    for p in ledger.get("pass_log", []):
        if p.get("pass_type") == "TARGETED_PROBE":
            probed_ids.add(p.get("target_id"))
    return all(f["id"] in probed_ids for f in open_hm)


def _pick_probe_target(ledger: dict) -> dict | None:
    """Pick the highest-severity OPEN finding with the fewest prior probes."""
    candidates = [f for f in ledger.get("findings", []) if f.get("status") == "OPEN"]
    if not candidates:
        return None
    probe_counts: dict[str, int] = {}
    for p in ledger.get("pass_log", []):
        if p.get("pass_type") == "TARGETED_PROBE":
            tid = p.get("target_id")
            if tid:
                probe_counts[tid] = probe_counts.get(tid, 0) + 1
    severity_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
    candidates.sort(key=lambda f: (severity_rank.get(f.get("severity"), 9), probe_counts.get(f["id"], 0)))
    return candidates[0]


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
class InterruptedException(Exception):
    pass


_interrupted = False


def sigint_handler(signum, frame):
    global _interrupted
    _interrupted = True
    log("SIGINT received — finishing current pass then writing INTERRUPTED marker", "WARN")


def run_pass(ledger: dict, workdir: Path, pass_num: int, pass_type: str, target: dict | None, artifact_body: str, fresh_observer_summary: str) -> dict:
    """Execute one pass: build prompt, call research_query, parse, validate, merge."""
    # Heartbeat first (so status command sees activity)
    ledger["last_heartbeat_ts"] = datetime.now(timezone.utc).isoformat()
    ledger["current_pass_num"] = pass_num
    ledger["current_pass_type"] = pass_type
    write_ledger_atomic(ledger, workdir)

    next_id = next_finding_id(ledger)
    invocation_id = f"er-{ledger['slug'][:8]}-p{pass_num:02d}-{uuid.uuid4().hex[:6]}"

    if pass_type == "DECOMPOSE":
        prompt = build_prompt_decompose(artifact_body, next_id)
    elif pass_type == "CRITIQUE":
        prompt = build_prompt_critique(artifact_body, ledger.get("findings", []), next_id)
    elif pass_type == "ADVERSARIAL":
        prompt = build_prompt_adversarial(artifact_body, ledger.get("findings", []), next_id)
    elif pass_type == "OPTIONS_SWEEP":
        prompt = build_prompt_options_sweep(artifact_body, ledger.get("findings", []), next_id)
    elif pass_type == "TARGETED_PROBE":
        assert target is not None
        # Look up phase line range for the target's phase
        phase_label = target.get("phase", "")
        phase_meta = next((p for p in ledger.get("phases", []) if p.get("label") == phase_label), None)
        line_start = phase_meta.get("line_start") if phase_meta else None
        line_end = phase_meta.get("line_end") if phase_meta else None
        slice_text = slice_artifact_by_phase(artifact_body, line_start, line_end)
        prompt = build_prompt_targeted_probe(target, slice_text, next_id)
    elif pass_type == "FRESH_OBSERVER":
        titles = [f["claim"][:80] for f in ledger.get("findings", [])]
        prompt = build_prompt_fresh_observer(fresh_observer_summary, titles, next_id)
    elif pass_type == "POSTMORTEM":
        domain = ledger.get("domain", "general software engineering")
        prompt = build_prompt_postmortem(domain, ledger.get("findings", []), next_id)
    elif pass_type == "INTEGRATION":
        prompt = build_prompt_integration(artifact_body, ledger.get("findings", []), ledger.get("contradictions", []), next_id)
    elif pass_type == "FINAL_VERDICT":
        adv = sum(1 for p in ledger.get("pass_log", []) if p.get("pass_type") == "ADVERSARIAL" and p.get("status") == "COMPLETED")
        all_opts = []
        for p in ledger.get("pass_log", []):
            for o in p.get("options_emitted", []):
                all_opts.append(o)
        prompt = build_prompt_final_verdict(ledger.get("findings", []), all_opts, adv, next_id)
    else:
        return {"pass_num": pass_num, "pass_type": pass_type, "status": "SKIPPED-UNKNOWN-TYPE", "timestamp": datetime.now(timezone.utc).isoformat()}

    log(f"PASS {pass_num} {pass_type} starting (target={target['id'] if target else 'n/a'})")
    raw, err = call_research_query(prompt, invocation_id)

    pass_record: dict[str, Any] = {
        "pass_num": pass_num,
        "pass_type": pass_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "invocation_id": invocation_id,
        "target_id": target["id"] if target else None,
    }

    if err:
        pass_record["status"] = "SKIPPED-NETWORK"
        pass_record["error"] = err
        log(f"PASS {pass_num} {pass_type} SKIPPED-NETWORK: {err}", "WARN")
        _append_passes_jsonl(workdir, pass_record, raw_response=None)
        return pass_record

    parsed = extract_json(raw or "")
    ok, vmsg = validate_response(parsed)
    if not ok:
        # Retry once with a stricter reminder
        log(f"PASS {pass_num} {pass_type} schema-fail ({vmsg}); retrying once", "WARN")
        retry_prompt = prompt + "\n\nREMINDER: Your previous response failed validation. Return ONLY valid JSON, nothing else."
        raw2, err2 = call_research_query(retry_prompt, invocation_id + "-r")
        if not err2:
            parsed = extract_json(raw2 or "")
            ok, vmsg = validate_response(parsed)
            raw = raw2 if raw2 else raw

    if not ok:
        pass_record["status"] = "PARSE-FAILED"
        pass_record["error"] = vmsg
        log(f"PASS {pass_num} {pass_type} PARSE-FAILED after retry: {vmsg}", "ERROR")
        _append_passes_jsonl(workdir, pass_record, raw_response=raw)
        return pass_record

    # Merge findings, contradictions, options into ledger
    new_findings = parsed.get("findings", [])
    net_new = upsert_findings(ledger, new_findings, pass_num)
    pass_record["net_new_findings"] = net_new

    new_contradictions = parsed.get("contradictions", [])
    existing_contras = set(ledger.get("contradictions", []))
    new_contras = [c for c in new_contradictions if c not in existing_contras]
    ledger.setdefault("contradictions", []).extend(new_contras)
    pass_record["net_new_contradictions"] = len(new_contras)

    opts = parsed.get("options", [])
    if opts:
        ledger.setdefault("options", []).extend(opts)
        pass_record["options_emitted"] = opts

    # Pass-type-specific extras
    if pass_type == "DECOMPOSE":
        phases = parsed.get("phases", [])
        ledger["phases"] = phases
        # Recompute max_passes now that N is known
        n = max(1, len(phases))
        formula = 4 + n + math.ceil(n / 2) + 2
        ledger["pass_formula"] = f"{formula} = 4(bootstrap) + {n}(targets) + ceil({n}/2)(followup) + 2(reserved)"
        # If user passed --max-passes explicitly, keep it. Otherwise, set to formula value.
        if ledger.get("max_passes_user_override") is not True:
            ledger["max_passes"] = max(ledger.get("min_passes", 5), formula)
        log(f"DECOMPOSE found N={n} phases. max_passes = {ledger['max_passes']} ({ledger['pass_formula']})")
        # Domain inference for POSTMORTEM
        ledger["domain"] = parsed.get("raw_evidence_summary", "")[:100]

    pass_record["status"] = "COMPLETED"
    pass_record["verdict_hint"] = parsed.get("verdict_hint", "")

    _append_passes_jsonl(workdir, pass_record, raw_response=raw)
    log(f"PASS {pass_num} {pass_type} COMPLETED net_new_findings={net_new} net_new_contras={len(new_contras)}")
    return pass_record


def _append_passes_jsonl(workdir: Path, pass_record: dict, raw_response: str | None) -> None:
    entry = dict(pass_record)
    entry["raw_response"] = raw_response
    with open(workdir / "passes.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def generate_fresh_observer_summary(artifact_body: str, phases: list[dict]) -> str:
    """Generate a frozen ~2k-token summary from the artifact + phase decomposition.

    This is a static heuristic summary (not a Claude call from inside the
    runner — Claude isn't running here). It includes: artifact head/tail,
    list of phases, total length.
    """
    lines = artifact_body.splitlines()
    head = "\n".join(lines[:30])
    tail = "\n".join(lines[-15:]) if len(lines) > 45 else ""
    phase_list = "\n".join(f"- {p.get('label', '?')} (lines {p.get('line_start', '?')}-{p.get('line_end', '?')})" for p in phases)
    summary = f"""ARTIFACT SUMMARY (frozen post-DECOMPOSE):

Total length: {len(lines)} lines, ~{len(artifact_body)//4} tokens estimated.

Decomposed phases:
{phase_list or '(none extracted by DECOMPOSE)'}

OPENING (first 30 lines):
{head}

{f'CLOSING (last 15 lines):{chr(10)}{tail}' if tail else ''}
"""
    return truncate_to_token_budget(summary, FRESH_OBSERVER_SUMMARY_CAP)


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------
def write_report(ledger: dict, workdir: Path, termination_reason: str) -> None:
    findings = ledger.get("findings", [])
    open_high = [f for f in findings if f.get("status") == "OPEN" and f.get("severity") == "HIGH"]
    structural = [f for f in findings if f.get("structural_unresolvable")]

    if not open_high and not ledger.get("contradictions"):
        verdict = "APPROVED"
    elif open_high and not structural:
        verdict = f"REVISE ({len(open_high)} HIGH findings)"
    elif structural:
        verdict = f"STRUCTURAL-UNRESOLVABLE ({len(structural)} unresolvable)"
    else:
        verdict = "INCONCLUSIVE"

    md = []
    md.append(f"# Extended Research Report: {ledger['slug']}")
    md.append(f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}  ")
    md.append(f"**Passes:** {len(ledger.get('pass_log', []))}/{ledger.get('max_passes', '?')}  ")
    md.append(f"**Verdict:** {verdict}  ")
    md.append(f"**Termination Reason:** {termination_reason}\n")

    md.append("## Executive Summary")
    md.append(f"Artifact verified across {len(ledger.get('pass_log', []))} Perplexity research passes. ")
    md.append(f"{len(findings)} findings ({len(open_high)} HIGH open, {len(structural)} STRUCTURAL-UNRESOLVABLE). ")
    md.append(f"adversarial_pass_count = {sum(1 for p in ledger.get('pass_log', []) if p.get('pass_type') == 'ADVERSARIAL' and p.get('status') == 'COMPLETED')}.\n")

    md.append("## Findings by Phase")
    by_phase: dict[str, list[dict]] = {}
    for f in findings:
        by_phase.setdefault(f.get("phase", "(unspecified)"), []).append(f)
    for phase, items in by_phase.items():
        md.append(f"### Phase: {phase}")
        for f in sorted(items, key=lambda x: SEVERITY_ORDER.get(x.get("severity"), 0), reverse=True):
            tag = " [STRUCTURAL-UNRESOLVABLE]" if f.get("structural_unresolvable") else ""
            src = f" [{f.get('source_flag', 'PRIMARY')}]"
            md.append(f"- **{f['id']} [{f['severity']}]{src}{tag}** — {f['claim']}")
            md.append(f"  - Source: {f.get('source', 'n/a')}")
            md.append(f"  - Status: {f.get('status', 'OPEN')}")
        md.append("")

    if ledger.get("contradictions"):
        md.append("## Contradiction Log")
        for c in ledger["contradictions"]:
            md.append(f"- {c}")
        md.append("")

    if ledger.get("options"):
        md.append("## Options Enumerated")
        for o in ledger["options"]:
            md.append(f"### {o.get('label', o.get('option_id', '?'))}")
            md.append(f"**Confidence:** {o.get('confidence', 'n/a')}")
            md.append(f"**Pros:** {', '.join(o.get('pros', []))}")
            md.append(f"**Cons:** {', '.join(o.get('cons', []))}\n")

    md.append("## Recommended Next Actions")
    if open_high:
        for f in open_high:
            md.append(f"- Address {f['id']} ({f['severity']}): {f['claim'][:120]}")
    else:
        md.append("- No open HIGH findings. Artifact may proceed.")
    md.append("")

    md.append("## Metadata")
    md.append(f"- adversarial_pass_count: {sum(1 for p in ledger.get('pass_log', []) if p.get('pass_type') == 'ADVERSARIAL' and p.get('status') == 'COMPLETED')}")
    md.append(f"- fresh_observer_passes: {[p['pass_num'] for p in ledger.get('pass_log', []) if p.get('pass_type') == 'FRESH_OBSERVER' and p.get('status') == 'COMPLETED']}")
    md.append(f"- last_heartbeat_ts: {ledger.get('last_heartbeat_ts', 'n/a')}")
    md.append(f"- workdir: {workdir}")
    md.append(f"- artifact_hash: {ledger.get('artifact_hash', 'n/a')}")
    md.append(f"- pass_formula: {ledger.get('pass_formula', 'n/a')}")

    (workdir / "report.md").write_text("\n".join(md), encoding="utf-8")
    log(f"Report written to {workdir / 'report.md'}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Extended Research Runner")
    parser.add_argument("--workdir", required=True, help="Per-invocation working directory")
    parser.add_argument("--mode", choices=["whole", "per-phase"], default="per-phase")
    parser.add_argument("--max-passes", type=int, default=None, help="Override dynamic formula")
    parser.add_argument("--min-passes", type=int, default=5, help="Floor for short artifacts")
    parser.add_argument("--resume", action="store_true", help="Resume from existing ledger.json")
    args = parser.parse_args()

    workdir = Path(args.workdir).expanduser().resolve()
    if not workdir.is_dir():
        print(f"[ERROR] workdir {workdir} does not exist", file=sys.stderr)
        return 1

    signal.signal(signal.SIGINT, sigint_handler)
    try:
        signal.signal(signal.SIGTERM, sigint_handler)
    except (AttributeError, OSError):
        pass  # Windows may not support SIGTERM

    # Load or initialize ledger
    if args.resume and (workdir / "ledger.json").exists():
        ledger = load_ledger(workdir)
        log(f"Resuming from pass {ledger.get('interrupted_at_pass', ledger.get('current_pass_num', 0))} (slug={ledger['slug']})")
        # Verify artifact hash hasn't drifted
        _, current_hash = read_artifact(workdir)
        if current_hash != ledger.get("artifact_hash"):
            log(f"WARNING: artifact_hash drift detected. Ledger says {ledger.get('artifact_hash')[:16]}..., current is {current_hash[:16]}...", "WARN")
            ledger["drift_warning"] = True
        start_pass = (ledger.get("interrupted_at_pass") or ledger.get("current_pass_num") or 0) + 1
    else:
        body, ahash = read_artifact(workdir)
        slug = workdir.name
        ledger = {
            "slug": slug,
            "artifact_hash": ahash,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": args.mode,
            "min_passes": args.min_passes,
            "max_passes": args.max_passes,
            "max_passes_user_override": args.max_passes is not None,
            "passes_completed": 0,
            "status": "RUNNING",
            "findings": [],
            "findings_history": [],
            "contradictions": [],
            "options": [],
            "phases": [],
            "pass_log": [],
            "last_heartbeat_ts": datetime.now(timezone.utc).isoformat(),
        }
        write_ledger_atomic(ledger, workdir)
        start_pass = 1

    artifact_body, _ = read_artifact(workdir)

    # Fresh-observer summary — generated after DECOMPOSE (Pass 1) and frozen.
    fresh_summary_path = workdir / "fresh_observer_summary.txt"
    if fresh_summary_path.exists():
        fresh_summary = fresh_summary_path.read_text(encoding="utf-8")
    else:
        fresh_summary = ""  # populated post-Pass-1

    # Main pass loop
    pass_num = start_pass
    termination_reason = None
    while True:
        if _interrupted:
            log("Interrupt acknowledged — writing INTERRUPTED state", "WARN")
            ledger["status"] = "INTERRUPTED"
            ledger["interrupted_at_pass"] = pass_num - 1
            write_ledger_atomic(ledger, workdir)
            (workdir / "INTERRUPTED").write_text(datetime.now(timezone.utc).isoformat())
            termination_reason = f"INTERRUPTED at pass {pass_num - 1}; resume with --resume {ledger['slug']}"
            break

        # Hard cap check (max_passes may be None until DECOMPOSE)
        max_p = ledger.get("max_passes")
        if max_p and pass_num > max_p:
            converged, reason, _ = check_convergence(ledger)
            if converged:
                termination_reason = f"CONVERGED at hard cap; {reason}"
            else:
                open_high = sum(1 for f in ledger.get("findings", []) if f.get("status") == "OPEN" and f.get("severity") == "HIGH")
                contras = len(ledger.get("contradictions", []))
                termination_reason = f"CAP-HIT ({open_high} open HIGH, {contras} contradictions; {reason})"
            break

        # Pre-pass convergence check (don't re-do passes that already passed)
        if pass_num > 5:  # only after bootstrap
            converged, reason, _adv_deficit = check_convergence(ledger)
            if converged and pass_num > ledger.get("min_passes", 5):
                termination_reason = f"CONVERGED — {reason}"
                # Run INTEGRATION + FINAL_VERDICT before terminating
                if not _ledger_has_pass(ledger, "INTEGRATION"):
                    integ = run_pass(ledger, workdir, pass_num, "INTEGRATION", None, artifact_body, fresh_summary)
                    ledger["pass_log"].append(integ)
                    ledger["passes_completed"] = pass_num
                    write_ledger_atomic(ledger, workdir)
                    pass_num += 1
                final = run_pass(ledger, workdir, pass_num, "FINAL_VERDICT", None, artifact_body, fresh_summary)
                ledger["pass_log"].append(final)
                ledger["passes_completed"] = pass_num
                write_ledger_atomic(ledger, workdir)
                break

        # Select and run the next pass
        pass_type, target = select_next_pass_type(ledger, pass_num)
        record = run_pass(ledger, workdir, pass_num, pass_type, target, artifact_body, fresh_summary)
        ledger["pass_log"].append(record)
        ledger["passes_completed"] = pass_num
        write_ledger_atomic(ledger, workdir)

        # Post-DECOMPOSE: generate the frozen fresh-observer summary
        if pass_num == 1 and pass_type == "DECOMPOSE" and not fresh_summary_path.exists():
            fresh_summary = generate_fresh_observer_summary(artifact_body, ledger.get("phases", []))
            fresh_summary_path.write_text(fresh_summary, encoding="utf-8")
            log(f"Fresh-observer summary generated ({len(fresh_summary)} chars) — frozen for run")

        pass_num += 1

    # Cleanup
    if termination_reason is None:
        termination_reason = "ended without explicit convergence (unexpected)"
    ledger["status"] = "COMPLETED" if "INTERRUPTED" not in termination_reason else "INTERRUPTED"
    ledger["termination_reason"] = termination_reason
    write_ledger_atomic(ledger, workdir)
    write_report(ledger, workdir, termination_reason)

    # Sentinel for Claude to detect completion
    (workdir / "runner.log.done").write_text(datetime.now(timezone.utc).isoformat() + "\n")
    log(f"DONE. Termination: {termination_reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
