# /stub-check — Deep Implementation Completeness Audit

Perform a thorough 3-phase audit of the current project's codebase to find code that is unfinished, shallow, skeletal, or not production-ready. Phase 0.5 runs a Perplexity research reconnaissance using GitHub connectors (runs in parallel with Phase 1). Phase 1 uses local scanning (Grep/Glob/Read) independently. Phase 2 merges both passes through Perplexity for final depth/brevity validation.

**Architecture**: Research recon (Perplexity + GitHub connectors) runs IN PARALLEL with local pattern scan → merge → research validation last (depth + brevity). ~90s total overhead. $0 cost via Perplexity login session.

**CRITICAL: Do NOT ask the user questions before completing all phases. Execute the full audit silently and present results at the end. Only interact if $ARGUMENTS specifies a subset of the codebase to audit.**

## Input

`$ARGUMENTS` = Optional path or module to audit (e.g., `automated-loop/`, `src/auth/`). If empty, audit the entire project from the working directory.

---

## Step 0: Detect Project Languages — MANDATORY, SILENT

Before scanning, auto-detect which languages and frameworks are present. This determines which pattern sets to use.

1. **Check for language markers** (run in parallel):
   - `Glob` for `**/*.py` → Python detected
   - `Glob` for `**/*.ts` or `**/*.tsx` → TypeScript detected
   - `Glob` for `**/*.js` or `**/*.jsx` → JavaScript detected
   - `Glob` for `**/*.go` → Go detected
   - `Glob` for `**/*.rs` → Rust detected
   - `Glob` for `**/*.java` or `**/*.kt` → Java/Kotlin detected
   - `Glob` for `**/*.rb` → Ruby detected
   - `Glob` for `**/*.cs` → C# detected
   - `Glob` for `**/*.swift` → Swift detected
   - `Glob` for `**/*.c` or `**/*.cpp` or `**/*.h` → C/C++ detected
   - `Glob` for `**/*.php` → PHP detected

2. **Check for framework markers** (read if they exist):
   - `package.json` → check `dependencies` for React, Next.js, Express, Fastify, NestJS, Vue, Angular, Svelte
   - `pyproject.toml` or `setup.py` → check for Django, Flask, FastAPI, SQLAlchemy
   - `Cargo.toml` → Rust crate metadata
   - `go.mod` → Go module metadata
   - `Gemfile` → Ruby gems
   - `pom.xml` or `build.gradle` → Java/Kotlin build system
   - `*.csproj` or `*.sln` → .NET project

3. **Build language list**: Record detected languages + frameworks. Use ONLY the relevant pattern sets below — skip patterns for languages not present.

---

## Phase 0.5: Research Reconnaissance — FIRST CHECK

**Purpose**: Use Perplexity's GitHub integration to scan the repository for architectural gaps and incomplete implementations that local grep patterns miss. Runs IN PARALLEL with Phase 1 — does NOT influence Phase 1's file selection (prevents confirmation bias). Results merge in Phase 2.

**CRITICAL: Phase 0.5 must NOT feed its hit list to Phase 1. Phase 1 runs its full independent scan. The hit list is used ONLY in Phase 2 merge as a post-sort overlay.**

### Step 0.5.0: Compile Session Context — MANDATORY, SILENT

1. Read project `MEMORY.md` from auto-memory directory
2. Run `git log --oneline -10` for recent work
3. Run `git diff --stat` for uncommitted changes
4. Use `Glob` for main source files, read structural files (README.md, pyproject.toml/package.json)
5. Run `ls -R` or `Glob **/*` (depth-limited) to capture directory tree for grounding
6. Synthesize internal context — do NOT output to user

### Step 0.5.1: Close Browser Bridge Sessions — MANDATORY

1. Call `mcp__browser-bridge__browser_close_session`
2. Wait 2 seconds (`sleep 2` via Bash)

### Step 0.5.2: Build Reconnaissance Query

Use the MANDATORY CONTEXT PREAMBLE from `/research-perplexity`, then a **grounded** recon prompt:

```
[ENVIRONMENT CONTEXT — READ FIRST]
This project is being developed using Claude Code, Anthropic's official CLI tool for Claude (claude.ai/claude-code). The developer uses a Claude Max subscription and works entirely in the terminal via the `claude` CLI command. Claude Code is an agentic coding assistant that reads/writes files, runs terminal commands, searches codebases, and executes multi-step development tasks autonomously. All code generation, refactoring, debugging, and project management happens through Claude Code's conversation interface — there is no IDE or GUI involved.
[END ENVIRONMENT CONTEXT]

You are a senior code auditor performing a **pre-scan reconnaissance**. Using your access to the repository, identify areas that appear unfinished, skeletal, or not production-ready.

REPOSITORY STRUCTURE (for grounding — examine these actual files):
{Insert directory tree from Step 0.5.0}

KEY FILES:
{Insert names + first 10 lines of main source files}

DETECTED LANGUAGES: {from Step 0}
SCAN FOCUS: {$ARGUMENTS if provided, otherwise "entire project"}

Examine the actual files in this repository and provide:
1. STUB CANDIDATES: Functions/methods that appear skeletal — short bodies, placeholder returns, TODO-heavy
2. API CONTRACT GAPS: Endpoints defined but not fully implemented, missing validation
3. ARCHITECTURAL GAPS: Missing modules or integrations referenced but not implemented
4. TEST COVERAGE SUSPICIONS: Complex logic with no corresponding test files
5. DEPENDENCY CONCERNS: Imported but underutilized modules

FORMAT as a HIT LIST table:
| File | Lines | Suspicion | Priority (CRITICAL/HIGH/MEDIUM/LOW) |

IMPORTANT: Only flag items you can verify in the actual repository files. Do not speculate about files you cannot see.
```

### Step 0.5.3: Execute Reconnaissance Query

Call `mcp__browser-bridge__research_query` with:
- `query`: The recon prompt from Step 0.5.2
- `includeContext`: `true`

**Error handling**: If query fails, wait 5s and retry once. If still fails, log "Research recon unavailable — proceeding with local scan only" and continue. The audit is valid without recon.

### Step 0.5.4: Hold Results for Phase 2

Parse the response and extract the HIT LIST + findings. **Do NOT pass to Phase 1.** Hold in context for Phase 2 merge only.

---

## Phase 1: Local Pattern Scan

**Concurrency**: Phase 0.5 (research recon) and Phase 1 (local scan) run in parallel. Phase 1 operates independently — it does NOT use Phase 0.5's hit list for file selection. Both passes feed into Phase 2 for merge and validation.

Systematically scan the codebase using Grep, Glob, and Read tools. Record every finding with file path, line number, category, and evidence. **Only use patterns for detected languages from Step 0.**

### Step 1.1: Discover Files

1. Use `Glob` for source files matching detected languages (see table below)
2. **Always exclude**: `node_modules/`, `__pycache__/`, `.git/`, `dist/`, `build/`, `*.min.js`, `venv/`, `.venv/`, `vendor/`, `target/`, `bin/`, `obj/`, `.next/`, `.nuxt/`, `coverage/`, `.tox/`
3. If `$ARGUMENTS` specifies a path, scope to that path only
4. Record total file count and language breakdown for the report

**File extensions by language**:

| Language | Extensions |
|----------|-----------|
| Python | `*.py` |
| TypeScript | `*.ts`, `*.tsx` |
| JavaScript | `*.js`, `*.jsx`, `*.mjs`, `*.cjs` |
| Go | `*.go` |
| Rust | `*.rs` |
| Java | `*.java` |
| Kotlin | `*.kt`, `*.kts` |
| Ruby | `*.rb` |
| C# | `*.cs` |
| Swift | `*.swift` |
| C/C++ | `*.c`, `*.cpp`, `*.cc`, `*.h`, `*.hpp` |
| PHP | `*.php` |

### Step 1.2: Stub & Skeleton Detection

Use `Grep` with patterns for each detected language (run in parallel where possible):

**Python patterns** (if detected):
```
^\s*pass\s*$                           # Empty pass statements
raise NotImplementedError              # Unimplemented methods
^\s*\.\.\.\s*$                         # Ellipsis body
return None\s*$                        # Bare return None (potential stub)
```

**JavaScript / TypeScript patterns** (if detected):
```
throw new Error\(['"]not implemented   # Unimplemented (case-insensitive)
throw new Error\(['"]todo              # TODO-as-error
^\s*return\s*;?\s*$                    # Empty return
^\s*\/\/\s*TODO                        # Inline TODO comments
```

**Go patterns** (if detected):
```
panic\(["']not implemented             # Unimplemented panic
panic\(["']todo                        # TODO panic
return nil, fmt\.Errorf.*not implemented
^\s*//\s*TODO                          # TODO comments
```

**Rust patterns** (if detected):
```
todo!\(\)                              # todo! macro
unimplemented!\(\)                     # unimplemented! macro
panic!\(["']not implemented            # Panic with message
^\s*//\s*TODO                          # TODO comments
```

**Java / Kotlin patterns** (if detected):
```
throw new UnsupportedOperationException  # Java unimplemented
throw new RuntimeException.*TODO         # TODO-as-exception
TODO\(\)|FIXME\(                         # Android Studio markers
return null;\s*//\s*(?:TODO|stub)        # Null return with TODO
```

**Ruby patterns** (if detected):
```
raise NotImplementedError              # Unimplemented methods
fail ["']Not implemented               # fail with message
^\s*#\s*TODO                           # TODO comments
```

**C# patterns** (if detected):
```
throw new NotImplementedException      # Unimplemented methods
throw new NotSupportedException        # Unsupported feature
^\s*//\s*TODO                          # TODO comments
```

**C/C++ patterns** (if detected):
```
^\s*//\s*TODO                          # TODO comments
assert\(false\).*not implemented       # Assert-as-stub
#error.*not implemented                # Preprocessor error
return -1;\s*//.*TODO                  # Error return with TODO
```

**PHP patterns** (if detected):
```
throw new \\?Exception\(['"]not implemented  # Unimplemented
throw new \\?BadMethodCallException          # Method stub
^\s*//\s*TODO                                 # TODO comments
```

**Generic markers** (always scan, all languages):
```
TODO|FIXME|HACK|XXX|TEMP|PLACEHOLDER|STUB|INCOMPLETE|WIP
not yet implemented|implement later|coming soon
```

For each match:
- Record: file, line number, matched text, 3 lines of surrounding context
- **Pre-classify severity** using file path heuristics:
  - Files containing `auth`, `security`, `payment`, `api`, `route`, `endpoint` → likely CRITICAL
  - Files containing `model`, `service`, `handler`, `controller` → likely HIGH
  - Files containing `util`, `helper`, `tool`, `script` → likely MEDIUM
  - Files in `test/`, `tests/`, `__tests__/`, `fixtures/` → likely LOW or FALSE POSITIVE

### Step 1.3: Shallow Implementation Detection

Read the top 10 files by finding density (most Grep hits). For each, look for:

- **Empty exception handlers**: `except.*:\s*pass` (Python), `catch.*\{\s*\}` (JS/TS/Java/C#), `rescue.*\n\s*end` (Ruby), `if err != nil \{.*\}` with no body (Go)
- **Functions under 3 lines** that should have more logic (skip property getters, simple delegates, trait/interface impls)
- **API endpoints** returning static/mock responses instead of real data
- **Database queries** that are hardcoded instead of parameterized
- **Missing input validation** on public-facing functions (no type checks, no bounds checks)
- **Hardcoded values** that should be configuration: URLs, ports, credentials, API keys
- **Framework-specific gaps** (adapt based on Step 0 detection):
  - **React/Vue/Svelte**: Components that render only placeholder text or empty divs
  - **Django/Flask/FastAPI**: Views/routes that return `HttpResponse(200)` or `{"status": "ok"}` without logic
  - **Express/NestJS/Fastify**: Route handlers with only `res.send()` or `res.json({})`
  - **Rails**: Controller actions with only `render json: {}` or `head :ok`
  - **Go**: Handler funcs that only call `w.WriteHeader(200)`
  - **Spring**: `@RequestMapping` methods with empty or trivial bodies

### Step 1.4: Test Gap Detection

Use `Grep` for skipped/empty tests matching detected languages:

**Python** (if detected):
```
@pytest.mark.skip|@unittest.skip|pytest.skip\(|xfail
def test_.*:\s*pass
```

**JavaScript / TypeScript** (if detected):
```
it\.skip\(|xit\(|xdescribe\(|test\.skip\(
describe\([^)]*\)\s*\{\s*\}
it\([^)]*\)\s*\{\s*\}
```

**Java / Kotlin** (if detected):
```
@Ignore|@Disabled
@Test.*\n\s*public void \w+\(\)\s*\{\s*\}
```

**Go** (if detected):
```
t\.Skip\(
func Test\w+.*\{\s*\}
```

**Rust** (if detected):
```
#\[ignore\]
#\[test\]\s*fn \w+\(\)\s*\{\s*\}
```

**Ruby** (if detected):
```
skip\s+['"]|pending\s+['"]
xit\s|xdescribe\s
```

**C#** (if detected):
```
\[Ignore\]|\[Skip\]
\[Test\].*\n\s*public void \w+\(\)\s*\{\s*\}
```

Also check for **modules with no corresponding test file** (adapt conventions to detected framework):
- Python: `src/foo.py` → `tests/test_foo.py` or `test/test_foo.py`
- JS/TS: `src/Foo.ts` → `__tests__/Foo.test.ts` or `src/Foo.spec.ts` or `test/Foo.test.ts`
- Go: `foo.go` → `foo_test.go` (same directory)
- Rust: check for `#[cfg(test)] mod tests` block within the same file, or `tests/` directory
- Java: `src/main/java/Foo.java` → `src/test/java/FooTest.java`
- Ruby: `lib/foo.rb` → `spec/foo_spec.rb` or `test/test_foo.rb`
- C#: `Foo.cs` → `FooTests.cs` or `Foo.Tests.cs`

### Step 1.5: False Positive Filtering

Before proceeding to Phase 2, filter out likely intentional patterns. **Apply only rules relevant to detected languages:**

**Universal (all languages):**
- `TODO` comments referencing a GitHub/Jira issue number (e.g., `TODO(#123)`, `FIXME(JIRA-456)`) → **DOWNGRADE** to LOW
- Files in `examples/`, `docs/`, `templates/`, `scripts/`, `tools/` → **DOWNGRADE** to LOW
- Mock/fixture/fake files → **SKIP** (test infrastructure)

**Python:**
- `NotImplementedError` in classes inheriting from `abc.ABC` or `Protocol` → **SKIP** (abstract interface)
- `pass` in `@pytest.fixture` or `conftest.py` → **SKIP** (test setup)
- `pass` in `__init__` methods with no other logic → **SKIP** (common pattern)
- `...` (Ellipsis) in `.pyi` stub files → **SKIP** (type annotation stubs)

**TypeScript:**
- `*.d.ts` type declaration files → **SKIP** (type stubs are intentional)
- `interface` or `type` definitions with method signatures → **SKIP** (declarations, not implementations)

**Go:**
- Functions satisfying an interface with only `return nil` or `return nil, nil` → **SKIP if interface compliance is required**
- `_test.go` files with helper functions containing `t.Skip()` for platform-specific tests → **SKIP**

**Rust:**
- `unimplemented!()` in trait default implementations → **SKIP** (compile-time enforced)
- `todo!()` in `#[cfg(test)]` blocks → **SKIP**

**Java/Kotlin:**
- `UnsupportedOperationException` in `abstract` class methods → **SKIP** (template method pattern)
- `@Override` methods with `super.method()` call only → **SKIP** (delegation)

**Ruby:**
- `raise NotImplementedError` in modules included via `include` → **SKIP** (mixin interface contract)

**C#:**
- `NotImplementedException` in `partial` class methods → **SKIP** (generated code placeholder)
- `NotSupportedException` in interface adapter patterns → **SKIP**

Move all filtered items to a separate "False Positives Detected" section in the report.

---

## Phase 2: Research Validation — LAST CHECK

Merge Phase 0.5 reconnaissance findings with Phase 1 local scan findings, then send through Perplexity for final depth/brevity validation.

### Step 2.0: Close Browser Bridge Sessions — MANDATORY

1. Call `mcp__browser-bridge__browser_close_session`
2. Wait 2 seconds (`sleep 2` via Bash)

### Step 2.1: Merge Findings

Combine both passes using these rules:

**Matching**: Normalize file paths before comparison. Match findings by `(normalized_path, line_number)` — not string comparison. Two findings match if they reference the same file within ±5 lines.

**Initial confidence tiers**:
- Found by **both** Phase 0.5 AND Phase 1 → `corroborated` (HIGH confidence)
- Found by **Phase 0.5 only** (research found, local missed) → `recon-only` (MEDIUM — architecturally interesting but unverified locally)
- Found by **Phase 1 only** (local found, research missed) → `local-only` (MEDIUM — pattern match, needs validation)

**Severity conflicts**: When Phase 0.5 and Phase 1 assign different severities to the same finding, use the **higher** severity (conservative — let Phase 2 validation downgrade if appropriate).

**Empty recon**: If Phase 0.5 returned no hits or was skipped due to error, all Phase 1 findings get `local-only` confidence. Do NOT treat empty recon as "recon confirmed nothing wrong."

### Step 2.2: Build Validation Query

Use the MANDATORY CONTEXT PREAMBLE from `/research-perplexity`, then:

```
[ENVIRONMENT CONTEXT — READ FIRST]
This project is being developed using Claude Code, Anthropic's official CLI tool for Claude (claude.ai/claude-code). The developer uses a Claude Max subscription and works entirely in the terminal via the `claude` CLI command. Claude Code is an agentic coding assistant that reads/writes files, runs terminal commands, searches codebases, and executes multi-step development tasks autonomously.
[END ENVIRONMENT CONTEXT]

You are a senior code auditor performing the FINAL VALIDATION of a completeness audit. Two prior passes have run:
1. RESEARCH RECONNAISSANCE (Perplexity + GitHub): Identified gaps from repository analysis
2. LOCAL PATTERN SCAN (Grep/Glob): Found stub patterns, TODO markers, shallow implementations

Your job is the definitive assessment. Respond in THREE SECTIONS:

## SECTION A: DEPTH CHECK — What was missed?
- Completeness gaps NEITHER pass caught
- Missing error handling around I/O, network, file operations
- Missing retry logic, timeouts, circuit breakers on external calls
- Missing input validation or output encoding
- State management gaps, middleware not applied, config referenced but unused

## SECTION B: BREVITY CHECK — What should be removed or downgraded?
- Which findings are FALSE POSITIVES? (intentional stubs, abstract interfaces, test mocks)
- Which findings are DUPLICATES across the two passes?
- Which severities are over-classified? (e.g., marked CRITICAL but actually MEDIUM)
- IMPORTANT: Do NOT silently remove any finding. For each removal/downgrade, state the finding and the reason.

## SECTION C: FINAL SEVERITY ASSESSMENT
For each finding (kept, new, or downgraded), provide:
- File:line
- Final severity: CRITICAL / HIGH / MEDIUM / LOW
- Source: corroborated / recon-only / local-only / validation-new
- One-line justification

RESEARCH RECONNAISSANCE FINDINGS:
{Insert Phase 0.5 findings}

LOCAL SCAN FINDINGS:
{Insert Phase 1 findings grouped by module}

CODEBASE CONTEXT:
{Insert key architectural files}
```

### Step 2.3: Execute Validation Query

Call `mcp__browser-bridge__research_query` with:
- `query`: The validation prompt from Step 2.2
- `includeContext`: `true`

### Step 2.4: Apply Validation Results

Process the response using these rules:

1. **New findings** (Section A): Add with source `validation-new`, severity as assessed
2. **False positives** (Section B): Mark as `potential_false_positive: true` with reason — do NOT delete. Move to False Positives section of report
3. **Severity changes** (Section B): Phase 2 validation wins on downgrades (it has most context). Upgrades require the finding to explain why
4. **Deduplicate** by `(file, line)` — keep the version with most context
5. **Final confidence** after validation:
   - `corroborated` + validated = `fully-validated` (highest)
   - `recon-only` + validated = `recon-validated`
   - `local-only` + validated = `local-validated`
   - `validation-new` = new finding from this pass
   - Any finding Phase 2 flagged as false positive = `disputed`

---

## Phase 3: Generate Report

Present the complete audit report to the user. Format:

```markdown
# Codebase Completeness Audit Report

**Project**: {project name from cwd}
**Languages**: {detected languages, e.g., "Python (42 files), TypeScript (18 files), Go (7 files)"}
**Scanned**: {total_files} files
**Timestamp**: {ISO 8601}
**Scope**: {$ARGUMENTS or "full project"}

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| CRITICAL | {n} | Production blockers — must fix before deploy |
| HIGH     | {n} | Fragile/incomplete — will fail under stress |
| MEDIUM   | {n} | Happy-path only — missing edge cases |
| LOW      | {n} | Polish/cleanup items |

**False positives filtered**: {n} (intentional stubs, test mocks, abstract classes)

---

## CRITICAL Findings

### {Category}: {Brief description}
- **File**: `{path}:{line}`
- **Evidence**:
  ```{lang}
  {code snippet — 3-5 lines of context}
  ```
- **Why critical**: {explanation}
- **Confidence**: {fully-validated / recon-validated / local-validated / corroborated / recon-only / local-only / validation-new / disputed}

{Repeat for each CRITICAL finding}

---

## HIGH Findings

{Same format, grouped by module/directory}

---

## MEDIUM Findings

{Same format, collapsed/condensed — show file:line and one-line description}

---

## LOW Findings

{One-line per finding: file:line — description}

---

## Recon-Only Findings

{Gaps identified by Phase 0.5 research reconnaissance that the local scan missed}

---

## Validation-New Findings

{Gaps identified by Phase 2 validation that neither prior pass caught}

---

## False Positives Detected

| File | Line | Pattern | Reason Excluded |
|------|------|---------|-----------------|
| {path} | {line} | {pattern} | Abstract base class |
| {path} | {line} | {pattern} | Test mock |

---

## Recommendations

1. Address all CRITICAL findings before next deployment
2. Create GitHub issues for HIGH findings with priority labels
3. Schedule tech debt sprint for MEDIUM backlog
4. LOW items can be addressed opportunistically
```

### Step 3.1: Save Report

Save the full report to `.workflow/completeness_audit.md` in the project directory.

---

## Phase 4: Summary to User

After saving, present a concise summary:

```
Completeness audit complete.

CRITICAL: {n} | HIGH: {n} | MEDIUM: {n} | LOW: {n}

Top critical findings:
1. {file:line} — {description}
2. {file:line} — {description}
3. {file:line} — {description}

Full report saved to .workflow/completeness_audit.md
```

If CRITICAL + HIGH count = 0, stop here. Otherwise append:

```
Proceeding to automatic fix planning...
```

---

## Phase 5: Automatic Fix Planning

**Trigger**: CRITICAL + HIGH finding count >= 1. If count = 0, skip this phase entirely — stop after Phase 4 summary.

### Step 5.0: Close Browser Bridge Sessions — MANDATORY

1. Call `mcp__browser-bridge__browser_close_session`
2. Wait 2 seconds (`sleep 2` via Bash)

### Step 5.1: Build Fix Research Query

Compose a fix-focused prompt using ALL CRITICAL and HIGH findings from the Phase 3 report. Include:

```
You are a senior engineer creating a concrete fix plan. I have a codebase completeness audit with CRITICAL and HIGH findings that need resolution. For each finding, provide:

1. ROOT CAUSE — Why does this gap exist? Is it a missing implementation, incomplete migration, or architectural gap?
2. FIX STRATEGY — The specific code changes needed. Include:
   - Exact file paths and line numbers
   - Code snippets showing the fix (before/after)
   - New files or dependencies needed (if any)
3. IMPLEMENTATION ORDER — Which fixes depend on others? What must be done first?
4. ACCEPTANCE CRITERIA — How to verify each fix works (test commands, manual checks)
5. RISK ASSESSMENT — What could break when applying each fix?

FINDINGS TO FIX:
{Insert ALL CRITICAL and HIGH findings with file paths, line numbers, code snippets, and surrounding context}

CODEBASE CONTEXT:
{Insert key architectural files, dependency info, and relevant source code from the scanned modules}

IMPORTANT: Be specific and actionable. No generic advice. Every fix must reference exact files and lines from the findings above.
```

### Step 5.2: Execute Fix Research Query

Call `mcp__browser-bridge__research_query` with:
- `query`: The fix prompt from Step 5.1
- `includeContext`: `true`

**Error handling**: If the query fails, wait 5 seconds and retry once. If it fails again, report "Perplexity session may be expired — run `/cache-perplexity-session` to refresh" and stop.

### Step 5.3: Persist Results

Save the fix research output to `~/.claude/council-logs/{timestamp}-stub-check-fixes-{project}.md` using ISO 8601 date format for the timestamp (e.g., `2026-03-12_1430`).

### Step 5.4: Enter Plan Mode — MANDATORY

Immediately enter plan mode (no user prompt needed). Structure the plan as follows:

**Two-tier plan structure** (matching `/research-perplexity` format):

1. **Master Plan**: High-level phases covering all CRITICAL and HIGH findings
   - Phase ordering based on dependency analysis from Step 5.2
   - Each phase has a clear scope and acceptance criteria

2. **Sub-plans per phase**: Detailed implementation steps within each phase
   - Exact file edits with before/after code
   - Test commands to verify each change
   - Rollback steps if something breaks

**Required final sections in the plan**:
- **Update project memory**: Add findings and fix strategies to project MEMORY.md / CLAUDE.md
- **Commit & push**: Stage changes, commit with descriptive message, push to remote

**Plan verification**: Before calling `ExitPlanMode`, run a verification pass by sending the plan + original fix research + codebase context through `mcp__browser-bridge__research_query` for critique. Revise once based on critique, then call `ExitPlanMode`. Maximum 1 verification pass — never re-verify.

### Step 5.5: Create Tasks from Plan

After the user approves the plan via `ExitPlanMode`:

1. Call `TaskCreate` once per plan phase, using the phase title as `subject` and details as `description`
2. Set `addBlockedBy` dependencies matching the phase ordering from Step 5.4
3. Begin executing the first unblocked task immediately

---

## Error Handling

| Error | Action |
|-------|--------|
| No source files found | Report "No source files found in {path}" and stop |
| Grep returns no findings | Report "No completeness gaps detected — codebase looks clean" |
| Perplexity query fails | Present Phase 1 results only with note "Cross-validation unavailable" |
| Browser collision / empty results | Close browser-bridge, wait 2s, retry once |
| Session expired | Report "run `/cache-perplexity-session` to refresh" |
| Phase 5 skipped (no CRITICAL/HIGH) | Silently skip — present Phase 4 summary only |
| Fix research query fails | Retry once after 5s; if still fails, report "run `/cache-perplexity-session` to refresh" and stop |
| Recon query fails (Phase 0.5) | Log warning, skip recon, proceed with local scan only — all findings get `local-only` confidence |
| Contradictory assessments | Phase 2 validation wins on severity downgrades; never silently deletes — marks `disputed` |

## Key Differences from Other Commands

| Aspect | /stub-check | /research-perplexity | /review |
|--------|-------------|---------------------|---------|
| **Purpose** | Find incomplete code | Strategic analysis | Code quality review |
| **Method** | Research recon ∥ local scan → merge → research validation | Perplexity only | Claude-only review |
| **Output** | Severity-ranked findings with multi-pass confidence | Narrative analysis | Review comments |
| **Scope** | Entire codebase or module | Session context | Specific changes |
| **Plan mode** | Automatic if CRITICAL/HIGH findings exist | Automatic | No |
| **Research passes** | 2 (recon + validation, parallel with local) | 1 + 1 verification | 0 |
| **Cost** | $0 | $0 | $0 |
