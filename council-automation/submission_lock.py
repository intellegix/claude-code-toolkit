"""Cross-process advisory lock for the Perplexity submit critical section.

Two Claude Code sessions running /research-perplexity simultaneously can race
on the Windows OS-level keyboard focus during slash-command typing. The
second Chrome launch can call SetForegroundWindow / BringWindowToTop mid-
keystroke on the first session, sending keys to the wrong target and
silently submitting the query in Search mode instead of Research mode.
Empty .prose -> server.js retry-once -> new subprocess -> new Chrome
window. User sees "browsers canceling each other and trying."

The fix is a cross-process file lock around the focus-sensitive submit
window (input focus click + slash-command type + Space commit + verify
+ query submission + first streaming token observed). Hold time is
typically 10-25s; browser launch and synthesis collection remain fully
parallel.

Usage (sync):
    with get_submit_lock():
        ...focus-sensitive work...

Usage (async, blocking event loop is unacceptable):
    lock = get_submit_lock()
    await asyncio.to_thread(lock.acquire)
    try:
        ...focus-sensitive work...
    finally:
        lock.release()

Stale-lock reclaim: if a process is SIGKILL'd before its __exit__ runs,
the lock file persists with the old PID. The 180s mtime check is the
only escape hatch -- any caller that finds a lock older than that
unlinks it before attempting acquire.
"""
from __future__ import annotations

import time
from pathlib import Path

from filelock import FileLock

# Co-located with the SessionSemaphore so cleanup paths see them together.
# Dotfile prefix prevents accidental matching by SessionSemaphore's
# slot-*.lock glob (verified -- different prefix family).
LOCK_PATH = (
    Path.home()
    / ".claude"
    / "config"
    / "browser-sessions"
    / ".perplexity_submit.lock"
)
STALE_AGE_S = 180  # crashed-holder lock left this long -> reclaim


def get_submit_lock(timeout: float | None = None) -> FileLock:
    """Return a FileLock for the Perplexity submit critical section.

    Timeout scales with MAX_CONCURRENT_SESSIONS so the Nth caller has
    time to drain the queue ahead of it. Floor 120s for single-session
    use; scales up to ~240s at full saturation (MAX_CONCURRENT_SESSIONS=8
    sessions x ~30s each = ~240s worst-case wait at the tail).
    """
    if timeout is None:
        # Lazy import to avoid a circular dep with council_config and
        # to keep this module importable from anywhere.
        try:
            from council_config import MAX_CONCURRENT_SESSIONS
            timeout = max(120.0, float(MAX_CONCURRENT_SESSIONS) * 30.0)
        except ImportError:
            timeout = 240.0  # safe floor without config

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Reclaim a stale lock from a crashed holder. This runs BEFORE
    # FileLock.acquire() so even if filelock's internal acquire would
    # block forever on a wedged file, we get an escape hatch.
    try:
        if LOCK_PATH.exists():
            age = time.time() - LOCK_PATH.stat().st_mtime
            if age > STALE_AGE_S:
                try:
                    LOCK_PATH.unlink()
                except OSError:
                    pass
    except OSError:
        pass

    return FileLock(str(LOCK_PATH), timeout=timeout)
