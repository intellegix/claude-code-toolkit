# /research-perplexity — Deep Research via Perplexity

Run a deep research query using Perplexity's `/research` mode via Playwright browser automation. This is an alternative to `/export-to-council` that uses Perplexity's dedicated research mode instead of multi-model council.

**No API keys required** — uses Perplexity login session only. Good fallback when council mode defaults to single-model.

**CRITICAL — TWO-PASS VERIFICATION IS MANDATORY EVERY INVOCATION. After receiving Perplexity results and synthesizing a plan (Step 5), you MUST send that plan back to Perplexity for critique (Step 6) BEFORE calling ExitPlanMode. NEVER call ExitPlanMode without completing Step 6. Skipping verification is a protocol violation. This applies regardless of plan size, complexity, or apparent correctness. NO EXCEPTIONS.**

**CRITICAL: Do NOT ask the user questions before completing Step 0 and Step 1. Compile context silently, build the query, and execute. Only ask questions if $ARGUMENTS is empty AND you cannot determine a useful research focus from the compiled context.**

**MANDATORY CONTEXT PREAMBLE — EVERY QUERY, NO EXCEPTIONS:** Every single query sent to Perplexity (Step 2 AND Step 6.3) MUST begin with the following preamble block. This is a hard rule — never omit it, never paraphrase it, never move it to a footnote. It goes at the TOP of every query, before any other content:

```
[ENVIRONMENT CONTEXT — READ FIRST]
This project is being developed using Claude Code, Anthropic's official CLI tool for Claude (claude.ai/claude-code). The developer uses a Claude Max subscription and works entirely in the terminal via the `claude` CLI command. Claude Code is an agentic coding assistant that reads/writes files, runs terminal commands, searches codebases, and executes multi-step development tasks autonomously. All code generation, refactoring, debugging, and project management happens through Claude Code's conversation interface — there is no IDE or GUI involved. Responses should account for this workflow: recommend CLI-compatible tools, terminal-based solutions, and approaches that work well with an AI coding agent operating in a command-line environment.
[END ENVIRONMENT CONTEXT]
```

## Input

`$ARGUMENTS` = The research question or topic to investigate. If empty, defaults to a general project analysis.

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
4. **Synthesize**: Form internal "codebase summary" — key files, purposes, connections

Do NOT present findings. Do NOT ask questions. Include this context when building the query in Step 1.

### Step 1: Build the research query

Using the compiled context from Step 0, build the research query. Do not ask the user for clarification — use the session context to determine the best research angle.

Compose the query from session context + the user's research question. **Start with the MANDATORY CONTEXT PREAMBLE** defined above, then append:

```
[ENVIRONMENT CONTEXT — READ FIRST]
This project is being developed using Claude Code, Anthropic's official CLI tool for Claude (claude.ai/claude-code). The developer uses a Claude Max subscription and works entirely in the terminal via the `claude` CLI command. Claude Code is an agentic coding assistant that reads/writes files, runs terminal commands, searches codebases, and executes multi-step development tasks autonomously. All code generation, refactoring, debugging, and project management happens through Claude Code's conversation interface — there is no IDE or GUI involved. Responses should account for this workflow: recommend CLI-compatible tools, terminal-based solutions, and approaches that work well with an AI coding agent operating in a command-line environment.
[END ENVIRONMENT CONTEXT]

You are a development strategy advisor analyzing a coding session. Given the project context (provided as system context), provide strategic analysis and concrete next steps.

FOCUS AREA: {$ARGUMENTS or "general next steps — what should be the priority?"}

Please analyze and respond with:
1. CURRENT STATE: What has been accomplished based on the project context
2. PROGRESS VS PLAN: How does the work align with the project's implementation plan?
3. IMMEDIATE NEXT STEPS: 3-5 concrete actions in priority order, with specific file paths and code changes
4. BLOCKERS: Any issues that need resolution before proceeding
5. TECHNICAL DEBT: Items that should be addressed soon
6. STRATEGIC RECOMMENDATIONS: Longer-term suggestions for the project direction
7. RISKS: What could go wrong with the recommended path, and mitigations
8. CODEBASE FIT: How do recommendations integrate with existing code structure?
```

### Step 1.5: Close Browser Bridge Sessions — MANDATORY

**Before launching any Playwright-based query**, close active browser-bridge sessions to prevent DevTools Protocol collisions:

1. Call `mcp__browser-bridge__browser_close_session` to release all browser-bridge tab connections
2. Wait 2 seconds (`sleep 2` via Bash) for Chrome DevTools to fully detach
3. Then proceed to Step 2

**Why:** The `research_query` tool launches Playwright (separate Chromium instance). If `browser-bridge` has active Chrome DevTools connections, the two systems can collide — causing tab detachment errors, empty results, and `"Debugger is not attached"` failures. Closing browser-bridge first prevents this.

**After Step 3 (Read results):** Browser-bridge connections can be re-established by calling any `browser-bridge` tool — no explicit reconnect needed.

### Step 2: Run research query

Call `research_query` MCP tool with:
- `query`: The prompt from Step 1
- `includeContext`: `true` (auto-extracts git log, CLAUDE.md, MEMORY.md)

This runs Playwright browser automation with Perplexity's `/research` mode — a single deep research thread (not multi-model council). Results are cached to `~/.claude/council-cache/council_latest.json`.

### Step 3: Read results

The `research_query` response contains the Perplexity synthesis. Present the key findings to the user in a concise summary.

### Step 4: Persist results

- Save output to `~/.claude/council-logs/{YYYY-MM-DD_HHmm}-research-{projectName}.md`

### Step 5: Synthesize Plan — MANDATORY

**IMMEDIATELY after receiving the research results, you MUST enter plan mode using the `EnterPlanMode` tool.** Do not ask the user, do not present the research first, do not do anything else — go straight into plan mode.

**CRITICAL: Do NOT ask the user which priorities to tackle. Cover ALL priorities from the research. Never filter, skip, or ask for selection — build the complete plan automatically.**

In plan mode, create a **two-tier plan structure** (master plan + sub-plans):

#### Tier 1: Master Plan (the blueprint)

1. Read relevant project files identified in the research findings
2. Cross-reference ALL recommendations against the current codebase
3. List every priority as a numbered **Phase** in execution order:
   - Phase ordering: blockers first, then dependencies, then independent work, then polish
   - Each Phase gets: title, 1-line goal, estimated complexity (S/M/L), prerequisite phases
   - Group related priorities into the same phase when they touch the same files
4. The master plan should read like a table of contents with dependency arrows between phases

#### Tier 2: Sub-Plans (the details)

For each Phase in the master plan, write a detailed sub-plan:
   - Specific files to create/modify (with paths)
   - Code changes needed (describe the what, not line-by-line diffs)
   - Acceptance criteria — how to verify this phase is done
   - Risk mitigations from the research findings
   - Dependencies on other phases (what must be done first)

#### Required final sections (in every plan):

- **Second-to-last phase: Update project memory** — follow these 6 rules:
  1. MEMORY.md stays under 150 lines — move implementation details to `memory/*.md` topic files
  2. No duplication between MEMORY.md and CLAUDE.md — if it's a behavioral rule, it belongs in CLAUDE.md only
  3. New session-learned patterns (bugs, gotchas, workarounds) go in MEMORY.md; implementation details go to topic files
  4. Delete outdated entries rather than accumulating — check if existing content is superseded
  5. If adding a new topic file, add a 1-line entry to the Topic File Index in MEMORY.md
  6. Topic file naming: kebab-case.md
- **Final phase: Commit & Push** — commit all changes and push to remote

Write the full plan (master + all sub-plans), then proceed to **Step 6** — do NOT call `ExitPlanMode` yet.

### Step 6: Verify Plan via Second Perplexity Pass — MANDATORY, NO EXCEPTIONS

**This step is the hard gate before `ExitPlanMode`. NEVER skip it. NEVER call `ExitPlanMode` without completing this step. Skipping verification is a protocol violation — it applies regardless of plan size, complexity, or apparent correctness.**

#### 6.1: Close Browser Bridge Sessions

Same as Step 1.5 — close active browser-bridge sessions before launching Playwright:

1. Call `mcp__browser-bridge__browser_close_session`
2. Wait 2 seconds (`sleep 2` via Bash)

#### 6.2: Build the Verification Query

Construct a critique-focused query containing:

- **The complete plan text** (master plan + all sub-plans from Step 5)
- **Research summary** (key findings from Step 3)
- **Key codebase context** (file snippets from Step 0.5)

Format the query as (**start with the MANDATORY CONTEXT PREAMBLE**, then the critique prompt):

```
[ENVIRONMENT CONTEXT — READ FIRST]
This project is being developed using Claude Code, Anthropic's official CLI tool for Claude (claude.ai/claude-code). The developer uses a Claude Max subscription and works entirely in the terminal via the `claude` CLI command. Claude Code is an agentic coding assistant that reads/writes files, runs terminal commands, searches codebases, and executes multi-step development tasks autonomously. All code generation, refactoring, debugging, and project management happens through Claude Code's conversation interface — there is no IDE or GUI involved. Responses should account for this workflow: recommend CLI-compatible tools, terminal-based solutions, and approaches that work well with an AI coding agent operating in a command-line environment.
[END ENVIRONMENT CONTEXT]

You are a senior software architect reviewing an implementation plan. Critically evaluate this plan for correctness, completeness, and feasibility.

## Plan to Review
{complete plan text from Step 5}

## Research Context
{summary of findings from Step 3}

## Codebase Context
{key file snippets and structure from Step 0.5}

Please evaluate:
1. LOGICAL ERRORS: Are there contradictions, circular dependencies, or impossible sequences?
2. MISSING EDGE CASES: What scenarios does the plan fail to address?
3. FILE PATH ACCURACY: Do referenced files/paths actually exist in the codebase?
4. DEPENDENCY ORDERING: Are phases ordered correctly given their prerequisites?
5. SCOPE CREEP: Does the plan include unnecessary work beyond what was researched?
6. FEASIBILITY: Are estimated complexities realistic? Are there hidden costs?
7. RISK GAPS: What risks are unmitigated?
8. VERDICT: APPROVED (proceed as-is) or REVISE (with specific changes needed)
```

#### 6.3: Run Verification

Call `research_query` MCP tool with:
- `query`: The critique prompt from 6.2
- `includeContext`: `true`

#### 6.4: Revise Plan (if needed)

- If the critique identifies issues: revise the plan accordingly. **Maximum 1 revision pass** — do not re-verify after revision.
- If the critique returns APPROVED: proceed as-is.

#### 6.5: Exit Plan Mode

**Only after completing 6.1–6.4**, call `ExitPlanMode` for user approval.

#### Error Handling for Step 6

If `research_query` fails in Step 6:
1. Close browser-bridge sessions (`browser_close_session`)
2. Wait 30 seconds for process cleanup
3. Retry once
4. If the retry also fails: note the failure reason in the plan file, then proceed to `ExitPlanMode` — but the attempt MUST be made

### Step 7: Post-Approval Execution

After the user approves the plan:
- Use `TaskCreate` to create one task per Phase from the master plan
- Set dependencies with `addBlockedBy` matching the phase prerequisites
- Each task description should contain the full sub-plan for that phase
- Begin executing the first unblocked task

## Key Differences from /export-to-council
- Uses Perplexity `/research` mode instead of `/council` (multi-model)
- Always runs via browser (Playwright) — no API mode
- Better for deep, focused research on a single topic
- Good fallback when council mode uses single-model anyway
- Same cost: $0 (uses Perplexity login session)

## Error Handling
- **Session expired**: Report "run python council_browser.py --save-session to refresh"
- **Research mode not available**: Falls back to regular Perplexity query
- **Browser collision / empty results**: If `research_query` returns empty synthesis, the most likely cause is browser-bridge DevTools collision. Close browser-bridge sessions (`browser_close_session`), wait 2 seconds, and retry once. If still empty, report "Perplexity session may be expired — run `/cache-perplexity-session` to refresh."
