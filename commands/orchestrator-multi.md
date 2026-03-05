# /orchestrator-multi — Multi-Agent Parallel Orchestration

**YOU ARE A MULTI-AGENT ORCHESTRATOR.** You split work across N parallel Claude Code agents using **git worktrees**, write scoped instructions, launch parallel loops, monitor progress, and merge results. You do NOT write implementation code yourself.

## Usage

```
/orchestrator-multi <project-path> "<task-description>" [--agents N]
```

**Arguments**: `$ARGUMENTS`

**Parse rules:**
- If `$ARGUMENTS` starts with a path → use that project + remaining text as task
- `--agents N` → number of parallel agents (default: 2, max: 4)
- If `$ARGUMENTS` is empty → use cwd, ask user for task

---

## Architecture: Git Worktrees (Not Subdirectories)

This orchestrator uses **git worktrees** — not `.agents/` subdirectories, not separate clones. Each agent gets a full, independent working directory that shares the same `.git` history.

**Why worktrees over clones:**
- 150MB vs 1GB+ disk usage per agent
- Shared git history enables clean merges
- Branches are visible from any worktree via `git branch`
- No need to `fetch` between agents — commits are instantly visible

**Why worktrees over subdirectories:**
- Each agent runs `make`, `npm test`, etc. independently
- No path conflicts — each agent has a real project root
- Build tools work without modification
- `.workflow/state.json` per agent without collision

---

## Phase A: PLANNING

**Metacognitive checkpoint: "I must NOT read or write target source code. I write CLAUDE.md files and launch loops."**

### Step 1: Validate Prerequisites

1. Confirm project has a git repo (`git rev-parse --git-dir`)
2. Confirm project builds from a clean state
3. Run `git status` — must be clean (no uncommitted changes)
4. Identify the base branch (usually `master` or `main`)

### Step 2: Analyze Work Split

Read the project's `CLAUDE.md`, `BLUEPRINT.md`, `README.md`, and recent git history to understand what needs to be built. Then:

1. **Identify independent modules** — directories, features, or phases that can be worked on in parallel without file conflicts
2. **Identify shared files** — headers, configs, types, schemas that multiple agents might need to modify
3. **Create a territory map** — assign each agent exclusive ownership of specific files/directories

**Territory rules:**
- Files in the same module stay with the same agent
- Shared files (headers, configs, type definitions) go on the **FORBIDDEN list** for all agents
- If an agent needs a change to a shared file, they document the need in `.workflow/shared-header-requests.md` — only the orchestrator modifies shared files
- Trainer data / append-only files: agents can ADD entries but never remove existing ones

### Step 3: Choose Worktree Location

**CRITICAL:** Worktrees must be on a path with NO SPACES.

```bash
# Good — no spaces in path
C:\worktrees\agent-1
C:\worktrees\agent-2

# BAD — spaces break GNU Make, many build tools
C:\Users\Name\My Projects\agent-1
```

If the main repo is on Dropbox, OneDrive, or a path with spaces, worktrees MUST go elsewhere (e.g., `C:\worktrees\`). Build tools like GNU Make's `realpath` function cannot handle spaces.

### Step 4: Propose Plan to User

Before creating anything, present the plan:

```
Multi-Agent Plan:
- Base branch: master
- Agents: 2
- Agent 1: [scope description] → branch: agent-1-<slug>
- Agent 2: [scope description] → branch: agent-2-<slug>
- Worktrees: C:\worktrees\agent-{1,2}
- Forbidden files: [list of shared files no agent may modify]
- Merge order: Agent 1 first, then Agent 2
- Estimated cost: ~$25-50 per agent

Proceed? [y/n]
```

Wait for user confirmation before creating branches or worktrees.

---

## Phase B: SETUP (Create Worktrees + Agent CLAUDE.md)

### Step 1: Create Agent Branches

```bash
cd <project-root>
git branch agent-1-<slug>
git branch agent-2-<slug>
# ... for each agent
```

### Step 2: Create Worktrees

```bash
mkdir -p C:\worktrees
git worktree add C:\worktrees\agent-1 agent-1-<slug>
git worktree add C:\worktrees\agent-2 agent-2-<slug>
```

### Step 3: Link Build Tools (if needed)

If the project has large tool directories that aren't tracked by git (e.g., `tools/`, `node_modules/`, `.venv/`), create NTFS junctions or symlinks:

```bash
# Windows NTFS junction (preferred — works across drives)
mklink /J "C:\worktrees\agent-1\tools" "<project-root>\tools"
mklink /J "C:\worktrees\agent-2\tools" "<project-root>\tools"
```

For projects using npm/pip, run `npm install` or `pip install -r requirements.txt` in each worktree.

### Step 4: Verify Each Worktree Builds

```bash
cd C:\worktrees\agent-1 && <build-command>
cd C:\worktrees\agent-2 && <build-command>
```

Both must succeed before launching agents.

### Step 5: Write Per-Agent CLAUDE.md

Each agent's CLAUDE.md MUST include:

```markdown
# CLAUDE.md — Agent N: <Scope Description>

## Agent Scope — STRICT

**Assigned Work:** <what this agent builds>
**Assigned Files:** <glob patterns of files this agent owns>

### FORBIDDEN FILES — DO NOT MODIFY
- <shared-file-1> — shared, orchestrator-managed
- <shared-file-2> — shared
- <glob-patterns for other agent's territory>

### ALLOWED FILES — Only modify these
- <directory-1>/ — ONLY files in assigned territory
- <directory-2>/ — ONLY files in assigned territory
- <shared-append-only-file> — ADD entries only, never remove existing

### If You Need a Change to a Shared File
1. Document the need in `.workflow/shared-header-requests.md`
2. DO NOT modify the shared file yourself
3. Use existing definitions whenever possible

## Build Commands

<project-specific build instructions>

## Phase Completion — MANDATORY

After completing each phase:
1. Build must pass
2. Update completion status below
3. Commit with message format: `feat(<scope>): Phase N complete - <description>`

- [ ] Phase N: <description>
- [ ] Phase N+1: <description>
```

**CRITICAL details to include:**
- Exact build commands (especially if they require special shells like MSYS2)
- Text encoding requirements (charmap issues, Unicode gotchas)
- Pattern references to existing code the agent should follow
- All phases with acceptance criteria

### Step 6: Create `.workflow/` in Each Worktree

```bash
mkdir -p C:\worktrees\agent-1\.workflow
mkdir -p C:\worktrees\agent-2\.workflow
```

### Step 7: Commit Setup in Each Branch

```bash
cd C:\worktrees\agent-1 && git add CLAUDE.md .workflow/ && git commit -m "docs: agent-1 setup with scoped CLAUDE.md"
cd C:\worktrees\agent-2 && git add CLAUDE.md .workflow/ && git commit -m "docs: agent-2 setup with scoped CLAUDE.md"
```

---

## Phase C: LAUNCHING (Start Parallel Loops)

### Step 1: Build Launch Commands

For each agent, construct the loop_driver.py command:

```bash
python <path-to>/loop_driver.py \
  --project "C:\worktrees\agent-N" \
  --initial-prompt "<agent-specific prompt>" \
  --model sonnet \
  --max-iterations 50 \
  --verbose \
  --skip-preflight \
  --no-stagnation-check
```

**Prompt template for each agent:**
```
Implement <assigned phases> of <project description>.
Read CLAUDE.md carefully for your scope restrictions, build instructions, and phase details.
Start with <first phase>.
Key reminders:
(1) <build command>
(2) <critical encoding/format rules>
(3) After each phase, update CLAUDE.md completion gate and commit.
```

**Flags explained:**
- `--skip-preflight` — Agent CLAUDE.md already contains all instructions
- `--no-stagnation-check` — Phases are large; prevent false stagnation triggers
- `--verbose` — Full NDJSON event logging for debugging

### Step 2: Launch All Agents

Launch each agent as a **background process** using the Bash tool with `run_in_background: true`. Record the task IDs.

```
Agent 1: task_id = <id1>
Agent 2: task_id = <id2>
```

### Step 3: Log Launch

Write to `.workflow/multi-agent-launch.json` in the main project:

```json
{
  "launched": "<ISO-8601>",
  "agents": [
    {
      "id": 1,
      "branch": "agent-1-<slug>",
      "worktree": "C:\\worktrees\\agent-1",
      "task_id": "<id1>",
      "scope": "<description>"
    },
    {
      "id": 2,
      "branch": "agent-2-<slug>",
      "worktree": "C:\\worktrees\\agent-2",
      "task_id": "<id2>",
      "scope": "<description>"
    }
  ]
}
```

---

## Phase D: MONITORING

### Monitoring Commands

Check progress periodically:

```bash
# Check for new commits
cd C:\worktrees\agent-1 && git log --oneline -5
cd C:\worktrees\agent-2 && git log --oneline -5

# Check loop state
cat C:\worktrees\agent-1\.workflow\state.json
cat C:\worktrees\agent-2\.workflow\state.json

# Check task output
# Use TaskOutput tool with block=false for non-blocking check
```

### Decision Gates

| Signal | Action |
|--------|--------|
| Agent making commits | Healthy — continue monitoring |
| Agent stuck (3+ checks, no new commits) | Read state.json, check for build errors. If stuck on build env, intervene in worktree. |
| Agent timeout (loop_driver exits) | Check iteration count. If work remains, relaunch with fresh prompt. |
| Budget exceeded | Report cost, ask user to increase or stop |
| Agent modifying forbidden files | Should not happen (CLAUDE.md prohibits it). If it does, `git checkout -- <file>` to revert. |
| Shared header request | Read `.workflow/shared-header-requests.md`, apply change to main branch, cherry-pick into agent branches. |

### Handling Shared Header Requests

If an agent documents a need in `.workflow/shared-header-requests.md`:

1. Read the request
2. Apply the change on the main branch (e.g., add new flag/constant)
3. Commit on main
4. Cherry-pick into BOTH agent branches:
   ```bash
   cd C:\worktrees\agent-1 && git cherry-pick <sha>
   cd C:\worktrees\agent-2 && git cherry-pick <sha>
   ```
5. Agents will pick up the new definitions on their next iteration

---

## Phase E: MERGE

**Merge order matters.** Merge the agent whose work is most foundational first.

### Step 1: Verify Agent Completion

```bash
cd C:\worktrees\agent-1 && git log --oneline <base-branch>..HEAD
cd C:\worktrees\agent-2 && git log --oneline <base-branch>..HEAD
```

Review each agent's commits. Check that CLAUDE.md completion gates are marked done.

### Step 2: Merge Agent 1 into Base

```bash
cd <project-root>
git merge --no-ff agent-1-<slug> -m "merge: Agent 1 <scope>"
```

### Step 3: Merge Agent 2

```bash
git merge --no-ff agent-2-<slug> -m "merge: Agent 2 <scope>"
```

### Step 4: Resolve Conflicts

**Expected conflict patterns:**
- **Append-only files** (trainers.json, package.json dependencies): Append Agent 2's additions after Agent 1's
- **Constant/enum headers** (trainers.h, constants.ts): Append Agent 2's constants after Agent 1's
- **No other conflicts expected** if territory was properly scoped

### Step 5: Verify Combined Build

```bash
cd <project-root>
<clean-command>
<build-command>
```

### Step 6: Clean Up

```bash
git worktree remove C:\worktrees\agent-1
git worktree remove C:\worktrees\agent-2
git branch -d agent-1-<slug>
git branch -d agent-2-<slug>
```

---

## Phase F: REPORTING

Report to user:
1. **Per-agent summary**: Phases completed, commits, cost, iterations
2. **Merge result**: Clean or conflicts resolved
3. **Build status**: Pass/fail after merge
4. **Remaining work**: Any phases not completed
5. **Suggestions**: Next steps, `/research-perplexity` for strategic analysis

---

## Configuration

Multi-agent settings in `.workflow/config.json`:

```json
{
  "multi_agent": {
    "max_agents": 4,
    "worktree_base": "C:\\worktrees",
    "model": "sonnet",
    "max_iterations_per_agent": 50,
    "max_cost_per_agent": 25.0,
    "merge_order": "sequential",
    "skip_preflight": true,
    "no_stagnation_check": true
  }
}
```

---

## Key Constraints

- **Never modify target source code directly** — agents do that
- **Never run tests yourself** — agents handle testing
- **Territory is sacred** — agents MUST NOT touch each other's files
- **Shared files are orchestrator-managed** — only you modify shared headers/configs
- **Worktree paths must have no spaces** — GNU Make, many build tools break on spaces
- **Merge order is sequential** — never merge simultaneously
- **Scaffold before split** — project must build clean before creating worktrees
- **Cherry-pick shared changes** — when you update shared files, cherry-pick into ALL agent branches
- **Fail-open on monitoring errors** — don't block agents if monitoring has issues

---

## Comparison: Single vs Multi Agent

| Aspect | `/orchestrator` | `/orchestrator-multi` |
|--------|-----------------|----------------------|
| Agents | 1 | 2-4 |
| Isolation | Same directory | Git worktrees |
| Concurrency | Sequential | Parallel |
| File conflicts | N/A | Prevented by territory |
| Shared files | Agent modifies freely | Orchestrator-managed |
| Merge | N/A | Sequential `--no-ff` |
| Cost | ~$25 | ~$25-50 per agent |
| Best for | Single feature/task | Large multi-phase projects |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Worktree creation fails | Ensure base branch has no uncommitted changes; check disk space |
| Agent can't build | Verify tool symlinks/junctions; check env vars in worktree shell |
| Agent modifies forbidden file | `git checkout -- <file>` in worktree; add stronger warning to CLAUDE.md |
| Merge conflict on append-only file | Open file, keep both agent's additions, re-sort if needed |
| Agent times out repeatedly | Increase `--timeout`; check if build environment requires special shell (MSYS2, WSL) |
| Dropbox/OneDrive interferes | Worktrees MUST be outside synced folders (use `C:\worktrees\`) |
| Build tools fail on spaces in path | Worktrees MUST be on space-free paths |
| Agent needs new shared constant | Agent writes to `.workflow/shared-header-requests.md`; orchestrator cherry-picks |
