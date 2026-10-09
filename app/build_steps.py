"""Developer tool: regenerates steps/*.py from the Colab notebooks so there is ONE source of truth for the logic.
    python build_steps.py <folder-with-notebooks>
You do not need this to use the app."""
import re, sys, nbformat
from pathlib import Path

NOTEBOOKS = {  # notebook file -> (step file, title)
    "01_Architecture_Diagram.ipynb": "step_01_architecture.py",
    "02_Data_Cleaning_and_MySQL_Tables.ipynb": "step_02_clean_and_load.py",
    "04_Seller_Table_Update.ipynb": "step_04_seller_load.py",
    "05_MAP_LPP_Compliance_Logic.ipynb": "step_05_compliance.py",
    "06_Enforcement_Letters_and_Summary.ipynb": "step_06_enforcement.py",
    "07_Charts_and_Reports.ipynb": "step_07_reports.py",
}
OVERRIDABLE = ["QUARTER_MODE", "FORCE_FX_REFRESH", "LETTER_AT", "LETTER_FORMAT", "MANUFACTURER_NAME", "CONTACT_LINE",
               "RESPONSE_DAYS", "RUN_DATES", "REPLACE_EXISTING_DAYS", "DATES_TO_LOAD", "FOCUS_DATE", "TOP_N"]
BOOT_MARK = "PROJECT_DIR = \"/content/drive/MyDrive/MAP_Compliance_Project\""
BOOT = '''import os
import map_common as mc          # run_step.py has already put the project folder on the import path
mc.ensure_dirs()
print("Project folder:", mc.PROJECT_DIR)'''

def transform(src, counts):
    if BOOT_MARK in src:
        return BOOT
    for name in OVERRIDABLE:   # NAME = value   # comment   ->   NAME = _ov("NAME", value)   # comment
        pat = re.compile(rf"^({name})(\s*=\s*)(.+?)(\s+#.*)?$", re.M)
        def repl(m):
            counts[name] = counts.get(name, 0) + 1
            return f'{m.group(1)} = _ov("{name}", {m.group(3)}){m.group(4) or ""}'
        src = pat.sub(repl, src)
    if "LPP_LOGIC = {" in src:      # multi-line dictionary: apply the override after it is defined
        src += '\nLPP_LOGIC = {k: tuple(v) for k, v in _ov("LPP_LOGIC", LPP_LOGIC).items()}\nprint("LPP table in use:", LPP_LOGIC)'
        counts["LPP_LOGIC"] = counts.get("LPP_LOGIC", 0) + 1
    return src

def main(nb_dir, out_dir):
    for nb_file, step_file in NOTEBOOKS.items():
        nb = nbformat.read(Path(nb_dir) / nb_file, 4)
        counts, parts = {}, []
        for i, cell in enumerate(nb.cells):
            if cell.cell_type != "code":
                continue
            what = nb.cells[i - 1].source.split("\n")[0].replace("**What this cell does:**", "").strip()
            parts.append(f"# {'-' * 70}\n# {what[:150]}\n# {'-' * 70}\n" + transform(cell.source, counts))
        header = f'"""AUTO-GENERATED from {nb_file} by build_steps.py - edit the notebook and regenerate, not this file."""\n'
        (Path(out_dir) / step_file).write_text(header + "\n\n".join(parts) + "\n", encoding="utf-8")
        print(f"{step_file:<30} overrides applied: {counts}")

if __name__ == "__main__":
    main(sys.argv[1], Path(__file__).parent / "steps")
