import re, shutil
from datetime import datetime, date
import pandas as pd
import streamlit as st
from ui import db, runner, settings_store
from ui.config import RAW_DIR, SELLER_DIR, REQUIRED_RAW, SELLER_COLUMNS, SAMPLE_DIR, LOG_DIR

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.csv$")
PRESETS = {"Daily run  (04 → 05 → 06 → 07)": ["04", "05", "06", "07"],
           "Full setup  (02 → 04 → 05 → 06 → 07)": ["02", "04", "05", "06", "07"], "Custom": None}
STEP_LABELS = {"02": "02  Clean source files and load master tables", "04": "04  Load daily seller prices",
               "05": "05  MAP / LPP compliance logic", "06": "06  Letters, summary and approval queue",
               "07": "07  Charts and Excel report", "01": "01  Architecture diagram"}

def _save_raw(name, data):
    target = RAW_DIR / name
    if target.exists():                                   # keep the previous version
        arch = RAW_DIR / "_archive"; arch.mkdir(exist_ok=True)
        shutil.copyfile(target, arch / f"{datetime.now():%Y%m%d_%H%M%S}_{name}")
    target.write_bytes(data)

def _source_files():
    st.subheader("1 · Manufacturer source files")
    rows = []
    for name in REQUIRED_RAW:
        p = RAW_DIR / name
        rows.append({"File": name, "Status": "present" if p.exists() else "MISSING",
                     "Size (KB)": round(p.stat().st_size / 1024, 1) if p.exists() else None,
                     "Last changed": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M") if p.exists() else ""})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.expander("Upload or replace source files"):
        st.caption("Upload any of the five files. The previous version is kept in raw_data/_archive. "
                   "After changing them run **Full setup** (step 02) so the master tables are rebuilt.")
        for name, exts in REQUIRED_RAW.items():
            up = st.file_uploader(name, type=exts, key=f"raw_{name}")
            if up is not None and st.button(f"Save as {name}", key=f"save_{name}"):
                _save_raw(name, up.getvalue()); st.success(f"Saved {name}"); st.rerun()

def _seller_files():
    st.subheader("2 · Daily seller price files")
    files = sorted(SELLER_DIR.glob("*.csv"))
    if files:
        info = [{"Date": f.stem, "File": f.name, "Size (KB)": round(f.stat().st_size / 1024, 1)} for f in files]
        st.write(f"{len(files)} file(s) from **{files[0].stem}** to **{files[-1].stem}**")
        st.dataframe(pd.DataFrame(info), hide_index=True, width="stretch", height=min(35 * len(info) + 40, 260))
    else:
        st.info("No daily files yet.")
    with st.expander("Add daily files (CSV)"):
        st.caption("Files named like 2026-01-05.csv keep their name. For any other name you choose the date. "
                   f"Required columns: {', '.join(SELLER_COLUMNS)}")
        ups = st.file_uploader("Daily seller CSV files", type=["csv"], accept_multiple_files=True, key="seller_up")
        plan = []
        for u in ups or []:
            m = DATE_RE.match(u.name)
            if m:
                plan.append((u, m.group(1)))
            else:
                d = st.date_input(f"Date for “{u.name}”", value=date.today(), key=f"sd_{u.name}")
                plan.append((u, d.isoformat()))
        if plan and st.button("Validate and save", type="primary", key="seller_save"):
            for u, d in plan:
                try:
                    header = pd.read_csv(u, nrows=0, dtype=str).columns.tolist(); u.seek(0)
                except Exception as exc:
                    st.error(f"{u.name}: cannot read as CSV ({exc})"); continue
                missing = [c for c in SELLER_COLUMNS if c not in header]
                if missing:
                    st.error(f"{u.name}: missing column(s) {missing}"); continue
                existed = (SELLER_DIR / f"{d}.csv").exists()
                (SELLER_DIR / f"{d}.csv").write_bytes(u.getvalue())
                st.success(f"Saved {d}.csv" + (" (replaced the existing file)" if existed else ""))
            st.info("Now run **04 → 05 → 06 → 07** below to load and judge the new data.")

def _sample_data():
    if not SAMPLE_DIR.exists():
        return
    with st.expander("Try it with the included SAMPLE data (fictional)"):
        st.caption("Copies invented source files and 15 daily seller files into the project folder so you can test the whole flow. "
                   "It does not overwrite files that already exist.")
        if st.button("Copy sample data into the project"):
            n = 0
            for sub, dest in [("raw_data", RAW_DIR), ("seller_data", SELLER_DIR)]:
                for f in (SAMPLE_DIR / sub).glob("*"):
                    if f.is_file() and not (dest / f.name).exists():
                        shutil.copyfile(f, dest / f.name); n += 1
            st.success(f"Copied {n} file(s). Next: run the **Full setup** preset below."); st.rerun()

def _run_section():
    st.subheader("3 · Run the pipeline")
    s = settings_store.load()
    with st.expander("Settings that will be used (change them on the Settings page)"):
        st.json({k: v for k, v in s.items() if k != "LPP_LOGIC"})
    ok, err = db.connection_ok()
    if not ok:
        st.error(f"Cannot reach the database: {err}\n\nCheck the MAP_DB_* values in your .env file and that MySQL is running.")
        return
    preset = st.radio("What to run", list(PRESETS), horizontal=True)
    steps = PRESETS[preset] or st.multiselect("Steps (they run in this order)", list(STEP_LABELS), default=["04", "05"],
                                              format_func=STEP_LABELS.get)
    steps = sorted(steps)
    if preset.startswith("Full"):
        st.warning("Step 02 rebuilds the six master tables from the source files (the seller price history is kept).")
    missing_raw = [n for n in REQUIRED_RAW if not (RAW_DIR / n).exists()]
    if "02" in steps and missing_raw:
        st.error(f"Step 02 needs these source files first: {', '.join(missing_raw)}")
        return
    if any(x in steps for x in ["04"]) and not list(SELLER_DIR.glob("*.csv")):
        st.error("Step 04 needs at least one daily seller CSV.")
        return
    if runner.is_running():
        st.warning("A run is already in progress (started from another browser tab or by a scheduled job). Wait for it to finish.")
        return
    if st.button("▶ Run now", type="primary", disabled=not steps):
        box, lines = st.empty(), []
        def on_line(t):
            lines.append(t.rstrip("\n")); box.code("\n".join(lines[-25:]), language="text")
        with st.spinner("Running... this page stays busy until the run finishes."):
            success, log = runner.run_steps(steps, on_line)
        (st.success if success else st.error)(("Finished successfully." if success else "A step failed - see the end of the log above.")
                                              + f"  Full log: {log.name}")
        st.cache_data.clear()

def _history():
    st.subheader("Run history")
    logs = runner.recent_logs(8)
    if not logs:
        st.caption("No runs yet.")
    for p in logs:
        res = runner.result_of(p)
        with st.expander(f"{'✅' if res == 'SUCCESS' else '❌' if res == 'FAILED' else '⏳'}  {p.stem.replace('run_', '')}  -  {res}"):
            txt = p.read_text(encoding="utf-8", errors="replace")
            st.code(txt[-6000:], language="text")
            st.download_button("Download full log", txt, p.name, key=f"dl_{p.name}")

def render():
    st.title("Upload & run")
    _source_files()
    _seller_files()
    _sample_data()
    st.divider()
    _run_section()
    st.divider()
    _history()
