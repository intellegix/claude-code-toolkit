# Global CLAUDE.md v3.0 — Compact
# <Your Name> | <Your Org> | Patterns: ~/.claude/patterns/

## Identity
- <Your Name> | <Role>
- <Organization> (<Description>)
- <City, State> | <Timezone>

## Tech Stack
- Python (70%), TypeScript (25%), Kotlin (5%)
- Backend: FastAPI, Flask, Node.js | Frontend: React, Next.js, TailwindCSS
- AI/ML: Claude API, Perplexity, Ollama | DB: PostgreSQL, SQLite, Redis

## Commands
`/research`, `/smart-plan`, `/fix-issue`, `/implement`, `/implement-perplexity`, `/review`, `/handoff`, `/mcp-setup`, `/browser-test`, `/mcp-deploy`, `/council-refine`, `/export-to-council`, `/council-extract`, `/cache-perplexity-session`, `/portfolio-status`, `/frontend-e2e`, `/solve-perplexity`, `/session-audit`, `/raken-perplexity`, `/raken-api` (Defined in `~/.claude/commands/*.md`)

## Models
opus (complex arch) | sonnet (code) | haiku (quick) | sonnet+web (research)

## Date/Time Awareness (MANDATORY)
- **Hooks auto-inject**: `[TIME SYNC]` messages appear on every session start AND before every prompt via `UserPromptSubmit` hook — these are authoritative, always use the most recent one
- **Never guess dates**: If no `[TIME SYNC]` is visible in context, run `python -c "from datetime import datetime; print(datetime.now().strftime('%Y-%m-%d %H:%M:%S %A'))"` before any time-sensitive work
- **Time-sensitive operations**: Creating dated files, scheduling, commits, reports — always reference the latest `[TIME SYNC]` timestamp
- **After compaction**: SessionStart hook re-injects time automatically, but verify with a Bash command if doing date-dependent work
- **File naming**: Use ISO 8601 format (YYYY-MM-DD) for sortability in all generated filenames

## Response Style
- Be direct and technical - skip preambles
- Show code first, explain after
- State assumptions explicitly when uncertain
- Don't ask for confirmation - just do it, then summarize

## Code Standards

### Python (Primary)
- Type hints on ALL functions: `def process(data: dict) -> Result[T]:`
- Async/await for I/O: `async def fetch(url: str) -> dict:`
- Pydantic for validation, logging over print, Result pattern for errors
- See `patterns/PYTHON_PATTERNS.md`

### TypeScript
- ES modules only, explicit return types on exports
- React Query for server state, Zustand for client, Zod for validation
- See `patterns/TYPESCRIPT_PATTERNS.md`

### Naming
Py: snake_case vars/funcs, PascalCase classes, SCREAMING_SNAKE consts, snake_case.py files
TS: camelCase vars/funcs, PascalCase classes, SCREAMING_SNAKE consts, kebab-case.ts files

## Pattern References
Error handling: `patterns/PYTHON_PATTERNS.md#result-pattern`; Validation: `patterns/PYTHON_PATTERNS.md#pydantic-validation`; API: `patterns/API_PATTERNS.md`; Testing: `patterns/TESTING_PATTERNS.md`; Security: `patterns/SECURITY_CHECKLIST.md`; MCP: `patterns/MCP_PATTERNS.md`; Browser: `patterns/BROWSER_AUTOMATION_PATTERNS.md`

## Security
- Load credentials from environment: `API_KEY = os.environ["API_KEY"]` — never hardcode; use pydantic-settings or python-dotenv
- Validate ALL external input with Pydantic/Zod; parameterized queries only — never concatenate user input into SQL
- Never log passwords, tokens, PII, or API keys; audit log all mutations with user_id + timestamp
- Full checklist: `patterns/SECURITY_CHECKLIST.md`

## Git Workflow
- Branches: `feature/IGX-123-desc` | `bugfix/ASR-456-fix` | `hotfix/critical-patch`
- Commits: `feat(scope): add feature` | `fix(scope): resolve bug` | `refactor(scope): improve code`
- Pre-commit: type check (`mypy src/` or `npm run type-check`); run affected tests; no hardcoded secrets; new env vars in `.env.example`

### GitHub Merge Protocol (MANDATORY)
Protected branches (`master`, `main`) require PRs. **Never merge directly.** Always:
1. Create PR via `gh pr create`
2. Wait for CI: `gh pr checks <number>` — ALL checks must pass (green)
3. If a check fails, investigate and fix (re-run if transient, fix code if real)
4. Only after all checks pass: `gh pr merge <number> --merge`
5. Never use `--admin` to bypass failed checks unless explicitly instructed

## Agent Behavior
- Before changes: read files first, understand context; Bugs: failing test first; Features: types/interfaces first; Refactors: tests pass before AND after
- Code gen: complete working code (no TODOs), all imports, follow codebase patterns, docstrings on public funcs
- Verify after changes: type-check; run affected tests; check circular deps if new imports

### Failure Escalation via Research (MANDATORY — FIRST UNCLEAR FAILURE TRIGGERS RESEARCH)
**After the first fix attempt fails and the root cause is NOT obvious from the error message + stack trace + diff, IMMEDIATELY escalate to `/research-perplexity`.** Do not retry with variations. Do not debug in circles. Unclear failure = research mode. $0 cost, ~90s — prevents 10K+ token debugging spirals.

**Escalation ladder (execute in order):**
1. **Tier 0 — Self-check** (0s): Read the error. If the fix is mechanically obvious from the message alone (wrong arg, missing import, syntax error), fix it. No escalation needed.
2. **Tier 1 — Memory check** (5s): Search project MEMORY.md and global MEMORY.md for the error signature. If a prior research fix exists, apply it directly. No escalation needed.
3. **Tier 2 — Research** (90s): If Tier 0 and Tier 1 don't resolve it, invoke `/research-perplexity` with the structured query below.
4. **Tier 2.5 — Iterative solver** (2-10 min): If Tier 2 returns low-confidence or contradictory results, or the problem requires multiple angles of investigation, invoke `/solve-perplexity`. Progressive research->labs iterations with contradiction tracking. $0 cost.
5. **Tier 3 — User handoff**: If research fix also fails, present a **structured decision request** (not a status dump):
   - **Problem**: One-sentence description
   - **Error**: Key error line (not full trace)
   - **Tried**: Fix attempts (manual + research-recommended)
   - **Research said**: Core finding from Perplexity
   - **Options**: 2-3 concrete next steps for user to choose from

**Tier 2 research query template:**
```
DEBUGGING ESCALATION — failure persists after Tier 0/1 self-check.
FAILURE: {what failed — build, test, runtime, integration}
ERROR: {key error lines, not full trace}
ATTEMPTED FIX: {what was tried and why it was expected to work}
CODE CONTEXT: {relevant file(s) only — scoped git diff, not full diff}
ENVIRONMENT: {language version, framework version, OS, platform}
DEPENDENCY CHANGES: {recent package.json/requirements.txt diff if relevant}
DETERMINISTIC: {yes/no — does it fail every time or intermittently?}
REQUEST: (1) Root cause analysis (2) Correct fix with code (3) Verification steps
```

**Memory write-back (MANDATORY after successful research fix):**
After any Tier 2 research fix succeeds, write to project MEMORY.md:
`## Research Fix: {error signature} ({date})` + root cause + fix applied + prevention note.
This feeds Tier 1 so the same error never triggers research twice.

**Escape hatches (escalation NOT required):**
- Error cause is mechanically obvious (Tier 0 resolves it)
- Known fix exists in MEMORY.md (Tier 1 resolves it)
- User provides the exact fix directly
- Test flake confirmed by successful re-run
- Stale environment state (cache, node_modules, .next, port conflict) — clean and retry first
- Error is in auto-generated, vendored, or external code not under project control

### Planning Discipline (MANDATORY — STAY IN PLAN MODE)
For non-trivial tasks (3+ files, new features, refactors, bug investigations): ALWAYS enter
plan mode first. Once in plan mode, STAY there — do NOT exit early, skip verification, or
start implementing before the plan is fully verified and user-approved. The full plan mode
workflow is: explore → design → write plan → verify via `/research-perplexity` → revise →
ExitPlanMode → wait for user approval → THEN implement. No shortcuts.

**Escape hatches (plan mode NOT required):**
- Single-file fix with user-specified exact change ("change X to Y")
- Emergency hotfix (user says "emergency", "hotfix", or "just do it")
- Pipeline-internal fix loops (e.g., /gba-build-develop Stage 4 — pipeline controls its own gates)

After implementation, run `/export-to-council` for feedback. For plans >1hr, run `/council-refine` first.

### Codebase Exploration Before Research (MANDATORY)
Before running any research/council/labs query, ALWAYS explore the codebase first: read key
source files (recently modified + structural files) to provide concrete code context. Never
send a research query with only metadata (git log, CLAUDE.md excerpts) — include actual code.

### Plan Verification via /research-perplexity (MANDATORY — EVERY PLAN, NO EXCEPTIONS)
When in plan mode, BEFORE calling ExitPlanMode to ask the user for plan approval, ALWAYS run
`/research-perplexity` to verify the plan. This applies to EVERY plan — regardless of how it
was created (user request, research, brainstorming, bug fix, feature, refactor, any task) and
regardless of which project or directory you are in. No exceptions. No skipping.

**Workflow:**
1. Write the complete plan to the plan file
2. Invoke `/research-perplexity` with the plan + relevant codebase context for critique
3. Revise the plan based on research feedback (1 pass maximum)
4. THEN call ExitPlanMode

Send the plan text, relevant code snippets, and project context to Perplexity. Ask it to:
- Identify flaws, gaps, or risks in the plan
- Suggest improvements or alternatives you missed
- Validate technical assumptions

If `/research-perplexity` fails, retry once. If the retry also fails, note the failure reason in the plan file and proceed to ExitPlanMode — but the attempt MUST be made.

### Post-Plan Completion (MANDATORY)
After completing any plan (all steps done, committed): **always suggest** running `/research-perplexity` to get strategic analysis on next steps. Present it as: "Plan complete. Suggest running `/research-perplexity` for strategic next steps — want me to proceed?" This applies to every plan, not just major ones.

### Post-Implementation Council Review
After major implementation: run `/export-to-council` → synthesize into MEMORY.md → create follow-up tasks.

### Perplexity Session Caching
Run `/cache-perplexity-session` after Perplexity login. Cached to `~/.claude/config/perplexity-session.json` (24h TTL). Auto-used by council commands; falls back to UI clicks if expired.

### Browser Automation (MANDATORY — STRICT)
**ONLY use `mcp__browser-bridge__*` tools for ALL browser interactions. NEVER use `mcp__claude-in-chrome__*` tools — they are FORBIDDEN.** Even if `claude-in-chrome` tools are available in the tool list, ALWAYS ignore them and use `browser-bridge` exclusively. This is a hard rule with zero exceptions.
Tools: `browser_navigate`, `browser_execute`, `browser_screenshot`, `browser_get_context`, `browser_get_tabs`, `browser_switch_tab`, `browser_wait_for_element`, `browser_fill_form`, `browser_extract_data`, `browser_scroll`, `browser_select`, `browser_close_session`, `browser_insert_text`, `browser_cdp_type`, `browser_press_key`, `browser_evaluate`, `browser_console_messages`, `browser_wait_for_stable`
Rules: Start with `browser_get_tabs`; sessions get own tab group; ALWAYS call `browser_close_session` when done; screenshots: no params=viewport, `selector`=element, `fullPage`=page, `savePath`=disk; if not connected, tell user to check extension.

## Portfolio Governance (MANDATORY)

### Before ANY Work
Read `~/.claude/portfolio/PORTFOLIO.md` for project tier, phase, and constraints.
Respect the project's "DO NOT" list. Phase restrictions are hard limits, not suggestions.

### Complexity Budget by Tier
| Tier | Tests | CI | Monitoring | Docs |
|------|-------|----|------------|------|
| T1 Maintenance | Existing only | Existing only | Existing only | CLAUDE.md + README |
| T2 Development | Unit tests | Optional | None | CLAUDE.md + README |
| T3 Experimental | None | None | None | CLAUDE.md only |
| T4 Archive | None | None | None | None |

### Velocity Rules
- MAX 2 active feature branches across all projects
- Prototype phase = working code only, no infrastructure
- If a feature takes >4h estimate, break it down or question scope
- Default to the SIMPLEST solution that works for the user count

## Add-ons

<!-- Add-ons are domain-specific context modules you can activate per-project.
     Each add-on provides Claude with industry knowledge, API patterns, and
     domain-specific rules. Copy relevant add-ons to your project's CLAUDE.md. -->

**MULTI_AGENT** (Claude Orchestration): Orchestrator(Opus)->Research/Backend/Frontend/Test(Sonnet) | Agent types: Orchestrator, Research, Architect, Frontend, Backend, Database, DevOps, Testing | Handoff: `.claude/handoffs/[timestamp]-[task].md`

**MCP_BROWSER_AUTOMATION** (Browser Extension, MCP Protocol): MCP Server<->WS Bridge<->Chrome Ext<->DOM | <2.2s exec, 40% productivity boost, 80% test reduction | See `patterns/MCP_PATTERNS.md`, `patterns/BROWSER_AUTOMATION_PATTERNS.md`, `patterns/SECURITY_MCP.md` | Full plan: `~/.claude/plans/mcp-master-plan.md`

<!-- Add your own domain add-ons here. Format:
     **ADDON_NAME** (Projects): key tools/APIs | domain concepts | constraints -->

## Hooks
Auto-format on save: Python (`black`+`isort`), TS/JS (`eslint --fix`), JSON/YAML/MD (`prettier --write`). Configure in `~/.claude/settings.json`.
Activate add-ons in projects: reference `~/.claude/CLAUDE.md` add-on section, or copy to project CLAUDE.md.

## Troubleshooting
**Failure → escalation ladder** (see "Failure Escalation via Research" in Agent Behavior): Tier 0 self-check → Tier 1 memory → Tier 2 `/research-perplexity` → Tier 2.5 `/solve-perplexity` → Tier 3 user handoff.

Quick checks (Tier 0): Python: `mypy src/` | `pip install -r requirements.txt --force-reinstall` | TS: `rm -rf node_modules/.cache && npm run build` | DB: `psql $DATABASE_URL -c "SELECT 1"` | Integrations: check OAuth expiry, rate limits, webhook delivery

If quick checks don't resolve on first attempt and root cause is unclear, escalate to Tier 2 research immediately.

## API Keys (Global)
Source: Environment variables (see `.env.example` for required keys)
Load from environment variables — never hardcode.
Keys: Claude (`ANTHROPIC_API_KEY`), Perplexity (`PERPLEXITY_API_KEY`), GitHub (use `gh auth login`)
