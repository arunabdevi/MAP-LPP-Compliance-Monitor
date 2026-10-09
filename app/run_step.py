"""Run one or more pipeline steps from the command line (also what the web app and cron call).

    python run_step.py 05              one step
    python run_step.py 04 05 06 07     several, in order (stops at the first failure)
    python run_step.py daily           04 -> 05 -> 06 -> 07
    python run_step.py full            02 -> 04 -> 05 -> 06 -> 07

Settings come from .env (database) and the project's settings.json (rules and wording).
Exit code 0 = success, 1 = a step failed (the error is printed)."""
import os, sys, json, runpy, time, traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ui import config                          # loads .env, sets paths, imports the shared helper
from ui import settings_store

STEPS = {
    "01": ("step_01_architecture.py", "Architecture diagram"),
    "02": ("step_02_clean_and_load.py", "Clean source files and load master tables"),
    "04": ("step_04_seller_load.py", "Load daily seller prices"),
    "05": ("step_05_compliance.py", "MAP / LPP compliance logic"),
    "06": ("step_06_enforcement.py", "Enforcement letters, summary and approval queue"),
    "07": ("step_07_reports.py", "Charts and Excel report"),
}
PRESETS = {"daily": ["04", "05", "06", "07"], "all": ["04", "05", "06", "07"], "full": ["02", "04", "05", "06", "07"]}

def make_override_function():
    values = settings_store.load()
    def _ov(name, default=None):
        return values.get(name, default)
    return _ov

def run_one(step):
    file_name, title = STEPS[step]
    print(f"\n===== STEP {step}: {title} =====", flush=True)
    t0 = time.time()
    runpy.run_path(str(HERE / "steps" / file_name), init_globals={"_ov": make_override_function()}, run_name="__step__")
    print(f"===== STEP {step} finished in {time.time() - t0:.0f}s =====", flush=True)

def expand(args):
    out = []
    for a in args:
        out += PRESETS.get(a.lower(), [a.zfill(2)])
    bad = [s for s in out if s not in STEPS]
    if bad:
        sys.exit(f"Unknown step(s): {bad}. Valid: {sorted(STEPS)} or {sorted(PRESETS)}")
    return out

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    todo = expand(sys.argv[1:])
    print("Project folder:", config.PROJECT_DIR, "| database:", f"{config.mc.DB_HOST}/{config.mc.DB_NAME}", "| steps:", todo, flush=True)
    for s in todo:
        try:
            run_one(s)
        except SystemExit:
            raise
        except BaseException:
            traceback.print_exc()
            print(f"\nSTEP {s} FAILED - later steps were not run.", flush=True)
            sys.exit(1)
    print("\nALL REQUESTED STEPS COMPLETED.", flush=True)
