"""Test parallel Playwright instance isolation & scaling.

Exercises:
  1. Concurrent semaphore slot acquisition (multiprocessing)
  2. Stale slot cleanup
  3. Concurrent browser launches with fingerprint verification
"""

import asyncio
import json
import multiprocessing
import os
import sys
import tempfile
import time
from pathlib import Path

# Ensure council-automation is on path
sys.path.insert(0, str(Path(__file__).parent))

from council_browser import SessionSemaphore, PerplexityCouncil, BrowserBusyError
from council_config import MAX_CONCURRENT_SESSIONS, INSTANCE_GPU_CUTOFF


def _worker_acquire(sessions_dir: str, worker_id: int, result_dict: dict, barrier) -> None:
    """Worker process: acquire a semaphore slot, report it, wait, release."""
    sem = SessionSemaphore(sessions_dir=Path(sessions_dir))
    try:
        slot = sem.acquire(wait_timeout=10)
        result_dict[worker_id] = {"slot": slot, "pid": os.getpid(), "error": None}
        # Wait at barrier so all workers hold slots simultaneously
        barrier.wait(timeout=15)
        time.sleep(0.5)
    except BrowserBusyError as e:
        result_dict[worker_id] = {"slot": -1, "pid": os.getpid(), "error": str(e)}
    except Exception as e:
        result_dict[worker_id] = {"slot": -1, "pid": os.getpid(), "error": str(e)}
    finally:
        sem.release()


def test_concurrent_semaphore(n_workers: int = 5) -> bool:
    """Test that N concurrent workers get unique slot IDs."""
    print(f"\n{'='*60}")
    print(f"TEST 1: Concurrent semaphore ({n_workers} workers)")
    print(f"{'='*60}")

    # Use a temp dir so we don't interfere with real sessions
    test_dir = Path(tempfile.mkdtemp(prefix="test_sem_"))
    manager = multiprocessing.Manager()
    results = manager.dict()
    barrier = multiprocessing.Barrier(n_workers, timeout=15)

    workers = []
    for i in range(n_workers):
        p = multiprocessing.Process(
            target=_worker_acquire,
            args=(str(test_dir), i, results, barrier),
        )
        workers.append(p)

    for p in workers:
        p.start()
    for p in workers:
        p.join(timeout=20)

    # Analyze results
    slots = []
    errors = []
    for wid in range(n_workers):
        r = dict(results.get(wid, {}))
        if r.get("error"):
            errors.append(f"  Worker {wid}: ERROR - {r['error']}")
        else:
            slots.append(r["slot"])
            print(f"  Worker {wid}: slot={r['slot']} pid={r['pid']}")

    if errors:
        for e in errors:
            print(e)

    # Verify uniqueness
    unique = len(set(slots)) == len(slots)
    in_range = all(0 <= s < MAX_CONCURRENT_SESSIONS for s in slots)
    passed = unique and in_range and len(errors) == 0
    print(f"\n  Slots acquired: {sorted(slots)}")
    print(f"  All unique: {unique}")
    print(f"  All in range [0, {MAX_CONCURRENT_SESSIONS}): {in_range}")
    print(f"  Errors: {len(errors)}")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")

    # Cleanup
    import shutil
    shutil.rmtree(test_dir, ignore_errors=True)
    return passed


def test_stale_cleanup() -> bool:
    """Test that stale slot files (dead PID) are cleaned up."""
    print(f"\n{'='*60}")
    print(f"TEST 2: Stale slot cleanup")
    print(f"{'='*60}")

    test_dir = Path(tempfile.mkdtemp(prefix="test_stale_"))
    sem = SessionSemaphore(sessions_dir=test_dir)

    # Create a fake stale slot with a dead PID
    dead_pid = 99999
    stale_file = test_dir / "slot-0.lock"
    stale_file.write_text(f"{dead_pid} {time.time() - 600:.0f}\n", encoding="utf-8")
    print(f"  Created stale slot-0.lock with dead PID {dead_pid}")

    # Acquire should clean stale and give us slot 0
    slot = sem.acquire(wait_timeout=5)
    print(f"  Acquired slot: {slot}")
    sem.release()

    passed = slot == 0
    print(f"  RESULT: {'PASS' if passed else 'FAIL'} (expected slot 0)")

    import shutil
    shutil.rmtree(test_dir, ignore_errors=True)
    return passed


def test_overflow_rejection() -> bool:
    """Test that requesting more than MAX slots raises BrowserBusyError."""
    print(f"\n{'='*60}")
    print(f"TEST 3: Overflow rejection (>{MAX_CONCURRENT_SESSIONS} slots)")
    print(f"{'='*60}")

    test_dir = Path(tempfile.mkdtemp(prefix="test_overflow_"))

    # Fill all slots with current PID (they'll look alive)
    pid = os.getpid()
    for i in range(MAX_CONCURRENT_SESSIONS):
        (test_dir / f"slot-{i}.lock").write_text(f"{pid} {time.time():.0f}\n", encoding="utf-8")
    print(f"  Filled all {MAX_CONCURRENT_SESSIONS} slots with PID {pid}")

    # Try to acquire one more — should fail quickly
    sem = SessionSemaphore(sessions_dir=test_dir)
    try:
        sem.acquire(wait_timeout=2)
        print(f"  ERROR: acquire() succeeded when all slots full!")
        passed = False
    except BrowserBusyError as e:
        print(f"  BrowserBusyError raised correctly: {str(e)[:80]}...")
        passed = True

    # Cleanup
    import shutil
    shutil.rmtree(test_dir, ignore_errors=True)
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return passed


def test_fingerprint_uniqueness() -> bool:
    """Test that all 8 instances get different fingerprints."""
    print(f"\n{'='*60}")
    print(f"TEST 4: Fingerprint uniqueness (all {MAX_CONCURRENT_SESSIONS} slots)")
    print(f"{'='*60}")

    fps = []
    for i in range(MAX_CONCURRENT_SESSIONS):
        fp = PerplexityCouncil._get_instance_fingerprint(i)
        fps.append(fp)
        gpu_note = " [GPU OFF]" if i >= INSTANCE_GPU_CUTOFF else ""
        print(f"  Slot {i}: {fp['viewport'][0]}x{fp['viewport'][1]}  lang={fp['language'][:15]:<15}  seed={fp['seed'][:8]}{gpu_note}")

    viewports = [f["viewport"] for f in fps]
    seeds = [f["seed"] for f in fps]
    unique_vp = len(set(viewports)) == len(viewports)
    unique_seeds = len(set(seeds)) == len(seeds)
    passed = unique_vp and unique_seeds
    print(f"\n  Unique viewports: {unique_vp}")
    print(f"  Unique seeds: {unique_seeds}")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return passed


def test_chrome_args() -> bool:
    """Test chrome args differ by instance — GPU cutoff, window position."""
    print(f"\n{'='*60}")
    print(f"TEST 5: Chrome args per instance")
    print(f"{'='*60}")

    passed = True
    for i in [0, 3, 5, 6, 7]:
        args = PerplexityCouncil._chrome_args(i)
        has_gpu_off = "--disable-gpu" in args
        has_swiftshader = any("swiftshader" in a for a in args)
        has_disk_cache = any("disk-cache-size" in a for a in args)
        has_position = any("window-position" in a for a in args)
        expected_gpu = i >= INSTANCE_GPU_CUTOFF

        ok = (has_gpu_off == expected_gpu) and has_disk_cache and has_position
        status = "OK" if ok else "FAIL"
        if not ok:
            passed = False
        print(f"  Slot {i}: gpu_off={has_gpu_off} (expect={expected_gpu})  disk_cache={has_disk_cache}  position={has_position}  [{status}]")

    print(f"\n  RESULT: {'PASS' if passed else 'FAIL'}")
    return passed


async def test_browser_launches(n_instances: int = 4) -> bool:
    """Test that N browser instances launch concurrently without conflicts.

    Launches real Chrome processes with temp profiles, verifies they start,
    then shuts them down. Does NOT navigate to Perplexity.
    """
    print(f"\n{'='*60}")
    print(f"TEST 6: Concurrent browser launches ({n_instances} instances)")
    print(f"{'='*60}")

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("  SKIP: playwright not installed")
        return True

    pw = await async_playwright().start()
    contexts = []
    temp_dirs = []
    passed = True

    try:
        for i in range(n_instances):
            fp = PerplexityCouncil._get_instance_fingerprint(i)
            vp_w, vp_h = fp["viewport"]
            temp_dir = tempfile.mkdtemp(prefix=f"test_browser_{i}_")
            temp_dirs.append(temp_dir)

            try:
                ctx = await pw.chromium.launch_persistent_context(
                    user_data_dir=temp_dir,
                    channel="chrome",
                    headless=False,
                    args=PerplexityCouncil._chrome_args(instance_id=i),
                    viewport={"width": vp_w, "height": vp_h},
                )
                contexts.append((i, ctx))
                print(f"  Instance {i}: launched  viewport={vp_w}x{vp_h}  pid=active")
            except Exception as e:
                print(f"  Instance {i}: FAILED - {e}")
                passed = False

        # Hold all instances open briefly to prove concurrency
        print(f"\n  All {len(contexts)} instances running concurrently. Holding 3s...")
        await asyncio.sleep(3)

        # Verify each context is still alive
        for i, ctx in contexts:
            try:
                pages = ctx.pages
                print(f"  Instance {i}: alive, {len(pages)} page(s)")
            except Exception as e:
                print(f"  Instance {i}: DEAD - {e}")
                passed = False

    finally:
        # Cleanup: close all contexts
        print(f"\n  Cleaning up {len(contexts)} instances...")
        for i, ctx in contexts:
            try:
                await ctx.close()
            except Exception:
                pass

        await pw.stop()

        import shutil
        for d in temp_dirs:
            shutil.rmtree(d, ignore_errors=True)

    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return passed


async def test_temp_dir_cleanup() -> bool:
    """Test that orphaned temp dirs are cleaned up on acquire."""
    print(f"\n{'='*60}")
    print(f"TEST 7: Orphaned temp dir cleanup")
    print(f"{'='*60}")

    # Create an old orphaned dir
    tmp = tempfile.gettempdir()
    orphan = Path(tmp) / "council_np_test_orphan"
    orphan.mkdir(exist_ok=True)
    # Set mtime to 15 minutes ago
    old_time = time.time() - 900
    os.utime(str(orphan), (old_time, old_time))
    print(f"  Created orphan: {orphan} (mtime=15min ago)")

    # Also create a recent one that should NOT be cleaned
    recent = Path(tmp) / "council_np_test_recent"
    recent.mkdir(exist_ok=True)
    print(f"  Created recent: {recent} (mtime=now)")

    # Acquire triggers cleanup
    test_dir = Path(tempfile.mkdtemp(prefix="test_cleanup_"))
    sem = SessionSemaphore(sessions_dir=test_dir)
    sem.acquire(wait_timeout=5)
    sem.release()

    orphan_gone = not orphan.exists()
    recent_alive = recent.exists()
    passed = orphan_gone and recent_alive
    print(f"  Orphan removed: {orphan_gone}")
    print(f"  Recent kept: {recent_alive}")
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")

    # Cleanup
    import shutil
    if recent.exists():
        shutil.rmtree(recent, ignore_errors=True)
    if orphan.exists():
        shutil.rmtree(orphan, ignore_errors=True)
    shutil.rmtree(test_dir, ignore_errors=True)
    return passed


def _worker_submit_lock(worker_id: int, hold_seconds: float, lock_path_str: str, results: dict) -> None:
    """Worker process: acquire FileLock (thread_local=False, same config as
    submission_lock.get_submit_lock()), hold, release. Record timestamps so
    the parent can assert serialisation.
    """
    import time
    from filelock import FileLock

    t_start = time.time()
    lock = FileLock(lock_path_str, timeout=30, thread_local=False)
    try:
        lock.acquire()
        t_acquired = time.time()
        time.sleep(hold_seconds)
        t_before_release = time.time()
        lock.release()
        t_released = time.time()
        results[worker_id] = {
            "pid": os.getpid(),
            "t_start": t_start,
            "t_acquired": t_acquired,
            "t_before_release": t_before_release,
            "t_released": t_released,
            "error": None,
        }
    except Exception as e:
        results[worker_id] = {
            "pid": os.getpid(),
            "error": str(e),
        }


def test_submit_lock_serialises_concurrent_processes(hold_seconds: float = 1.5) -> bool:
    """LOCK-SCOPE REGRESSION TEST: verify the submit_lock pattern serialises
    correctly across processes.

    Two workers each acquire+hold+release a FileLock at the SAME path with
    thread_local=False (the production configuration in
    `submission_lock.get_submit_lock()`). Validates that:
    1. Both workers complete without error
    2. The second worker's acquire timestamp is AFTER the first worker's
       release timestamp (with 100ms tolerance for filelock poll interval)
    3. Total elapsed time confirms sequential (not parallel) execution

    Locks in the cross-process serialisation contract that
    `submission_lock.py` depends on. If filelock changes its semantics or
    a future refactor of submission_lock.py breaks the thread_local=False
    invariant, this test fails fast.

    Uses a test-specific lock path so it does NOT interfere with a real
    /research-perplexity run in progress.
    """
    print(f"\n{'='*60}")
    print(f"TEST 9: submit_lock cross-process serialisation")
    print(f"{'='*60}")

    test_lock_path = Path(tempfile.gettempdir()) / f"test_submit_lock_{os.getpid()}.lock"
    # Ensure clean slate
    try:
        if test_lock_path.exists():
            test_lock_path.unlink()
    except OSError:
        pass

    manager = multiprocessing.Manager()
    results = manager.dict()
    workers = []
    for i in range(2):
        p = multiprocessing.Process(
            target=_worker_submit_lock,
            args=(i, hold_seconds, str(test_lock_path), results),
        )
        workers.append(p)

    test_start = time.time()
    for p in workers:
        p.start()
    # Generous join timeout: 4x hold + some slack for process startup.
    for p in workers:
        p.join(timeout=(hold_seconds * 4 + 5))
    test_elapsed = time.time() - test_start

    r0 = dict(results.get(0, {}))
    r1 = dict(results.get(1, {}))

    # Check for errors
    errors = [(i, r.get("error")) for i, r in [(0, r0), (1, r1)] if r.get("error")]
    if errors:
        for i, e in errors:
            print(f"  Worker {i}: ERROR — {e}")
        print(f"  RESULT: FAIL (worker errors)")
        # Cleanup
        try:
            test_lock_path.unlink()
        except OSError:
            pass
        return False

    # Determine who acquired first (by t_acquired timestamp).
    if r0.get("t_acquired", float("inf")) <= r1.get("t_acquired", float("inf")):
        first, second = r0, r1
        first_id, second_id = 0, 1
    else:
        first, second = r1, r0
        first_id, second_id = 1, 0

    print(f"  Worker {first_id} (PID {first['pid']}): "
          f"acquired t+{first['t_acquired']-test_start:.3f}s, "
          f"released t+{first['t_released']-test_start:.3f}s "
          f"(held {first['t_released']-first['t_acquired']:.3f}s)")
    print(f"  Worker {second_id} (PID {second['pid']}): "
          f"acquired t+{second['t_acquired']-test_start:.3f}s, "
          f"released t+{second['t_released']-test_start:.3f}s "
          f"(held {second['t_released']-second['t_acquired']:.3f}s)")
    print(f"  Total elapsed: {test_elapsed:.2f}s "
          f"(sequential ~{2*hold_seconds:.1f}s, parallel would be ~{hold_seconds:.1f}s)")

    # Assertions:
    both_completed = "t_released" in first and "t_released" in second
    # Second's acquire is AFTER first's release (50ms poll-interval tolerance).
    serialised = (second["t_acquired"] - first["t_released"]) >= -0.05
    # Total time confirms sequential execution: should be ~2 * hold, not ~hold.
    sequential_timing = test_elapsed >= (hold_seconds * 1.8)

    print(f"\n  Both workers completed:                        {both_completed}")
    print(f"  Second acquired AFTER first released:          {serialised}")
    print(f"  Total elapsed confirms sequential execution:   {sequential_timing}")

    passed = both_completed and serialised and sequential_timing
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")

    # Cleanup
    try:
        test_lock_path.unlink()
    except OSError:
        pass
    return passed


def test_concurrent_subprocess_isolation(n_workers: int = 2) -> bool:
    """LIVE integration test: spawn N `python council_query.py` subprocesses
    in parallel, assert distinct chrome.exe process trees with distinct
    canonical temp profile dirs, distinct synthesis outputs, clean rmtree
    on completion.

    Locks in the realpath canonicalisation + isolation-args fix from
    commit 82e61e3 (2026-05-13). Without this test, a future Playwright /
    Chrome update could silently re-introduce the cross-instance state-
    bleed bug.

    Gated by `--live` flag or RUN_LIVE_TESTS=1 env (real Perplexity queries
    take 30-90s each; full test ~2 minutes).
    """
    print(f"\n{'='*60}")
    print(f"TEST 8: Concurrent subprocess isolation (LIVE — N={n_workers})")
    print(f"{'='*60}")

    try:
        import psutil
    except ImportError:
        print("  SKIP: psutil not installed (pip install psutil)")
        return True

    import subprocess
    script_dir = Path(__file__).parent
    council_query_path = script_dir / "council_query.py"
    if not council_query_path.exists():
        print(f"  SKIP: {council_query_path} not found")
        return True

    # Distinct short queries so cross-contamination is detectable.
    queries = [
        "What is 2 plus 2? One number only.",
        "What color is the sky on a clear day? One word only.",
        "What is the capital of France? One word only.",
        "What is the speed of light in km/s? One number only.",
    ][:n_workers]

    # Snapshot existing council_np_ temp dirs so we can detect leftovers.
    temp_root = Path(tempfile.gettempdir())
    pre_existing = set(d.name for d in temp_root.glob("council_np_*"))

    print(f"  Spawning {n_workers} council_query.py subprocesses with distinct queries...")
    t0 = time.perf_counter()
    procs = []
    for i, q in enumerate(queries):
        p = subprocess.Popen(
            [
                sys.executable,
                str(council_query_path),
                "--mode", "browser",
                "--perplexity-mode", "research",
                "--invocation-id", f"test{i:04d}",
                q,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        procs.append((i, q, p))

    # Mid-flight Chrome check: wait briefly for Chrome to spawn, then poll
    # psutil for chrome.exe processes with --user-data-dir=council_np_*.
    time.sleep(15)
    chrome_procs = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["name"] not in ("chrome.exe", "chrome"):
                continue
            cmdline = proc.info["cmdline"] or []
            user_data_arg = next(
                (a for a in cmdline
                 if a.startswith("--user-data-dir=") and "council_np_" in a),
                None,
            )
            if user_data_arg:
                chrome_procs.append({
                    "pid": proc.info["pid"],
                    "user_data_dir": user_data_arg.split("=", 1)[1],
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    distinct_dirs = sorted(set(p["user_data_dir"] for p in chrome_procs))
    print(f"  Mid-flight: {len(chrome_procs)} chrome.exe parents w/ council_np_ profile, "
          f"{len(distinct_dirs)} distinct dirs")
    for d in distinct_dirs:
        print(f"    {d}")

    # Canonicalisation check: realpath of each path should equal itself
    # (idempotent under realpath + rstrip(sep)).
    canonical_ok = all(
        d == os.path.realpath(d).rstrip(os.sep) for d in distinct_dirs
    ) if distinct_dirs else False
    print(f"  All dirs are canonical (realpath idempotent): {canonical_ok}")

    # Wait for all subprocesses to complete.
    syntheses = []
    rcs = []
    for i, q, p in procs:
        try:
            stdout, stderr = p.communicate(timeout=300)
        except subprocess.TimeoutExpired:
            p.kill()
            stdout, stderr = p.communicate()
            print(f"  Subprocess {i}: TIMEOUT after 300s")
            stdout = stdout or ""
            stderr = stderr or ""
        rc = p.returncode
        rcs.append(rc)
        synth = (stdout or "").strip()
        syntheses.append(synth)
        print(f"  Subprocess {i}: rc={rc} synth_len={len(synth)} q={q[:50]!r}")

    elapsed = time.perf_counter() - t0
    print(f"  Total elapsed: {elapsed:.1f}s")

    # Post-completion: NEW council_np_ dirs should all be cleaned up
    # (the existing __aexit__ rmtree handles this).
    post_existing = set(d.name for d in temp_root.glob("council_np_*"))
    new_alive_dirs = post_existing - pre_existing
    cleanup_ok = len(new_alive_dirs) == 0
    if not cleanup_ok:
        sample = sorted(new_alive_dirs)[:5]
        print(f"  WARN: {len(new_alive_dirs)} council_np_* dirs left behind: {sample}")

    # Final assertions
    n_chrome_parents_ok = len(chrome_procs) >= n_workers
    n_distinct_dirs_ok = len(distinct_dirs) >= n_workers
    all_rcs_zero = all(rc == 0 for rc in rcs)
    syntheses_nonempty = all(len(s) > 50 for s in syntheses)
    syntheses_distinct = len(set(syntheses)) == len(syntheses)

    print(f"\n  chrome.exe parents observed mid-flight >= {n_workers}: {n_chrome_parents_ok}")
    print(f"  distinct canonical user_data_dirs >= {n_workers}: {n_distinct_dirs_ok}")
    print(f"  all dirs are canonical (realpath idempotent):  {canonical_ok}")
    print(f"  all subprocesses returned rc=0:                {all_rcs_zero}")
    print(f"  syntheses non-empty (len > 50):                {syntheses_nonempty}")
    print(f"  syntheses distinct (no state bleed):           {syntheses_distinct}")
    print(f"  temp dirs cleaned up:                          {cleanup_ok}")

    passed = all([
        n_chrome_parents_ok,
        n_distinct_dirs_ok,
        canonical_ok,
        all_rcs_zero,
        syntheses_nonempty,
        syntheses_distinct,
        cleanup_ok,
    ])
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}")
    return passed


async def main():
    print("=" * 60)
    print("PARALLEL PLAYWRIGHT SCALING — TEST SUITE")
    print(f"MAX_CONCURRENT_SESSIONS={MAX_CONCURRENT_SESSIONS}  INSTANCE_GPU_CUTOFF={INSTANCE_GPU_CUTOFF}")
    print("=" * 60)

    # --live flag or RUN_LIVE_TESTS=1 env opts into the slow live test 8.
    run_live = ("--live" in sys.argv) or (os.environ.get("RUN_LIVE_TESTS") == "1")

    results = {}

    # Tests 1-5: no browser needed
    results["semaphore_concurrency"] = test_concurrent_semaphore(5)
    results["stale_cleanup"] = test_stale_cleanup()
    results["overflow_rejection"] = test_overflow_rejection()
    results["fingerprint_uniqueness"] = test_fingerprint_uniqueness()
    results["chrome_args"] = test_chrome_args()

    # Tests 6-7: need browser/filesystem
    results["temp_dir_cleanup"] = await test_temp_dir_cleanup()
    results["browser_launches"] = await test_browser_launches(4)

    # Test 9: submit_lock cross-process serialisation regression test
    # (no browser, no Perplexity — runs in ~4s, locks in the lock-scope
    # contract that prevents two-Claude-session Chrome ProcessSingleton races).
    results["submit_lock_serialisation"] = test_submit_lock_serialises_concurrent_processes(1.5)

    # Test 8: live integration (slow — opt-in only).
    # NOTE: spawns real `python council_query.py` subprocesses against the
    # real Perplexity session. Requires a recent /cache-perplexity-session.
    # ~2 minutes for N=2 with research mode.
    if run_live:
        results["concurrent_subprocess_isolation"] = test_concurrent_subprocess_isolation(2)
    else:
        print(
            f"\n  (Skipping live integration test 8 — pass --live or set "
            f"RUN_LIVE_TESTS=1 to include it.)"
        )

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n  {passed}/{total} tests passed")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    asyncio.run(main())
