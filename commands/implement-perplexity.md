# /implement-perplexity — Research-Validated Implementation Planning

Bridge the gap between creative-research blueprints and executable implementation plans. Uses 2-4 targeted Perplexity research queries to produce a dependency-aware, externally-validated plan ready for TaskCreate and /orchestrator-multi.

**2-4 Perplexity queries via Playwright** — ~3-6 min total, free per query.

**CRITICAL: Do NOT ask the user questions before completing Step 0. Compile context silently, build queries, and execute. Only interact at the Scope Gate (Step 2) or after plan synthesis (Step 7).**

**MANDATORY CONTEXT PREAMBLE — EVERY QUERY, NO EXCEPTIONS:** Every single query sent to Perplexity MUST begin with the following preamble block. This is a hard rule — never omit it, never paraphrase it, never move it to a footnote. It goes at the TOP of every query, before any other content:

```
[ENVIRONMENT CONTEXT — READ FIRST]
This project is being developed using Claude Code, Anthropic's official CLI tool for Claude (claude.ai/claude-code). The developer uses a Claude Max subscription and works entirely in the terminal via the `claude` CLI command. Claude Code is an agentic coding assistant that reads/writes files, runs terminal commands, searches codebases, and executes multi-step development tasks autonomously. All code generation, refactoring, debugging, and project management happens through Claude Code's conversation interface — there is no IDE or GUI involved. Responses should account for this workflow: recommend CLI-compatible tools, terminal-based solutions, and approaches that work well with an AI coding agent operating in a command-line environment.
[END ENVIRONMENT CONTEXT]
```

## Input

`$ARGUMENTS` = Feature selection from creative-research output. Examples:
- "Feature #5" — single feature by number
- "Features #2 and #5" — multiple features
- 'Feature #1 "Latent Thread Navigator"' — by name
- Empty — read latest creative-research stage logs, present TOP 5, ask user to pick

## Workflow

### Step 0: Compile Session Context — MANDATORY, SILENT

**Before doing ANYTHING else**, compile the current session state. Do NOT ask the user any questions during this step — proceed silently and autonomously.

1. **Read project memory**: Read the project MEMORY.md from the auto-memory directory to understand conventions, recent patterns, and known issues
2. **Recent commits**: Run `git log --oneline -10` to see recent work
3. **Uncommitted work**: Run `git diff --stat` to see what's in progress
4. **Active tasks**: Check TaskList for any active/pending tasks
5. **Synthesize**: Form a 1-paragraph internal "current state" summary — do NOT output this to the user, just hold it in context

Do NOT present findings. Do NOT ask questions. Proceed directly to Step 0.5.

### Step 0.5: Explore Codebase and Parse Creative Research — MANDATORY, SILENT

After compiling session context (Step 0), explore the codebase and extract feature blueprints:

**Codebase exploration:**
1. **Find key files**: Use Glob for main source files (*.py, *.ts, *.js) in project root and src/
2. **Read recently modified**: Run `git diff --name-only HEAD~5 HEAD`, read up to 10 files (first 100 lines each)
3. **Read structural files**: README.md, pyproject.toml, package.json, CLAUDE.md if they exist
4. **Read relevant patterns**: Check files in the patterns directory that match the project stack

**Creative research parsing:**
5. **Find stage logs**: Glob for files matching *creative-stage* in the council-logs directory
6. **Read Stage 2 log** (viability scores): Parse each feature's impact, effort, uniqueness, composite score, and verdict
7. **Read Stage 3 log** (blueprints): Parse phases, hour estimates, key files, dependencies, and risk notes for selected features

**If no creative-research logs found**: Ask the user to provide feature descriptions manually (fallback mode). Present: "No creative-research logs found. Please describe the feature(s) you want to implement, including scope and key files."

**If $ARGUMENTS is empty and logs exist**: Present the TOP 5 features from Stage 2 as a numbered list with composite scores and verdicts. Ask the user to pick. Wait for response before continuing.

Do NOT present other findings. Proceed to Step 1 after feature selection is confirmed.

---

## Step 1: Architecture Recon (Q1) — ALWAYS runs

Build and execute the shared infrastructure query using compiled context.

### Query Construction

**Start with the MANDATORY CONTEXT PREAMBLE**, then append:

```
ARCHITECTURE RECON for implementing {N} features simultaneously in {project}.

FEATURES SELECTED:
{For each feature: name, impact score, effort score, hour estimate, key files from blueprint}

CODEBASE CONTEXT:
{Tech stack, patterns from project CLAUDE.md, MEMORY.md excerpts, recent git history}

EXISTING ARCHITECTURE:
{Key file summaries from Step 0.5 — actual code snippets, not just file names}

Identify:
1. Shared DB tables, models, or schemas needed by multiple features
2. Shared utilities, middleware, or services that can be reused across features
3. Correct implementation order to avoid circular dependencies between features
4. Existing codebase patterns that must be followed (naming, error handling, validation)
5. Cross-cutting concerns: auth, error handling, logging, caching impacts
6. Integration risks between the selected features (schema conflicts, API surface overlap, state management)
7. Estimated total effort for shared infrastructure (hours)
```

### Execution

1. Call `mcp__browser-bridge__research_query` with:
   - `query`: The prompt above (with context baked in)
   - `includeContext`: `true`
2. **On success**: Save raw response to the council-logs directory as `{YYYY-MM-DD_HHmm}-implement-q1-{projectName}.md`
3. **On failure**: Wait 5 seconds, retry once. If second attempt fails, skip shared infra detection. Flag the plan with `[MANUAL REVIEW: shared infra not validated]` and continue to Step 2.

---

## Step 2: Scope Gate

Calculate total estimated hours and evaluate scope:

```
total_hours = sum(blueprint hours for all selected features) * 1.3  (integration buffer)
```

**If total_hours > 40**: Present to user: "Estimated {total_hours}h with integration buffer. Recommend splitting into phases: Phase 1 = data layer + core backend, Phase 2 = frontend + polish. Full scope or split?" Wait for answer.

**If total_hours > 80**: WARN: "Scope likely too large for single implementation session. Strongly recommend splitting."

This gate is advisory — user decides whether to proceed at full scope or split.

---

## Step 3: Feature Deep Dives (Q2a, Q2b) — ALWAYS runs

Execute per-feature deep dive queries. Run one query per selected feature (max 2 features).

### Parallelization Rule

- **Features touch independent data domains** (no shared new schemas, no producer-consumer relationship): Run Q2a and Q2b in **parallel** (separate `research_query` calls in the same message)
- **Features share new DB schemas or one consumes the other's output**: Run **sequentially** — Q2b seeds from Q2a summary

### Per-Feature Query Template

**Start with the MANDATORY CONTEXT PREAMBLE**, then append:

```
IMPLEMENTATION DEEP DIVE for "{feature_name}" in {project}.

ARCHITECTURE CONSTRAINTS (from recon):
{Q1 shared infrastructure summary}
{Q1 ordering recommendation}

FEATURE BLUEPRINT:
- Phases: {from creative-research Stage 3}
- Hour estimate: {hours}h
- Key files: {from blueprint}
- Uniqueness score: {score} — {rationale from Stage 2}

CODEBASE PATTERNS:
{Relevant patterns from the patterns directory — actual pattern content, not just file names}

EXISTING CODE CONTEXT:
{Actual code snippets from files this feature will modify — from Step 0.5}

Provide:
1. Step-by-step implementation sequence (Types/Interfaces first, then DB migrations, then Backend/API, then Frontend, then Tests)
2. Specific file paths to create or modify (following project naming conventions exactly)
3. External library recommendations with version and rationale for each
4. Edge cases and failure modes specific to this feature
5. Test strategy: unit tests, integration tests, E2E checkpoints with specific test file paths
6. Estimated hours per implementation step (validate or refine the blueprint estimate)
7. Risk assessment: what is most likely to go wrong, and the mitigation for each risk
```

### Execution

1. Call `mcp__browser-bridge__research_query` for each feature with:
   - `query`: The per-feature prompt above
   - `includeContext`: `true`
2. **On success**: Save each response to the council-logs directory:
   - Q2a: `{YYYY-MM-DD_HHmm}-implement-q2a-{projectName}.md`
   - Q2b: `{YYYY-MM-DD_HHmm}-implement-q2b-{projectName}.md`
3. **Parallel failure fallback**: If EITHER Q2a or Q2b fails when run in parallel, do NOT abort. Instead: (a) log a note "Parallel Q2 failed, retrying sequentially", (b) re-run the FAILED query as a single sequential `research_query` call, (c) continue with synthesis using whichever results are available.
4. **Batch rule for 3+ features**: If the user selected more than 2 features (e.g., "all"), group features into batches of 2 for Q2 queries. Run each batch sequentially (not all in parallel) to stay within Perplexity's ~5 concurrent session soft limit.
5. **Q2a fails** (both parallel and sequential retry): Use blueprint-only plan for that feature with `[RESEARCH UNAVAILABLE]` banner.
6. **Q2b fails but Q2a succeeded**: Present Feature A plan fully, Feature B with blueprint-only fallback.
7. **All Q2 queries fail**: Fall back to procedural plan from blueprints only (no external validation). Log failure to council-logs.

---

## Step 4: In-Context Synthesis (No Query)

Agent performs locally — no Perplexity call needed. Merge Q1 + Q2 results into a unified plan:

1. **Extract shared infrastructure** from Q1 + Q2 responses — items referenced by multiple features become the Foundation Phase
2. **Build dependency graph** — annotate each phase with `[depends: FeatureA.Phase2]` or `[independent]`
3. **Risk-order features** — implement the highest-uncertainty feature first (lowest uniqueness score from creative-research, most external API dependencies) as a de-risk spike
4. **Assign parallel/sequential flags** — phases with no cross-feature dependencies get `[parallel-safe]`, shared DB migrations get `[sequential-required]`
5. **Generate plan** in the output format specified in Step 7

---

## Step 5: Post-Synthesis Checklist

Verify the synthesized plan against these structural checks:

```
POST-SYNTHESIS CHECKLIST:
[ ] Every feature phase has a git branch name assigned
[ ] Shared infrastructure identified and sequenced as Foundation Phase (first)
[ ] No circular dependencies in the dependency graph
[ ] Acceptance criteria specified for each Phase 1 task
[ ] Scope gate evaluated (hours under 40 or split recommended)
[ ] Orchestrator directive block complete with parallel/sequential annotations
```

If any item fails, resolve it from existing Q1/Q2 context before proceeding. Do NOT run additional Perplexity queries for checklist failures.

---

## Step 6: Conditional Risk Synthesis (Q3)

**Trigger conditions** (ANY one triggers Q3):
- Total hours > 40
- Q2 results contain conflicting infrastructure recommendations
- Features share a new DB schema that was not pre-existing

**If triggered**, run one additional research_query:

**Start with the MANDATORY CONTEXT PREAMBLE**, then append:

```
RISK AND INTEGRATION REVIEW for multi-feature implementation plan.

MERGED PLAN:
{Full synthesized plan from Step 4}

ARCHITECTURE RECON FINDINGS:
{Q1 summary}

PER-FEATURE FINDINGS:
{Q2a and Q2b summaries}

Evaluate:
1. Cross-feature conflicts: Do any implementation steps contradict each other?
2. Ordering validation: Is the proposed dependency graph correct? Any hidden dependencies?
3. Schema conflicts: Do DB migrations from different features collide?
4. Go/no-go criteria: What conditions, if discovered during implementation, should trigger a stop-and-reassess?
5. Risk mitigations: For each MEDIUM or HIGH risk item, is the mitigation sufficient?
6. Estimated total hours: Does the integrated plan's effort match the sum of parts, or does integration add overhead?
```

**Execution**:
1. Call `mcp__browser-bridge__research_query` with the prompt above and `includeContext: true`
2. Save response to council-logs as `{YYYY-MM-DD_HHmm}-implement-q3-{projectName}.md`
3. If Q3 fails: Retry once. If still fails, skip risk synthesis, note `[RISK SYNTHESIS UNAVAILABLE]` in plan header. Continue to Step 7.

**If NOT triggered**, skip directly to Step 7.

---

## Step 7: Plan Mode Output

Enter plan mode using EnterPlanMode. Write the synthesized plan to the plan file in this format:

```markdown
## Implementation Plan: {Feature Names}
**Total Estimated Hours**: {N}h (includes 1.3x integration buffer)
**Research-Validated**: Yes ({query_count} Perplexity queries)
**Scope Gate**: {WITHIN_SCOPE | PHASE_SPLIT_RECOMMENDED}
**Source**: /implement-perplexity from creative-research output

### Foundation Phase (Shared Infrastructure)
> Must complete before any feature-specific work
- [ ] Task: {shared DB migration, utility, or service}
  - Files: {specific paths}
  - Branch: feature/shared-foundation
  - Est: {h}h
  - Acceptance: {specific criterion}

### Feature A: {Name}
**Branch**: feature/{kebab-case-slug}
**Depends on**: Foundation Phase
**Parallel-safe**: {YES or NO — with reason}

#### Phase 1 — {Phase Name} [{h}h]
- [ ] Task: {description}
  - Files: {specific paths to create or modify}
  - Acceptance: {specific, testable criterion}
  - Risk: {LOW or MEDIUM or HIGH — with 1-line rationale}

#### Phase 2 — {Phase Name} [{h}h]
(same structure)

### Feature B: {Name}
(same structure as Feature A)

### Integration Phase
- [ ] Integration tests across features
- [ ] E2E validation
- [ ] Git — merge feature branches to main via PR

### Orchestrator Directive
Instructions for /orchestrator-multi or /orchestrator:
- Foundation Phase completes FIRST (sequential-required)
- Sequential-required phases: {list with rationale}
- Parallel-safe phases: {list — can run simultaneously across agents}
- Go/no-go gates: {from Q3 if available}
```

**After writing the plan**, verify it via a critique-focused research_query (same pattern as /research-perplexity Step 6):

1. Build critique query with MANDATORY CONTEXT PREAMBLE + complete plan + Q1/Q2 summaries + codebase context
2. Ask Perplexity to evaluate: logical errors, missing edge cases, dependency ordering, scope creep, feasibility, risk gaps
3. Revise plan if needed (1 pass maximum)
4. THEN call ExitPlanMode for user approval

**Do NOT create tasks or execute until the user approves the plan.**

---

## Error Handling

| Failure | Action |
|---------|--------|
| Q1 fails (both attempts) | Skip shared infra detection, flag plan with MANUAL REVIEW banner |
| Q2a or Q2b fails in parallel | Retry failed query sequentially. If still fails, use blueprint-only fallback |
| Q2a fails (both parallel + sequential) | Use blueprint-only plan for that feature with RESEARCH UNAVAILABLE banner |
| Q2b fails but Q2a succeeded | Feature A fully planned, Feature B blueprint-only fallback |
| All Q2 queries fail | Fall back to procedural plan from blueprints only. Log to council-logs |
| 3+ features selected | Batch Q2 queries in pairs, run batches sequentially |
| Q3 fails (both attempts) | Skip risk synthesis, note in plan header |
| No creative-research logs found | Ask user for feature descriptions manually (fallback mode) |
| Session expired | Report: "Run /cache-perplexity-session to refresh Perplexity login session" |
| Verification query fails (Step 7) | Retry once. If still fails, note failure in plan, proceed to ExitPlanMode |

## Council Log Persistence

Save each query result to the council-logs directory:
- Q1 (Architecture Recon): `{YYYY-MM-DD_HHmm}-implement-q1-{projectName}.md`
- Q2a (Feature A Deep Dive): `{YYYY-MM-DD_HHmm}-implement-q2a-{projectName}.md`
- Q2b (Feature B Deep Dive): `{YYYY-MM-DD_HHmm}-implement-q2b-{projectName}.md` (if applicable)
- Q3 (Risk Synthesis): `{YYYY-MM-DD_HHmm}-implement-q3-{projectName}.md` (if triggered)

## Key Differences from Other Commands

| Aspect | /implement-perplexity | /research-perplexity | /creative-research |
|--------|----------------------|---------------------|-------------------|
| **Purpose** | Blueprint to validated plan | Strategic analysis | Divergent ideation |
| **Queries** | 2-4 targeted | 2 (research + verify) | 3 sequential |
| **Input** | Feature selection | Open-ended topic | Focus area |
| **Output** | Dependency-aware plan | Strategic roadmap | Ranked features + blueprints |
| **Plan mode** | Automatic after synthesis | Automatic | User-triggered |
| **Orchestrator-ready** | YES — parallel/sequential flags | NO | NO |
| **Cost** | Free | Free | Free |
