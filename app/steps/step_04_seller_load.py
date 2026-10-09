"""AUTO-GENERATED from 04_Seller_Table_Update.ipynb by build_steps.py - edit the notebook and regenerate, not this file."""
# ----------------------------------------------------------------------
# Connects Google Drive, finds your project folder and loads the shared helper module `map_common`.
# ----------------------------------------------------------------------
import os
import map_common as mc          # run_step.py has already put the project folder on the import path
mc.ensure_dirs()
print("Project folder:", mc.PROJECT_DIR)

# ----------------------------------------------------------------------
# Starts MySQL (restoring your Drive backup in a new Colab session) and connects.
# ----------------------------------------------------------------------
import os, re, glob
import pandas as pd
from datetime import datetime
from sqlalchemy import text
engine = mc.connect_db()

# ----------------------------------------------------------------------
# Settings: which days to load (all files, or a list of dates), the columns every file must have, and whether days already in the database are replaced.
# ----------------------------------------------------------------------
DATES_TO_LOAD = _ov("DATES_TO_LOAD", None)            # None = every file found | or a list such as ["2026-01-05", "2026-01-06"]
REPLACE_EXISTING_DAYS = _ov("REPLACE_EXISTING_DAYS", True)    # True = reload a day that is already in the table (no duplicates are created)
EXPECTED_COLUMNS = ["SKU", "Marketplace", "Seller_name", "region", "adv_price", "Screenshot", "live_link"]
DATE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})\.csv$")
print("Looking in:", mc.SELLER_DIR)

# ----------------------------------------------------------------------
# Lists the daily CSV files and reads the date from each file name (e.g. `2026-01-05.csv` is 5 Jan 2026). A file with a wrongly spelled name stops the r
# ----------------------------------------------------------------------
def parse_date_from_filename(path):
    name = os.path.basename(path)
    m = DATE_PATTERN.match(name)
    if not m:
        raise ValueError(f"File '{name}' does not match 'YYYY-MM-DD.csv'. Rename it or move it out of seller_data/.")
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"File '{name}' looks like a date but is not a real calendar date.")

csv_files = sorted(glob.glob(os.path.join(mc.SELLER_DIR, "*.csv")))
if not csv_files:
    raise FileNotFoundError(f"No CSV files in {mc.SELLER_DIR}. Upload the daily files (YYYY-MM-DD.csv) there.")
file_dates = {f: parse_date_from_filename(f) for f in csv_files}
if DATES_TO_LOAD:
    wanted = {pd.Timestamp(d).date() for d in DATES_TO_LOAD}
    file_dates = {f: d for f, d in file_dates.items() if d in wanted}
print(f"{len(file_dates)} file(s) selected:")
for f, d in file_dates.items():
    print("  ", os.path.basename(f), "->", d)

# ----------------------------------------------------------------------
# Reads every selected file, checks it has all expected columns, trims stray spaces from text, and stacks them into one table with the file's date and n
# ----------------------------------------------------------------------
def read_csv_robust(path):
    try:
        return pd.read_csv(path, encoding="utf-8", dtype=str)
    except UnicodeDecodeError:
        print(f"Note: {os.path.basename(path)} is not UTF-8 - reading as latin1.")
        return pd.read_csv(path, encoding="latin1", dtype=str)

frames = []
for f, d in file_dates.items():
    df = read_csv_robust(f)
    missing = set(EXPECTED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"{os.path.basename(f)} is missing column(s) {sorted(missing)}. Found: {list(df.columns)}")
    df = df[EXPECTED_COLUMNS].copy()
    for col in ["SKU", "Marketplace", "Seller_name", "region"]:
        df[col] = df[col].str.strip()
    df["file_date"], df["source_file"] = d, os.path.basename(f)
    frames.append(df)
combined = pd.concat(frames, ignore_index=True)
print(f"Rows read: {len(combined):,} from {len(frames)} file(s); dates {min(file_dates.values())} to {max(file_dates.values())}")
combined.groupby("file_date").size().rename("rows").to_frame().T

# ----------------------------------------------------------------------
# Converts `adv_price` text such as `1,249.00` or `$ 12.50` into a number. Rows that cannot be converted become empty and are caught by the checks below
# ----------------------------------------------------------------------
combined["adv_price_raw"] = combined["adv_price"]
cleaned = (combined["adv_price"].astype(str).str.replace(",", "", regex=False).str.replace(r"[^0-9.\-]", "", regex=True))
combined["adv_price"] = pd.to_numeric(cleaned, errors="coerce")
print("Prices that could not be read:", int(combined["adv_price"].isna().sum()))
combined[["SKU", "adv_price_raw", "adv_price"]].head()

# ----------------------------------------------------------------------
# Loads the list of valid SKUs from `SKU_TABLE` and runs the four checks, producing a clean set and a quarantine set. Prints each problem found with its
# ----------------------------------------------------------------------
with engine.connect() as conn:
    valid_skus = set(pd.read_sql(text("SELECT SKU FROM SKU_TABLE"), conn)["SKU"])
if not valid_skus:
    raise RuntimeError("SKU_TABLE is empty. Run notebook 02 first.")

df = combined
null_sku   = df["SKU"].isna() | (df["SKU"] == "")
bad_price  = df["adv_price"].isna() | (df["adv_price"] <= 0)
dup_day    = df.duplicated(["file_date", "SKU", "Marketplace", "Seller_name", "region"], keep=False) & ~null_sku
orphan     = ~df["SKU"].isin(valid_skus) & ~null_sku

reason = pd.Series("", index=df.index)
for mask, label in [(null_sku, "missing SKU"), (bad_price, "price missing/invalid/not positive"),
                    (dup_day, "duplicate within the same day's file"), (orphan, "SKU not in SKU_TABLE")]:
    reason = reason.mask(mask, reason + label + "; ")
    print(f"{label:<40}: {int(mask.sum()):>7,} row(s)")

bad_mask = null_sku | bad_price | dup_day | orphan
clean_df = df[~bad_mask].copy()
quarantined_df = df[bad_mask].assign(quarantine_reason=reason[bad_mask].str.rstrip("; "))
print(f"\nClean rows: {len(clean_df):,} | quarantined rows: {len(quarantined_df):,}")

# ----------------------------------------------------------------------
# Saves the quarantined rows (with the reason) to a CSV in `outputs/reports/` and shows the first few.
# ----------------------------------------------------------------------
if len(quarantined_df):
    qpath = os.path.join(mc.REPORT_DIR, f"quarantined_rows_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    quarantined_df.to_csv(qpath, index=False)
    print("Quarantine file:", os.path.relpath(qpath, mc.PROJECT_DIR))
else:
    print("Nothing quarantined.")
quarantined_df[["file_date", "SKU", "Marketplace", "Seller_name", "region", "adv_price_raw", "quarantine_reason"]].head(10)

# ----------------------------------------------------------------------
# Creates `SELLER_PRICE_OBSERVATIONS` if it does not exist: a primary key, a link to `SKU_TABLE`, and a rule that the same seller/product/marketplace/re
# ----------------------------------------------------------------------
with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS SELLER_PRICE_OBSERVATIONS (
            observation_id  INT AUTO_INCREMENT PRIMARY KEY,
            file_date       DATE NOT NULL,
            SKU             VARCHAR(50) NOT NULL,
            Marketplace     VARCHAR(150) COLLATE utf8mb4_bin,
            Seller_name     VARCHAR(255) COLLATE utf8mb4_bin,
            region          VARCHAR(50)  COLLATE utf8mb4_bin,
            adv_price       DECIMAL(12,2),
            adv_price_raw   VARCHAR(50),
            Screenshot      VARCHAR(500),
            live_link       VARCHAR(1000),
            source_file     VARCHAR(255),
            CONSTRAINT FK_SELLERPRICE_SKU FOREIGN KEY (SKU) REFERENCES SKU_TABLE(SKU),
            CONSTRAINT UQ_SELLERPRICE_DAY UNIQUE (file_date, SKU, Marketplace, Seller_name, region)
        ) ENGINE=InnoDB"""))
print("SELLER_PRICE_OBSERVATIONS is ready.")

# ----------------------------------------------------------------------
# Loads the clean rows. First it deletes any rows already stored for the same days (if `REPLACE_EXISTING_DAYS` is on, otherwise it stops if a day exists
# ----------------------------------------------------------------------
load_cols = ["file_date", "SKU", "Marketplace", "Seller_name", "region", "adv_price", "adv_price_raw",
             "Screenshot", "live_link", "source_file"]
dates = sorted(clean_df["file_date"].unique())
with engine.begin() as conn:
    existing = pd.read_sql(text("SELECT file_date, COUNT(*) AS n FROM SELLER_PRICE_OBSERVATIONS GROUP BY file_date"), conn)
    existing["file_date"] = pd.to_datetime(existing["file_date"]).dt.date
    clash = existing[existing["file_date"].isin(dates)]
    if len(clash) and not REPLACE_EXISTING_DAYS:
        raise RuntimeError(f"{len(clash)} day(s) already loaded: {clash['file_date'].tolist()}. "
                           f"Set REPLACE_EXISTING_DAYS = True to reload them.")
    if len(clash):
        print(f"Replacing {len(clash)} day(s) already in the table ({int(clash['n'].sum()):,} old rows).")
        conn.execute(text("DELETE FROM SELLER_PRICE_OBSERVATIONS WHERE file_date IN :d").bindparams(
            __import__("sqlalchemy").bindparam("d", expanding=True)), {"d": dates})
    clean_df[load_cols].to_sql("SELLER_PRICE_OBSERVATIONS", con=conn, if_exists="append", index=False,
                               chunksize=1000, method="multi")
print(f"Loaded {len(clean_df):,} rows for {len(dates)} day(s).")

# ----------------------------------------------------------------------
# Checks the table: total rows, rows per day, same-day duplicates (must be 0) and SKUs unknown to the master list (must be 0).
# ----------------------------------------------------------------------
with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM SELLER_PRICE_OBSERVATIONS")).scalar()
    by_day = pd.read_sql(text("SELECT file_date, COUNT(*) AS rows_loaded FROM SELLER_PRICE_OBSERVATIONS GROUP BY file_date ORDER BY file_date"), conn)
    dups = conn.execute(text("""SELECT COUNT(*) FROM (SELECT 1 FROM SELLER_PRICE_OBSERVATIONS
        GROUP BY file_date, SKU, Marketplace, Seller_name, region HAVING COUNT(*) > 1) t""")).scalar()
    orphans = conn.execute(text("""SELECT COUNT(*) FROM SELLER_PRICE_OBSERVATIONS o LEFT JOIN SKU_TABLE s ON o.SKU = s.SKU
        WHERE s.SKU IS NULL""")).scalar()
print(f"Total rows in SELLER_PRICE_OBSERVATIONS: {total:,}")
print(f"Same-day duplicate groups (should be 0): {dups} | unknown SKUs (should be 0): {orphans}")
expected = len(clean_df)
loaded_now = int(by_day[by_day['file_date'].isin(dates)]['rows_loaded'].sum())
print(f"Rows loaded this run: expected {expected:,}, found {loaded_now:,} ->", "OK" if expected == loaded_now else "MISMATCH")
by_day

# ----------------------------------------------------------------------
# Lists seller names that appear in the price files but have no entry in `SELLERMAPPING_TABLE`, with how many observations each has. Saves the list to a
# ----------------------------------------------------------------------
with engine.connect() as conn:
    unmapped = pd.read_sql(text("""
        SELECT o.Seller_name, COUNT(*) AS observations, COUNT(DISTINCT o.Marketplace) AS marketplaces
        FROM SELLER_PRICE_OBSERVATIONS o
        LEFT JOIN (SELECT DISTINCT SSELLERS_NAME FROM SELLERMAPPING_TABLE) m ON m.SSELLERS_NAME = o.Seller_name COLLATE utf8mb4_bin
        WHERE m.SSELLERS_NAME IS NULL
        GROUP BY o.Seller_name ORDER BY observations DESC"""), conn)
if len(unmapped):
    path = os.path.join(mc.REPORT_DIR, "sellers_missing_from_mapping.csv"); unmapped.to_csv(path, index=False)
    print(f"{len(unmapped)} seller name(s) are not in SELLERMAPPING_TABLE -> {os.path.relpath(path, mc.PROJECT_DIR)}")
else:
    print("Every seller name in the price files is in the seller mapping.")
unmapped.head(15)

# ----------------------------------------------------------------------
# Saves a backup of the database to Drive.
# ----------------------------------------------------------------------
mc.db_backup()
