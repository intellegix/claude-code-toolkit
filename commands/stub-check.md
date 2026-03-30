# /stub-check — Deep Implementation Completeness Audit

Perform a thorough 2-phase audit of the current project's codebase to find code that is unfinished, shallow, skeletal, or not production-ready. Phase 1 uses local scanning (Grep/Glob/Read). Phase 2 sends findings to Perplexity for cross-validation and gap detection.

**Architecture**: Local scan first → Perplexity validation second (Semgrep/SonarQube pattern). $0 cost via Perplexity login session.

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

## Phase 1: Local Pattern Scan

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

## Phase 2: Perplexity Cross-Validation

### Step 2.0: Close Browser Bridge Sessions — MANDATORY

1. Call `mcp__browser-bridge__browser_close_session`
2. Wait 2 seconds (`sleep 2` via Bash)

### Step 2.1: Build Cross-Validation Query

Group Phase 1 findings by module/directory. For the top 3-5 modules with the most findings, build a Perplexity query:

```
You are a senior code auditor performing a production readiness review. I've run a local scan and found potential completeness gaps in a codebase. Your job is to:

1. VALIDATE each finding — is it a genuine gap or a false positive?
2. FIND MISSING GAPS — what did the local scan miss? Look for:
   - Missing error handling (no try/catch around I/O, network, or file operations)
   - Missing retry logic or timeouts on external API calls
   - Missing rate limiting on public endpoints
   - Missing database transactions where atomicity is required
   - Missing input sanitization or output encoding
   - Missing logging/observability around critical operations
   - State management gaps (stores defined but never connected)
   - WebSocket/SSE connections opened but no message handling
   - Middleware registered but not applied to routes
   - Config/feature flags referenced but never used
3. ASSESS SEVERITY — for each finding, rate as:
   - CRITICAL: Blocks production use, security vulnerability, data loss risk
   - HIGH: Works but fragile, will fail under load or edge cases
   - MEDIUM: Incomplete but functional for happy path
   - LOW: Polish, cleanup, or nice-to-have

LOCAL SCAN FINDINGS:
{Insert grouped findings with file paths, line numbers, and evidence}

CODEBASE CONTEXT:
{Insert key architectural files: README.md sections, main module structure}
```

### Step 2.2: Execute Research Query

Call `mcp__browser-bridge__research_query` with:
- `query`: The cross-validation prompt from Step 2.1
- `includeContext`: `true`

### Step 2.3: Merge Results

Combine Phase 1 local findings with Phase 2 Perplexity findings:
- Findings validated by both → **confidence: HIGH**
- Findings only from local scan → **confidence: MEDIUM** (may be false positive)
- Findings only from Perplexity → **confidence: MEDIUM** (verify manually)
- Mark any Phase 1 findings that Perplexity flagged as false positives

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
- **Confidence**: {HIGH if validated by Perplexity, MEDIUM if local-only}

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

## Perplexity-Only Findings

{Gaps identified by Perplexity that the local scan missed}

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

## Key Differences from Other Commands

| Aspect | /stub-check | /research-perplexity | /review |
|--------|-------------|---------------------|---------|
| **Purpose** | Find incomplete code | Strategic analysis | Code quality review |
| **Method** | Local scan + Perplexity validation | Perplexity only | Claude-only review |
| **Output** | Severity-ranked finding list | Narrative analysis | Review comments |
| **Scope** | Entire codebase or module | Session context | Specific changes |
| **Plan mode** | Automatic if CRITICAL/HIGH findings exist | Automatic | No |
| **Cost** | $0 | $0 | $0 |
