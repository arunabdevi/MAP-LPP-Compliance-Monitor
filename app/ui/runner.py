"""Starts run_step.py as a separate process and streams its output (used by the Upload & run page)."""
import os, sys, subprocess, time
from datetime import datetime
from ui.config import APP_DIR, LOG_DIR

LOCK = LOG_DIR / "run.lock"
LOCK_MAX_AGE_SEC = 6 * 3600

def is_running():
    if not LOCK.exists():
        return False
    if time.time() - LOCK.stat().st_mtime > LOCK_MAX_AGE_SEC:     # stale lock from a crashed run
        LOCK.unlink(missing_ok=True)
        return False
    return True

def run_steps(steps, on_line):
    """Runs the steps one after another in one process. Calls on_line(text) for every output line.
    Returns (success, log_path)."""
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}.log"
    LOCK.write_text(f"{os.getpid()} {datetime.now().isoformat()}")
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    ok = False
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            head = f"Started {datetime.now():%Y-%m-%d %H:%M:%S} | steps: {' '.join(steps)}\n"
            log.write(head); on_line(head)
            proc = subprocess.Popen([sys.executable, "-u", str(APP_DIR / "run_step.py"), *steps], cwd=str(APP_DIR), env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                    errors="replace", bufsize=1)
            for line in proc.stdout:
                log.write(line); log.flush(); on_line(line)
            ok = proc.wait() == 0
            tail = f"\nResult: {'SUCCESS' if ok else 'FAILED'} at {datetime.now():%H:%M:%S}\n"
            log.write(tail); on_line(tail)
    finally:
        LOCK.unlink(missing_ok=True)
    return ok, log_path

def recent_logs(n=10):
    return sorted(LOG_DIR.glob("run_*.log"), reverse=True)[:n]

def result_of(path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "?"
    return "SUCCESS" if "Result: SUCCESS" in text else ("FAILED" if "Result: FAILED" in text else "running/unknown")
