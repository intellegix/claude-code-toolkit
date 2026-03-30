# /solve-perplexity — Iterative Problem Solver via Perplexity

Iteratively solve complex bugs, edge cases, and nearly-unsolvable issues using progressive Perplexity queries with contradiction tracking and convergence detection. **Tier 2.5** in the escalation ladder — between single-pass `/research-perplexity` (Tier 2) and user handoff (Tier 3).

**Cost: $0** — uses Perplexity login session only (Playwright browser automation).

**CRITICAL: This is a SOLVER, not a PLANNER. It outputs concrete fixes directly. Do NOT enter plan mode. Do NOT ask the user questions before completing Step 0 and Step 1. Compile context silently, decompose the problem, and begin iterating.**

**MANDATORY CONTEXT PREAMBLE — EVERY QUERY, NO EXCEPTIONS:** Every single query sent to Perplexity MUST begin with the following preamble block. This is a hard rule — never omit it, never paraphrase it, never move it to a footnote. It goes at the TOP of every query, before any other content:

```
[ENVIRONMENT CONTEXT — READ FIRST]
This project is being developed using Claude Code, Anthropic's official CLI tool for Claude (claude.ai/claude-code). The developer uses a Claude Max subscription and works entirely in the terminal via the `claude` CLI command. Claude Code is an agentic coding assistant that reads/writes files, runs terminal commands, searches codebases, and executes multi-step development tasks autonomously. All code generation, refactoring, debugging, and project management happens through Claude Code's conversation interface — there is no IDE or GUI involved. Responses should account for this workflow: recommend CLI-compatible tools, terminal-based solutions, and approaches that work well with an AI coding agent operating in a command-line environment.
[END ENVIRONMENT CONTEXT]
```

## When to Use

- Tier 2 (`/research-perplexity`) returned low-confidence or contradictory results
- Problem requires multiple angles of investigation (e.g., interplay between library version, OS, and config)
- Edge case that doesn't match any known pattern in docs or Stack Overflow
- Bug where root cause is ambiguous — multiple plausible hypotheses need systematic elimination
- Integration issues spanning multiple systems (API + DB + auth + deployment)

## When NOT to Use

- Problem is straightforward — use Tier 0/1/2 instead
- You need strategic analysis — use `/research-perplexity` or `/export-to-council`
- You need plan refinement — use `/council-refine`
- Problem is well-understood but solution is complex — just implement it
- Error message directly indicates the fix (Tier 0)

## Input

`$ARGUMENTS` = Problem description. Should include:
- **Expected behavior**: What should happen
- **Actual behavior**: What actually happens
- **What was tried**: Previous fix attempts and their results
- **Error output**: Key error lines (not full traces)

If `$ARGUMENTS` is empty AND you cannot determine a problem from session context, ask the user to describe the problem.

## Workflow

### Step 0: Compile Session Context — MANDATORY, SILENT

**Before doing ANYTHING else**, compile the current session state. Do NOT ask the user any questions during this step — proceed silently and autonomously.

1. **Read project memory**: Read the project's `MEMORY.md` from the auto-memory directory to understand what's been worked on, recent patterns, and known issues
2. **Recent commits**: Run `git log --oneline -10` to see recent work
3. **Uncommitted work**: Run `git diff --stat` to see what's in progress
4. **Active tasks**: Check `TaskList` for any active/pending tasks
5. **Synthesize**: Form a 1-paragraph internal "current state" summary — do NOT output this to the user, just hold it in context for Step 1

Do NOT present findings. Do NOT ask questions. Proceed directly to Step 0.5.

### Step 0.5: Explore Codebase — MANDATORY, SILENT

After compiling session context (Step 0), explore the actual codebase:

1. **Find key files**: Use `Glob` for main source files (*.py, *.ts, *.js) in project root and src/
2. **Read recently modified**: Run `git diff --name-only HEAD~5 HEAD`, read up to 10 files (first 100 lines each)
3. **Read structural files**: README.md, pyproject.toml, package.json if they exist
4. **Read problem-relevant files**: Based on `$ARGUMENTS`, identify and read files most likely related to the problem (error traces, imports, config files)
5. **Synthesize**: Form internal "codebase summary" — key files, purposes, connections, and problem-relevant code snippets

Do NOT present findings. Do NOT ask questions. Include this context when building queries.

### Step 1: Decompose Problem

Break the problem into 3-5 targeted sub-questions. Initialize the `PROBLEM_STATE` tracking object (hold in context, not output to user):

```
PROBLEM_STATE = {
  iteration: 0,
  sub_questions: [
    { id: 1, question: "...", status: "open", confidence: 0, findings: [] },
    { id: 2, question: "...", status: "open", confidence: 0, findings: [] },
    ...
  ],
  contradictions: [],        // { finding_a: "...", finding_b: "...", resolution: null }
  attempted_fixes: [],       // from $ARGUMENTS + discovered during iteration
  overall_confidence: 0,     // 1-10 scale
  root_cause: null,          // updated as evidence accumulates
  proposed_fix: null,        // updated as evidence accumulates
  convergence_reason: null   // set when loop exits
}
```

**Output to user**: "Decomposed into {N} sub-questions. Starting iteration loop."

### Step 1.5: Close Browser Bridge Sessions — MANDATORY

**Before launching any Playwright-based query**, close active browser-bridge sessions to prevent DevTools Protocol collisions:

1. Call `mcp__browser-bridge__browser_close_session` to release all browser-bridge tab connections
2. Wait 2 seconds (`sleep 2` via Bash) for Chrome DevTools to fully detach
3. Then proceed to Step 2

**Why:** The `research_query` and `labs_query` tools launch Playwright (separate Chromium instance). If `browser-bridge` has active Chrome DevTools connections, the two systems can collide — causing tab detachment errors, empty results, and `"Debugger is not attached"` failures. Closing browser-bridge first prevents this.

### Step 2: Iteration Loop (max 5 iterations)

For each iteration (1 through 5):

#### 2.1: Select Query Mode

| Iteration | Mode | Rationale |
|-----------|------|-----------|
| 1 | `research_query` | Breadth-first — cast wide net for hypotheses |
| 2+ | `labs_query` | Depth-first — drill into specific hypotheses |
| Any (contradiction) | `research_query` | Fresh perspective to resolve conflicting findings |

**Exception**: If iteration 2+ has unresolved contradictions, use `research_query` instead of `labs_query` to get a fresh perspective.

#### 2.2: Build Iteration Query

**Start with the MANDATORY CONTEXT PREAMBLE**, then append the iteration-specific template:

**Iteration 1 (Broad Investigation):**

```
[ENVIRONMENT CONTEXT — READ FIRST]
{context preamble}
[END ENVIRONMENT CONTEXT]

PROBLEM INVESTIGATION — Iteration 1 (Broad)

PROBLEM STATEMENT:
{$ARGUMENTS — expected vs actual behavior}

SUB-QUESTIONS TO INVESTIGATE:
{numbered list of sub-questions from PROBLEM_STATE}

PREVIOUS FIX ATTEMPTS (all failed):
{list of attempted_fixes from PROBLEM_STATE}

CODE CONTEXT:
{relevant code snippets from Step 0.5 — scoped to problem area}

ENVIRONMENT:
{language version, framework version, OS, platform}

Please respond with:
1. ROOT CAUSE HYPOTHESES: Ranked list of possible causes (most likely first), each with confidence (1-10)
2. SUB-QUESTION ANSWERS: For each sub-question, provide answer + confidence (1-10) + evidence
3. KNOWN ISSUES: Any documented bugs, GitHub issues, or version-specific problems that match
4. CONCRETE FIX: Your best-guess fix with actual code (not pseudocode)
5. VERIFICATION STEPS: How to confirm the fix works
6. ALTERNATIVE APPROACHES: If primary fix fails, what else to try
7. OVERALL CONFIDENCE: 1-10 score for your recommended fix
```

**Iteration 2+ (Targeted Deep-Dive):**

```
[ENVIRONMENT CONTEXT — READ FIRST]
{context preamble}
[END ENVIRONMENT CONTEXT]

PROBLEM INVESTIGATION — Iteration {N} (Targeted)

ORIGINAL PROBLEM:
{$ARGUMENTS — expected vs actual behavior}

FINDINGS FROM PREVIOUS ITERATIONS:
{for each previous iteration: key findings, confidence scores}

ANSWERED SUB-QUESTIONS (settled):
{questions with confidence >= 7 and their answers}

OPEN SUB-QUESTIONS (still investigating):
{questions with confidence < 7}

CONTRADICTIONS TO RESOLVE:
{list of contradictions from PROBLEM_STATE — these are HIGH PRIORITY}

CURRENT BEST HYPOTHESIS:
{root_cause from PROBLEM_STATE}

CURRENT PROPOSED FIX:
{proposed_fix from PROBLEM_STATE}

Please respond with:
1. CONTRADICTION RESOLUTION: For each listed contradiction, which finding is correct and why
2. REFINED ROOT CAUSE: Updated root cause given all evidence (explain what changed from previous)
3. REMAINING ANSWERS: Answers for open sub-questions + confidence (1-10)
4. UPDATED FIX: Refined fix incorporating new evidence (actual code, not pseudocode)
5. EDGE CASES: Scenarios where the fix might not work
6. VERIFICATION: Steps to confirm fix AND validate edge cases
7. UPDATED CONFIDENCE: 1-10 score for the refined fix
```

#### 2.3: Execute Query

Call the selected MCP tool (`research_query` or `labs_query`) with:
- `query`: The prompt from 2.2
- `includeContext`: `true`

#### 2.4: Extract and Update State

Parse the response and update `PROBLEM_STATE`:
- Update sub-question confidence scores and findings
- Add new contradictions if response conflicts with previous findings
- Update `root_cause` and `proposed_fix`
- Calculate `overall_confidence` as: min(sub-question confidences) weighted by root-cause confidence
- Mark sub-questions as "answered" if confidence >= 7

#### 2.5: Detect Contradictions

Compare new findings against all previous findings. A contradiction exists when:
- Two iterations give opposite answers to the same sub-question
- A recommended fix in iteration N contradicts a finding from iteration N-1
- Root cause hypothesis changes category (e.g., "config issue" vs "code bug")

Add detected contradictions to `PROBLEM_STATE.contradictions` with both findings cited.

#### 2.6: Convergence Check

| Condition | Action |
|-----------|--------|
| `overall_confidence >= 8` AND no unresolved contradictions AND `proposed_fix` exists | **STOP** — converged |
| Confidence gain < 1 from previous iteration | **STOP** — diminishing returns |
| `iteration >= 5` | **STOP** — max iterations reached |
| All sub-questions answered with confidence >= 7 | **STOP** — fully answered |
| Otherwise | **CONTINUE** — increment iteration |

Set `convergence_reason` to the matching condition.

#### 2.7: Progress Update (Output to User)

After each iteration, display a 2-3 line update:

```
Iteration {N}/{max}: confidence {X}/10 | {Y}/{Z} sub-questions answered | {C} contradictions
Current hypothesis: {one-line root cause}
```

#### 2.8: Browser Cleanup Between Iterations

Before starting the next iteration:
1. Call `mcp__browser-bridge__browser_close_session`
2. Wait 2 seconds (`sleep 2` via Bash)
3. Then proceed to next iteration's query

### Step 3: Solution Synthesis

After the iteration loop exits, synthesize the final solution. **Output to user:**

```
## Solution Summary

**Iterations**: {N} | **Convergence**: {convergence_reason} | **Confidence**: {X}/10

### Root Cause
{root_cause — 2-3 sentences explaining the underlying issue}

### Fix
{proposed_fix — actual code with file paths and line references}

### Verification
{step-by-step verification procedure}

### Edge Cases
{scenarios to watch for, if any}

### Iteration Trail
{1-line summary per iteration: what was learned, what changed}

### Contradictions Resolved
{if any: what conflicted, how it was resolved, which evidence won}
```

### Step 4: Persist Results

Save the full solution (including iteration trail and PROBLEM_STATE summary) to:
`~/.claude/council-logs/{YYYY-MM-DD_HHmm}-solve-{projectName}.md`

### Step 5: Memory Write-Back — MANDATORY

Record the problem signature and fix in the project's MEMORY.md so this problem class resolves via Tier 1 next time:

```markdown
## Research Fix: {error signature} ({date})
- **Root cause**: {1-line root cause}
- **Fix**: {1-line fix description}
- **Prevention**: {how to avoid this in the future}
- **Source**: /solve-perplexity ({N} iterations, confidence {X}/10)
```

If MEMORY.md is approaching 150 lines, move older entries to a `memory/research-fixes.md` topic file.

### Step 6: Post-Solve Prompt

Present 4 choices to the user — do NOT auto-apply, do NOT enter plan mode:

```
Solution ready (confidence {X}/10). Choose:
1. Apply fix — implement the proposed changes now
2. Verify first — run verification steps before applying
3. Dig deeper — run additional iterations (override convergence)
4. Discard — solution doesn't look right, try a different approach
```

Wait for user selection before proceeding.

## Differences from Existing Commands

| Aspect | /solve-perplexity | /research-perplexity | /council-refine |
|--------|-------------------|---------------------|-----------------|
| Purpose | Solve specific problem | Strategic analysis | Refine a plan |
| Iterations | 1-5 adaptive | 2 (research + verify) | 1-3 fixed loop |
| Mode strategy | research -> labs | research only | council only |
| Plan mode | **NO** | YES | NO |
| Output | Concrete fix | Strategic roadmap | Refined plan |
| Contradiction tracking | **YES** | NO | NO |
| Memory write-back | **YES** (automatic) | NO | NO |
| Tier | 2.5 | 2 | N/A |

## Error Handling

- **Query fails on iteration 1**: Call `browser_close_session`, wait 2 seconds, retry once. If still fails, suggest `/cache-perplexity-session` to refresh the Perplexity login session.
- **Query fails on iteration 2+**: Present partial findings from successful iterations as the solution (reduced confidence). Note which iterations succeeded and which failed.
- **All 5 iterations with confidence < 5**: Warn user that the problem may need a different approach. Suggest `/export-to-council` for multi-model perspective, or escalate to Tier 3 (user handoff) with structured decision request.
- **Browser collision / empty results**: Close browser-bridge sessions (`browser_close_session`), wait 2 seconds, retry once. If still empty, report "Perplexity session may be expired — run `/cache-perplexity-session` to refresh."
- **Session expired**: Report "run `/cache-perplexity-session` to refresh Perplexity login session"
