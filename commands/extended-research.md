# /extended-research — Exhaustive Multi-Pass Artifact Verification via Perplexity

Runs 5–40 iterative `research_query` passes against any artifact (architectural blueprint, implementation plan, debugging trace, refactor proposal, single function) and stops when iterations converge — no new findings, no new contradictions, no new options worth exploring. Produces a definitive verdict + exhaustive list of every gotcha, gap, and flaw, with the most-optimal option chosen per finding.

**Design rationale (5 design passes, 2026-05-18):** Pass 1 draft → Pass 2 adversarial critique (9 bugs) → Pass 3 refined v2 → Pass 4 final critique (8 more bugs) → Pass 5 conditional approval. All 17 bugs integrated. Logs at `~/.claude/council-cache/`.

## Usage

```
/extended-research [--max-passes N] [--mode whole|per-phase] [--resume slug] [--min-passes M]
<artifact text or path>
```

**Flags:**
- `--max-passes N` — hard cap (overrides dynamic formula). Default: `4 + N_phases + ceil(N_phases/2) + 2`, computed after DECOMPOSE.
- `--mode whole|per-phase` — `per-phase` (default) drills each phase separately; `whole` treats artifact as one unit.
- `--resume <slug>` — resume an interrupted run. Compares artifact SHA-256 — warns on drift.
- `--min-passes M` — floor for short artifacts. Default: 5. Forces ≥M passes even if convergence fires earlier.

## What Claude Does When Invoked

### Step 1 — Parse and stage

Claude extracts the artifact (everything after flags) and the flag values. If the artifact looks like a file path (`./blueprint.md` or absolute), Claude `Read`s it. Otherwise treats it as inline text.

```
SLUG = first-8-words-sanitized + sha256(artifact)[:8]
WORKDIR = ~/.claude/extended-research-logs/{SLUG}/
```

If `--resume` is set, Claude reads `{WORKDIR}/ledger.json` and compares stored `artifact_hash` vs current artifact SHA-256. **On hash mismatch:** prints both hashes and asks the user to confirm `--force-resume` (continues with DRIFT-WARNING tag on every finding) or restart fresh.

### Step 2 — Bootstrap dependencies

```bash
pip install -q -r ~/.claude/council-automation/requirements.txt 2>&1 | tail -3
```

Pinned: `jsonschema>=4.0`, `filelock>=3.13` (both pure-Python wheels, no admin needed).

### Step 3 — Write artifact + launch runner async

```bash
mkdir -p $WORKDIR
# Write artifact with SHA-256 + ISO timestamp header
python -c "import hashlib,sys,pathlib;t=pathlib.Path(sys.argv[1]).read_text() if pathlib.Path(sys.argv[1]).exists() else sys.argv[1];h=hashlib.sha256(t.encode()).hexdigest();open(sys.argv[2],'w').write(f'HASH:sha256:{h}\nVERSION:1\n---\n{t}')" "$ARTIFACT" "$WORKDIR/artifact.txt"

# Shell out to runner — DETACHED so Claude returns immediately
nohup python ~/.claude/council-automation/extended_research_runner.py \
  --workdir "$WORKDIR" \
  --mode "$MODE" \
  ${MAX_PASSES:+--max-passes $MAX_PASSES} \
  ${MIN_PASSES:+--min-passes $MIN_PASSES} \
  ${RESUME:+--resume} \
  > "$WORKDIR/runner.log" 2>&1 &
echo $! > "$WORKDIR/runner.pid"
```

On Windows-bash where `nohup` may be absent: use `(python ... > runner.log 2>&1 &)` — the subshell + `&` is equivalent.

### Step 4 — Return control to user immediately

Claude prints (and stops, returning the conversation to the user):

```
Extended research started.
  Slug:    {SLUG}
  Workdir: ~/.claude/extended-research-logs/{SLUG}/
  PID:     {PID}
  Status:  Running DECOMPOSE (pass 1)...

Estimated runtime: 5–40 minutes (depends on phase count + convergence).
This is a background job. Continue using Claude normally.

To check status:
  /extended-research-status {SLUG}                 (Claude reads ledger + last_heartbeat_ts)
  tail -f ~/.claude/extended-research-logs/{SLUG}/runner.log    (live stream from terminal)

When done, the runner writes runner.log.done. Ask Claude "is my research run done?" or wait
for the file to appear, then ask Claude to summarize the report.
```

**Claude does NOT poll for completion proactively** (Claude Code has no background-task mechanism). The user must come back and ask, OR run a status check.

### Step 5 — Status check (when user asks)

When the user asks "status on my research run" or runs `/extended-research-status <slug>`:

```bash
cat ~/.claude/extended-research-logs/{SLUG}/ledger.json | python -m json.tool
ls -la ~/.claude/extended-research-logs/{SLUG}/runner.log.done 2>/dev/null && echo "DONE" || echo "RUNNING"
```

Claude reads:
- `passes_completed`, `max_passes`, `adversarial_pass_count`
- `last_heartbeat_ts` — if `now - heartbeat > 5min`, print `⚠️ STALE — runner may be stuck`
- If `runner.log.done` exists, read `report.md` and summarize

### Step 6 — On completion (passive trigger via user)

When `runner.log.done` exists:

1. Claude reads `report.md` in full.
2. Claude summarizes to the user in chat:
   - **Verdict:** `CONVERGED` / `CAP-HIT(N HIGH open)` / `INTERRUPTED`
   - **Termination Reason:** one sentence
   - **Top 3 findings** (by severity, with `STRUCTURAL-UNRESOLVABLE` tagged if applicable)
   - **Recommended option** (highest-scored, per FINAL_VERDICT)
   - **Full report path:** `~/.claude/extended-research-logs/{SLUG}/report.md`

## The 9 Pass Types (executed by the runner)

The runner orchestrates these. Claude doesn't run them inline — but here's what each does so the user understands what their run is doing:

| Pass | Type | When fires | Purpose |
|---|---|---|---|
| 1 | DECOMPOSE | Always first | Break artifact into N phases + line_start/line_end ranges. Emits one HIGH finding per phase (central question). |
| 2 | CRITIQUE | After DECOMPOSE | Search literature for gaps in each phase's claims. Produces findings + contradictions. |
| 3 | ADVERSARIAL | After CRITIQUE | Hostile expert mode. Strongest possible attacks against the artifact. |
| 4 | OPTIONS_SWEEP | After ADVERSARIAL | Enumerate 3–6 distinct solution paths for the central problem. |
| 5+ | TARGETED_PROBE | Loop | One pass per open HIGH/MEDIUM finding. Tries to disprove the finding. Updates in-place via `findings_history[]`. |
| event | POSTMORTEM | Fires once when all HIGH/MED have ≥1 TARGETED_PROBE | Compares against real-world failures in domain. Uses `DOMAIN-POSTMORTEM-UNAVAILABLE` flag for niche domains. |
| every 6 from 8 | FRESH_OBSERVER | Pass 8, 14, 20... | Claude-generated 2k-token summary + finding titles only. "Identify only what is missing." |
| N−1 | INTEGRATION | One pass before final | Cross-phase synthesis. Identifies seams that break when phases combine. |
| N | FINAL_VERDICT | Final pass | Per-phase verdict (CONFIRMED / REFUTED / INCONCLUSIVE / STRUCTURAL-UNRESOLVABLE) + ranked options. |

## Convergence Rules (AND-gate)

The run terminates when **ALL** of these hold:
1. **3 consecutive passes** with zero new findings AND
2. **3 consecutive passes** with zero new contradictions AND
3. **All open findings are effective_severity LOW** (effective_severity = `min(raw_severity, MEDIUM)` if `source_flag=ANALOGOUS`) for 2 consecutive passes AND
4. **`adversarial_pass_count ≥ ceil(N/2)`** (forces at least one adversarial pass for any artifact, more for multi-phase)

**Or** the hard cap (`max_passes`) fires.

**Forced-ADVERSARIAL rule:** if (1)+(2)+(3) would fire but adversarial deficit blocks (4), the next pass MUST be ADVERSARIAL. The runner injects it explicitly. No silent burn of budget on dead-target probes.

## Termination Reasons (always in report.md)

- `CONVERGED` — all 4 AND-gate conditions met. Verdict trustworthy.
- `CAP-HIT (N open HIGH, M unresolved contradictions)` — hard cap fired. Findings remain.
- `STRUCTURAL-UNRESOLVABLE` — HIGH findings persisted across ≥3 consecutive passes (auto-tagged). Verdict treats them as inherent constraints, not gaps to close.
- `INTERRUPTED at pass K` — SIGINT during run. `--resume {slug}` continues from K+1.

## Report Format (`{WORKDIR}/report.md`)

```markdown
# Extended Research Report: {slug}
**Date:** {date} | **Passes:** {N}/{max} | **Verdict:** {verdict}

## Executive Summary
One paragraph. What the artifact is, verdict, single most important finding.

## Termination Reason
CONVERGED | CAP-HIT(...) | STRUCTURAL-UNRESOLVABLE | INTERRUPTED — with one-sentence why.

## Findings by Phase
### Phase 1: {name}
- **F001 [HIGH] [PRIMARY|ANALOGOUS]** — {claim}
  - Status: OPEN | RESOLVED ({resolution}) | STRUCTURAL-UNRESOLVABLE
  - Targeted probes: {N}, history: {findings_history list}
  - Best option: {option_label} (score: X.X)

## Integration Seams
{cross-phase issues from INTEGRATION pass}

## Exhaustive Flaw Table
| ID | Phase | Severity (raw → effective) | Source | Status | Resolution |

## Option Comparison
For each finding with multiple options:
| Option | Correctness (30%) | Simplicity (20%) | Blast (20%) | Reversibility (15%) | Speed (15%) | **Score** |
Highest-scoring option selected. Score margins < 0.5 flagged as judgment-call.

## Contradiction Log
All detected contradictions, paired resolutions.

## Recommended Next Actions
One concrete sentence per open HIGH finding.

## Metadata
- adversarial_pass_count: {N}
- fresh_observer_passes: [{list of pass numbers}]
- POSTMORTEM domain: {domain or "DOMAIN-POSTMORTEM-UNAVAILABLE"}
- last_heartbeat_ts: {iso}
```

## Examples

### Example 1 — Verify an architectural blueprint

```
/extended-research --mode per-phase
[paste the contents of ~/.claude/plans/my-multi-phase-plan.md here]
```

Runner extracts phases from the plan (looking for `## Phase` / `## Edit` / numbered sections), drills each. Returns per-phase verdict + integration seams + scored alternatives for any HIGH findings.

### Example 2 — Stress-test a single function

```
/extended-research --max-passes 10
[paste a 50-line Python function]
```

DECOMPOSE finds N=2 (logic-correctness phase + edge-case-handling phase). Formula gives max_passes=9. Convergence likely by pass 5–7. Output: ranked alternatives for any logic gaps found.

### Example 3 — Resume after Ctrl-C

```
/extended-research --resume gpt4-safety-alignment-a3f92c1d
```

Loads `~/.claude/extended-research-logs/gpt4-safety-alignment-a3f92c1d/ledger.json`, verifies artifact hash matches (or prompts), continues from `interrupted_at_pass + 1`.

## Files Touched

- `~/.claude/council-automation/extended_research_runner.py` — the orchestrator (long-running, async-spawned)
- `~/.claude/council-automation/requirements.txt` — `jsonschema`, `filelock`
- `~/.claude/extended-research-logs/{slug}/` — per-run workdir (artifact.txt, ledger.json, passes.jsonl, report.md, runner.log, runner.log.done, fresh_observer_summary.txt)

## Coordination With Other Commands

- **`/research-perplexity`** — both commands share the `submission_lock` (`~/.claude/council-automation/submission_lock.py`). If `/research-perplexity` is mid-call, the runner's lock acquire blocks up to 180s, then proceeds. Single-Claude-session-level serialization is automatic; cross-session via the file-based lock.
- **`/council-refine`** — independent. Different prompt path through Perplexity. No conflicts.
- **`/solve-perplexity`** — `/solve-perplexity` is for problem-solving (1–5 iterations with contradiction tracking); `/extended-research` is for VERIFICATION (5–40 iterations until convergence). Use solve for "how do I X?", use extended-research for "is this proposed X actually correct?"

## Cost & Time

- **Cost:** $0 — uses the existing Perplexity Pro login session via Playwright (no API key needed).
- **Time:** ~60–120s per pass. Typical runs: 5–40 minutes wall time. The artifact + complexity + convergence pattern determines actual run length.
- **Concurrency:** the runner serializes its own Perplexity calls via `submission_lock`. The user can keep using `/research-perplexity` in the same Claude Code session — calls will queue at the lock.
