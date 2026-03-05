#!/usr/bin/env python3
"""PreToolUse hook: Orchestrator mode path guard.

Reads tool invocation from stdin (JSON), checks for .workflow/orchestrator-mode.json
sentinel in the cwd. If sentinel is active, enforces path-based access control to
prevent the orchestrator from touching target project source code.

Fail-open: any error -> sys.exit(0) (allow operation).
No sentinel -> sys.exit(0) silently (zero overhead for normal sessions).
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path classification
# ---------------------------------------------------------------------------

ALWAYS_ALLOWED_NAMES = {
    "CLAUDE.md", "BLUEPRINT.md", "MEMORY.md", "README.md", "LICENSE",
    "package.json", "pyproject.toml", "Cargo.toml", ".gitignore",
    "requirements.txt", "setup.py", "setup.cfg", "tsconfig.json",
}

ALWAYS_ALLOWED_PATH_PARTS = {
    ".workflow", ".claude", "automated-loop", "council-automation", "automated claude",
}

DENIED_SOURCE_EXTENSIONS = {
    ".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt",
    ".c", ".cpp", ".h", ".cs", ".rb", ".php", ".swift", ".scala",
}

DENIED_SOURCE_DIRS = {
    "src", "lib", "app", "tests", "test", "__tests__", "spec",
}

DENIED_BASH_PATTERNS = [
    "pytest", "npm test", "npm run test", "cargo test", "go test",
    "jest", "vitest", "mocha", "python -m pytest",
]

ALLOWED_BASH_PATTERNS = [
    "git log", "git diff", "git status", "git show", "git branch",
    "git stash", "git add", "git commit", "git push", "git checkout",
    "git mv", "git remote", "git merge", "git worktree", "git cherry-pick",
    "python loop_driver.py", "python automated-loop",
    "sleep", "echo", "type", "dir", "ls", "cat", "head", "tail",
    "python -c", "mkdir", "mklink",
]


def read_sentinel(cwd: str) -> dict | None:
    """Read and validate the orchestrator sentinel file. Returns None if inactive."""
    sentinel_path = Path(cwd) / ".workflow" / "orchestrator-mode.json"
    if not sentinel_path.exists():
        return None

    try:
        data = json.loads(sentinel_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if not data.get("active", False):
        return None

    # Check expiration
    expires_str = data.get("expires", "")
    if expires_str:
        try:
            expires = datetime.fromisoformat(expires_str)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if now > expires:
                return None  # Expired sentinel -> treat as inactive
        except (ValueError, TypeError):
            return None  # Malformed date -> treat as inactive

    return data


def is_self_modification(sentinel: dict, target_path: str) -> bool:
    """Check if the tool targets the orchestrator's own codebase."""
    orchestrator_cwd = sentinel.get("orchestrator_cwd", "")
    if not orchestrator_cwd:
        return False

    try:
        target = Path(target_path).resolve()
        orch = Path(orchestrator_cwd).resolve()
        return target == orch or orch in target.parents
    except (ValueError, OSError):
        return False


def is_worktree_path(sentinel: dict, target_path: str) -> bool:
    """Check if the tool targets a managed worktree directory.

    In multi-agent mode, the orchestrator is allowed to write CLAUDE.md
    and .workflow/ files in agent worktrees.
    """
    worktrees = sentinel.get("worktrees", [])
    if not worktrees:
        return False

    try:
        target = Path(target_path).resolve()
        for wt in worktrees:
            wt_path = Path(wt).resolve()
            if target == wt_path or wt_path in target.parents:
                return True
    except (ValueError, OSError):
        pass
    return False


def extract_path(tool_name: str, tool_input: dict) -> str | None:
    """Extract the file/dir path from tool_input based on tool type."""
    for field in ("file_path", "path", "pattern", "notebook_path"):
        val = tool_input.get(field)
        if val and isinstance(val, str):
            return val
    return None


def is_path_allowed(file_path: str, sentinel: dict) -> tuple[bool, str]:
    """Classify a path as allowed or denied. Returns (allowed, reason)."""
    p = Path(file_path)
    name = p.name

    # Always-allowed filenames
    if name in ALWAYS_ALLOWED_NAMES:
        return True, f"allowed: {name} is an always-allowed filename"

    # All markdown files allowed
    if p.suffix == ".md":
        return True, "allowed: markdown file"

    # Always-allowed path parts
    parts_lower = {part.lower() for part in p.parts}
    for allowed_part in ALWAYS_ALLOWED_PATH_PARTS:
        if allowed_part.lower() in parts_lower:
            return True, f"allowed: path contains '{allowed_part}'"

    # Self-modification check
    if is_self_modification(sentinel, file_path):
        return True, "allowed: self-modification of orchestrator codebase"

    # Worktree CLAUDE.md / .workflow files check
    if is_worktree_path(sentinel, file_path):
        # In worktrees, only allow CLAUDE.md, .workflow/, and markdown
        if name in ALWAYS_ALLOWED_NAMES or p.suffix == ".md":
            return True, "allowed: orchestrator writing to agent worktree config"
        for part in p.parts:
            if part.lower() == ".workflow":
                return True, "allowed: orchestrator writing to agent .workflow/"
        # Deny source code in worktrees
        if p.suffix.lower() in DENIED_SOURCE_EXTENSIONS:
            return False, f"denied: source code file in worktree ({p.suffix})"

    # Denied source extensions
    if p.suffix.lower() in DENIED_SOURCE_EXTENSIONS:
        return False, f"denied: source code file ({p.suffix})"

    # Denied source directories
    for part in p.parts:
        if part.lower() in {d.lower() for d in DENIED_SOURCE_DIRS}:
            return False, f"denied: path contains source directory '{part}'"

    # Default: allow (whitelist approach for known-bad, not deny-all)
    return True, "allowed: no deny rule matched"


def is_bash_allowed(command: str, sentinel: dict) -> tuple[bool, str]:
    """Check if a bash command is allowed in orchestrator mode."""
    cmd_lower = command.strip().lower()

    # Check allowed patterns first (higher priority)
    for pattern in ALLOWED_BASH_PATTERNS:
        if cmd_lower.startswith(pattern.lower()):
            return True, f"allowed: matches allowed bash pattern '{pattern}'"

    # Check if command targets automated-loop (always allowed)
    if "automated-loop" in command or "automated claude" in command.lower():
        return True, "allowed: targets automated-loop codebase"

    # Check if command targets worktrees (allowed for git/build verification)
    if "worktree" in cmd_lower or "c:\\worktrees" in cmd_lower or "/c/worktrees" in cmd_lower:
        return True, "allowed: targets agent worktree"

    # Check denied patterns
    for pattern in DENIED_BASH_PATTERNS:
        if pattern.lower() in cmd_lower:
            return False, f"denied: matches blocked test command '{pattern}'"

    # Default: allow (fail-open for unrecognized commands)
    return True, "allowed: no deny rule matched for bash"


def main() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)

        data = json.loads(raw)
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})
        cwd = data.get("cwd", "")

        if not cwd:
            sys.exit(0)

        # Check sentinel -- no sentinel means normal mode, allow everything
        sentinel = read_sentinel(cwd)
        if sentinel is None:
            sys.exit(0)

        # Bash tool: check command
        if tool_name == "Bash":
            command = tool_input.get("command", "")
            if not command:
                sys.exit(0)
            allowed, reason = is_bash_allowed(command, sentinel)
            if not allowed:
                result = {
                    "decision": "block",
                    "reason": f"[Orchestrator Guard] {reason}. Write instructions in CLAUDE.md instead of running commands directly.",
                }
                print(json.dumps(result))
                sys.exit(1)
            sys.exit(0)

        # File tools: extract and classify path
        file_path = extract_path(tool_name, tool_input)
        if not file_path:
            sys.exit(0)  # No path to check -> allow

        allowed, reason = is_path_allowed(file_path, sentinel)
        if not allowed:
            result = {
                "decision": "block",
                "reason": f"[Orchestrator Guard] {reason}. As orchestrator, write instructions in CLAUDE.md instead of modifying source code directly.",
            }
            print(json.dumps(result))
            sys.exit(1)

        sys.exit(0)

    except Exception:
        # Fail-open: any error -> allow the operation
        sys.exit(0)


if __name__ == "__main__":
    main()
