# /orchestrator-multi — Multi-Agent Parallel Orchestration

Launch N parallel Claude Code agents, each with isolated workspaces and Dropbox-safe file locking, coordinated by the multi-agent orchestrator.

## Usage
```
/orchestrator-multi <project-path> "<task-description>" [--agents N]
```

**Arguments**: `$ARGUMENTS`

## Role

You are a **multi-agent orchestrator**. You coordinate N parallel Claude Code loops — you do NOT write implementation code yourself. Your job is:

1. **Analyze** the project and split work into independent modules
2. **Create** per-agent CLAUDE.md files with scoped instructions
3. **Launch** parallel loop_driver.py processes with --agent-id
4. **Monitor** all agents via their .workflow/state.json files
5. **Merge** results when all agents complete

## Phase A: PLANNING

1. **Ensure git repo + .gitignore** — follow `/orchestrator` Step 2:
   - If `.git/` missing → `git init`
   - If `.gitignore` missing → generate from detected project type (package.json → node_modules/, pyproject.toml → __pycache__/.venv/, Cargo.toml → target/, etc. + universal patterns: .env, .DS_Store, *.log, IDE dirs) → commit .gitignore first
   - Then `git add -A && git commit -m "Initial commit"`

2. **Scaffold CLAUDE.md/BLUEPRINT.md if missing or empty** — follow `/orchestrator` Step 2.5:
   - **Content validation**: File exists is not enough — CLAUDE.md must contain `## Current Task` or `## Completion Gate`; BLUEPRINT.md must contain `## Architecture` or `## Key Components`. Empty/corrupt files → treat as missing.
   - **Empty dir fast-path**: If directory has no files beyond .git/.gitignore → skip auto-detection, go straight to interactive gap-filling ("Empty project directory — all project details needed from user.")
   - **Auto-detection**: Read metadata files (package.json, pyproject.toml, Cargo.toml, go.mod, build.gradle, Makefile, CMakeLists.txt, *.csproj, pubspec.yaml, Gemfile, composer.json, mix.exs), directory layout, git history — no source code
   - **Interactive gap-filling**: Ask user via `AskUserQuestion` for anything not detected
   - Generate lean CLAUDE.md/BLUEPRINT.md from templates, commit them
   - **IMPORTANT**: Scaffold must complete (committed) BEFORE splitting work across agents. Only one orchestrator scaffolds — never let agents scaffold in parallel.

3. **Assess maturity** — follow `/orchestrator` Step 3:
   - ≤2 commits + only scaffold files (CLAUDE.md, BLUEPRINT.md, .gitignore, README.md) → **Scaffold** tier
   - ≤2 commits + source code files present → classify using 4-tier table
   - Use maturity tier to inform work split complexity

4. Identify independent modules/directories that can be parallelized
5. Propose a work split: which files go to which agent
6. Determine how many agents to use (default: 2, max from config)
7. Write a plan summary to `.workflow/multi-agent-plan.md`

**Rules**:
- Files in the same directory should stay with the same agent
- Shared config/types files should be identified as sequential phases
- Each agent MUST have a clear, scoped CLAUDE.md

## Phase B: LAUNCHING

1. Use `MultiAgentOrchestrator.setup_workspaces()` to create `.agents/` structure
2. Each agent gets: `CLAUDE.md`, `assigned_files.txt`, `.workflow/`
3. Launch via `MultiAgentOrchestrator.launch_all()`
4. Log all PIDs and agent IDs

**Agent workspace structure**:
```
.agents/
  agent-1/
    CLAUDE.md           # Scoped instructions for this agent
    assigned_files.txt  # Files this agent owns
    .workflow/
      state.json        # Agent's loop state
      trace.jsonl       # Agent's trace events
  agent-2/
    ...
  shared/
    global_locks.json   # Cross-agent file locks
```

## Phase C: MONITORING

1. Every 30 seconds (configurable), read all agents' `.workflow/state.json`
2. Generate a dashboard table showing:
   - Agent ID, status, iteration, cost, turns, errors, files, locks
3. Watch for:
   - **Stuck agents**: same iteration for 3+ checks
   - **Budget overruns**: any agent exceeding limits
   - **Conflicts**: lock contention warnings in logs
4. Write dashboard to `.workflow/multi-agent-dashboard.md`

**Do NOT intervene in agent code** — only monitor and report.

## Phase D: MERGE

After all agents complete (or timeout):

1. Release all file locks via `LockRegistry.release_all()`
2. Run the project's test suite (`validation.test_command`)
3. Check for merge conflicts in git
4. If tests pass, create a merge commit
5. Write merge results to `.workflow/merge-results.json`

## Phase E: REPORTING

1. Aggregate costs across all agents
2. Generate per-agent summary: iterations, cost, turns, files modified
3. Write final report to `.workflow/multi-agent-report.md`
4. Clean up agent workspaces (optional, based on user preference)

## Configuration

Multi-agent settings live in `.workflow/config.json` under `multi_agent`:

```json
{
  "multi_agent": {
    "enabled": true,
    "max_agents": 4,
    "dropbox_sync_delay_seconds": 5.0,
    "lock_retry_attempts": 5,
    "lock_retry_delay_seconds": 10.0,
    "lock_ttl_seconds": 1800,
    "dashboard_refresh_seconds": 30,
    "merge_timeout_seconds": 600,
    "agent_state_dir": ".agents"
  }
}
```

## Key Constraints

- **Never modify target source code directly** — that's what agents are for
- **Never run tests yourself** — agents and merge phase handle this
- **File locks are mandatory** — the PreToolUse hook enforces them
- **Fail-open on errors** — don't let orchestration bugs block all work
- **Backward compatible** — single-loop `/orchestrator` still works unchanged
- **Scaffold before split** — git init, .gitignore, CLAUDE.md/BLUEPRINT.md must all be committed before creating agent workspaces. Never let agents scaffold in parallel (race condition).
- **Content validation over existence** — a 0-byte or section-less CLAUDE.md is treated as missing, even if the file exists on disk
