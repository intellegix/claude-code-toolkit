# /automate-perplexity — Unified Perplexity Automation

Run a Perplexity query by typing `/control` in the browser — a custom Comet command that activates browser control mode with Dropbox/GitHub context. Single entry point for all Perplexity research.

**No API keys required** — uses Perplexity login session via Chrome browser automation. $0/query.

**CRITICAL: Do NOT ask the user questions before completing Step 0 and Step 1. Compile context silently, build the query, and execute. Only ask questions if $ARGUMENTS is empty AND you cannot determine a useful research focus from the compiled context.**

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

Using the compiled context from Step 0 and Step 0.5, build the research query. Do not ask the user for clarification — use the session context to determine the best research angle.

Compose the query from session context + the user's research question:

```
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

### Step 2: Execute via browser automation

**Use `mcp__browser-bridge__*` tools ONLY.** Never use `mcp__claude-in-chrome__*` tools.

#### 2a: Get browser context

1. Call `browser_get_tabs` to see existing tabs
2. If Perplexity is already open in a tab, use `browser_switch_tab` to activate it
3. Otherwise, call `browser_navigate` to open `https://www.perplexity.ai/`
4. Call `browser_wait_for_element` with selector `textarea` (timeout 15000) to confirm the page loaded

#### 2b: Type `/control` command

1. Call `browser_execute` with action `click` on the textarea selector to focus it
2. Call `browser_cdp_type` with text `/control` and selector `textarea` — **must use CDP typing** so the slash command triggers Comet's command palette
3. Call `browser_wait_for_element` to wait for the command to activate (look for control mode indicators — command palette dropdown, mode badge, or similar UI change). Wait up to 10000ms.
4. Call `browser_press_key` with key `Enter` to confirm the `/control` command selection

#### 2c: Type the enriched query

1. Wait briefly (call `browser_press_key` with key `Space` or similar) for the input to be ready after control mode activates
2. Call `browser_cdp_type` with the enriched query text from Step 1 — use CDP typing to ensure all characters are properly input
3. Call `browser_press_key` with key `Enter` to submit the query

#### 2d: Wait for response

1. Call `browser_wait_for_stable` on the response content area (try selectors: `.prose`, `[class*="markdown"]`, `[class*="response"]`, `[class*="answer"]`) with:
   - `stableMs`: 8000 (8 seconds of no change = response complete)
   - `pollInterval`: 2000
   - `timeout`: 300000 (5 minutes max)
2. If `timedOut` is true, warn the user but still extract whatever content is available

#### 2e: Extract results

1. Call `browser_evaluate` with JavaScript to extract the response text:
   ```js
   (() => {
     const prose = document.querySelector('.prose') || document.querySelector('[class*="markdown"]') || document.querySelector('[class*="response"]');
     return prose ? prose.innerText : document.body.innerText.slice(0, 10000);
   })()
   ```
2. Store the extracted text as the research results

### Step 3: Present Results

Present key findings to the user in a concise summary. Include:
- Top 3-5 actionable recommendations
- Any blockers or risks identified
- Strategic direction highlights

### Step 4: Persist Results

- Create directory `~/.claude/council-logs/` if it doesn't exist
- Determine project name from current working directory
- Save output to `~/.claude/council-logs/{YYYY-MM-DD_HHmm}-control-{projectName}.md`

### Step 5: Enter plan mode — MANDATORY

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

#### Plan Verification — MANDATORY

After writing the complete plan but BEFORE calling `ExitPlanMode`:

1. **Build verification query**: Include the complete plan + research summary + key codebase files from Step 0.5
2. **Run verification**: Repeat Step 2 (navigate to Perplexity, type `/control`, submit a critique-focused prompt asking to evaluate: logical errors, missing edge cases, file path accuracy, dependency ordering, scope creep, feasibility)
3. **Revise plan**: If critique identifies issues, revise the plan. If APPROVED, proceed as-is.
4. **Maximum 1 verification pass** — never re-verify after revision. Call ExitPlanMode.

Write the full plan (master + all sub-plans), then call `ExitPlanMode` for user approval.

After the user approves:
- Use `TaskCreate` to create one task per Phase from the master plan
- Set dependencies with `addBlockedBy` matching the phase prerequisites
- Each task description should contain the full sub-plan for that phase
- Begin executing the first unblocked task

## Key Differences from other Perplexity commands

- Uses `/control` (custom Comet command) instead of MCP tools (`research_query`, `council_query`, `labs_query`)
- Runs in the user's live Chrome browser via `browser-bridge` — not a Playwright subprocess
- `/control` provides Dropbox/GitHub context automatically — richer context than MCP `includeContext`
- Single mode — no research/council/labs selection needed
- Same cost: $0 (uses Perplexity login session)

## Error Handling

- **Perplexity not loading**: Check network, try refreshing with `browser_navigate`
- **`/control` command not recognized**: Verify Comet extension is installed and `/control` shortcut is configured
- **Textarea not found**: Page layout may have changed — try alternative selectors (`input[type="text"]`, `[contenteditable]`, `[role="textbox"]`)
- **Response timeout**: Extract partial content and warn user
- **Session expired**: User needs to log in to Perplexity manually in Chrome

## Troubleshooting

If `/control` doesn't trigger:
1. Verify the Comet extension is active in Chrome
2. Check that the `/control` custom command is configured in Comet settings
3. Try clicking the textarea first, then typing `/control` with a small delay
4. If the command palette doesn't appear, try `browser_cdp_type` with a slower `delay` (100ms between keystrokes)
