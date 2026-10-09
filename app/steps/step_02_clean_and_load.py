"""AUTO-GENERATED from 02_Data_Cleaning_and_MySQL_Tables.ipynb by build_steps.py - edit the notebook and regenerate, not this file."""
# ----------------------------------------------------------------------
# Connects Google Drive, finds your project folder and loads the shared helper module `map_common`.
# ----------------------------------------------------------------------
import os
import map_common as mc          # run_step.py has already put the project folder on the import path
mc.ensure_dirs()
print("Project folder:", mc.PROJECT_DIR)

# ----------------------------------------------------------------------
# Defines every setting that drives the cleaning: file names, the LPP percentage table, the code-to-name mappings for category and sub-category, the qua
# ----------------------------------------------------------------------
FILES = {
    "sku":      "SKU Table.xml",
    "pl":       "PL Table.json",
    "pricelist":"Price List Table.yaml",
    "seller":   "Seller Mapping Table.xlsx",
    "promo":    "Promotion Table.xlsx",
}

# LPP = MAP x (1 - pct/100); pct depends on the company in the product line (HP or DELL) and the sub-category
LPP_LOGIC = {  # sub-category: (HP %, DELL %)
    "LAPTOP": (3.4, 7.8), "MONITOR": (1.2, 5.6), "TONNER": (9.1, 2.3), "LASERJET": (6.5, 3.5),
    "INKJET": (1.2, 5.6), "DESKTOP": (9.1, 2.3), "INK": (6.5, 3.5),
}

# Product line looks like HP8L_PC_Desktop  ->  company 'HP' (code HP8L minus its last 2 chars), category 'PC', type 'Desktop'
CATEGORY_MAP    = {"SUP": "SUPPLY", "PC": "PC", "PH": "PRINTHARDWARE"}
SUBCATEGORY_MAP = {"INK": "INK", "Laptop": "LAPTOP", "TON": "TONNER", "Desktop": "DESKTOP", "IJ": "INKJET",
                   "LJ": "LASERJET", "Monitor": "MONITOR", "UNK": "INK", "SJ": "SCANNER"}

# Offer grid (from the manufacturer's offer table). Quarter columns follow the fiscal calendar.
OFFER_GRID = {
    "Category":     ["Supply",       "Print Hardware",     "PC"],
    "Q1 (Nov-Jan)": ["10% off ink",  "15% off ink jet",    "$10 off laptops"],
    "Q2 (Feb-Apr)": ["$2 off toner", "Free setup service", "Free accessories"],
    "Q3 (May-Jul)": ["5% off toner", "2% off scanners",    "Free accessories"],
    "Q4 (Aug-Oct)": ["20% off ink",  "$10 off laser jet",  "15 % off"],
}
OFFER_CATEGORY_MAP = {"Supply": "SUPPLY", "PC": "PC", "Print Hardware": "PRINTHARDWARE"}
OFFER_SUBCATEGORY_MAP = {"ink": "INK", "laptops": "LAPTOP", "toner": "TONNER", "setup service": "setup service",
                         "ink jet": "INKJET", "laser jet": "LASERJET", "accessories": "accessories", "scanners": "SCANNER"}

# These SKUs appear twice with two different product lines. The pair listed here is the WRONG one and is removed
# (the assumption recorded in the project: L = laptop, D = desktop). Review with the manufacturer if in doubt.
CONFLICT_PAIRS_TO_REMOVE = [("8L129PA", "HP8L_PC_Desktop"), ("8L130PA", "HP8L_PC_Desktop"),
                            ("8L120PA", "HP8L_PC_Desktop"), ("8F6D4PA", "HP8F_PC_Laptop")]

# Promotion SKU list: Excel column B, rows 16 to 115 (100 rows)
PROMO_SKU_COLUMN, PROMO_SKIP_ROWS, PROMO_NROWS = "B", 15, 100
print("Configuration loaded.")
LPP_LOGIC = {k: tuple(v) for k, v in _ov("LPP_LOGIC", LPP_LOGIC).items()}
print("LPP table in use:", LPP_LOGIC)

# ----------------------------------------------------------------------
# Reads `SKU Table.xml` into a table and shows its size, empty cells and any SKU that appears more than once.
# ----------------------------------------------------------------------
import json, yaml
import numpy as np
import pandas as pd

df_sku = pd.read_xml(mc.find_raw(FILES["sku"]))
df_sku["Sku"] = df_sku["Sku"].astype(str).str.strip()
print("SKU rows:", len(df_sku), "| columns:", list(df_sku.columns))
print("Empty cells:\n", df_sku.isnull().sum().to_string())
dups = df_sku[df_sku.duplicated("Sku", keep=False)]
print(f"\nSKUs that appear more than once: {dups['Sku'].nunique()} ({len(dups)} rows)")
dups.head(10)

# ----------------------------------------------------------------------
# Reads `PL Table.json` (one JSON record per line) into a table.
# ----------------------------------------------------------------------
records = []
with open(mc.find_raw(FILES["pl"]), "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))
df_pl = pd.DataFrame(records)
df_pl["sku"] = df_pl["sku"].astype(str).str.strip()
print("PL rows:", len(df_pl), "| columns:", list(df_pl.columns))
print("Empty cells:\n", df_pl.isnull().sum().to_string())
print(f"SKUs appearing more than once: {df_pl.loc[df_pl['sku'].duplicated(), 'sku'].nunique()}")
df_pl.head()

# ----------------------------------------------------------------------
# Reads `Price List Table.yaml` (MAP price per SKU and product line).
# ----------------------------------------------------------------------
with open(mc.find_raw(FILES["pricelist"]), "r", encoding="utf-8") as f:
    df_price = pd.DataFrame(yaml.safe_load(f))
df_price["sku"] = df_price["sku"].astype(str).str.strip()
df_price["MAP"] = pd.to_numeric(df_price["MAP"], errors="coerce")
print("Price list rows:", len(df_price), "| columns:", list(df_price.columns))
print("Empty cells:\n", df_price.isnull().sum().to_string())
print(df_price["MAP"].describe().round(2).to_string())

# ----------------------------------------------------------------------
# Reads `Seller Mapping Table.xlsx` and trims stray spaces from the seller names.
# ----------------------------------------------------------------------
df_seller = pd.read_excel(mc.find_raw(FILES["seller"]))
for col in ["Ssellers_name", "homologated_sellers"]:
    df_seller[col] = df_seller[col].astype(str).str.strip()
print("Seller mapping rows:", len(df_seller), "| distinct spellings:", df_seller["Ssellers_name"].nunique(),
      "| distinct recognised sellers:", df_seller["homologated_sellers"].nunique())
df_seller.head()

# ----------------------------------------------------------------------
# Splits each product line code into Company / Category / Sub-category, translates the short codes into full names, and reports any code that was not re
# ----------------------------------------------------------------------
parts = df_pl["PL"].str.split("_", expand=True)
if parts.shape[1] != 3:
    raise ValueError(f"Expected product lines like 'HP8L_PC_Desktop' (3 parts split by '_'); got {parts.shape[1]} parts. Check PL Table.json.")
df_pl[["Company", "Category", "Subcategory"]] = parts
df_pl["Company"] = df_pl["Company"].str[:-2]                      # 'HP8L' -> 'HP'
raw_cat, raw_sub = df_pl["Category"].copy(), df_pl["Subcategory"].copy()
df_pl["Category"] = raw_cat.map(CATEGORY_MAP)
df_pl["Subcategory"] = raw_sub.map(SUBCATEGORY_MAP)

for label, raw, mapped in [("category", raw_cat, df_pl["Category"]), ("sub-category", raw_sub, df_pl["Subcategory"])]:
    unknown = sorted(raw[mapped.isna()].unique())
    print(f"Unrecognised {label} codes: {unknown if unknown else 'none'}")
print("Companies found:", sorted(df_pl["Company"].unique()))
print()
print(df_pl[["Category", "Subcategory"]].value_counts().sort_index(level=0).to_string())

# ----------------------------------------------------------------------
# Removes the four SKU / product-line pairs that conflict (the same SKU listed under two product lines) from the product-line data, and keeps only the f
# ----------------------------------------------------------------------
before_sku, before_pl, before_price = len(df_sku), len(df_pl), len(df_price)

# SKU table: keep first occurrence
removed_sku = df_sku[df_sku.duplicated("Sku", keep="first")]
df_sku = df_sku.drop_duplicates("Sku", keep="first").reset_index(drop=True)

# Product line + price list: remove the known wrong pairs
bad = pd.MultiIndex.from_tuples(CONFLICT_PAIRS_TO_REMOVE)
df_pl    = df_pl[~df_pl.set_index(["sku", "PL"]).index.isin(bad)].reset_index(drop=True)
df_price = df_price[~df_price.set_index(["sku", "PL"]).index.isin(bad)].reset_index(drop=True)

print(f"SKU table      : {before_sku} -> {len(df_sku)}  (removed {len(removed_sku)} repeated SKU row(s))")
print(f"Product lines  : {before_pl} -> {len(df_pl)}")
print(f"Price list     : {before_price} -> {len(df_price)}")

# Everything must now be unique per SKU - stop with a clear message if not
for name, frame, col in [("SKU table", df_sku, "Sku"), ("Product lines", df_pl, "sku"), ("Price list", df_price, "sku")]:
    still = frame.loc[frame[col].duplicated(), col].unique()
    if len(still):
        raise ValueError(f"{name} still has repeated SKUs after cleaning: {list(still)[:10]}. "
                         f"Add the wrong (sku, PL) pair to CONFLICT_PAIRS_TO_REMOVE.")
print("Uniqueness check passed: one row per SKU in every table.")

# ----------------------------------------------------------------------
# Calculates the LPP for every SKU: looks up the percentage for its company and sub-category, then `LPP = MAP x (1 - percentage / 100)`, rounded to 2 de
# ----------------------------------------------------------------------
lpp_table = pd.DataFrame([{"Subcategory": k, "HP": v[0], "DELL": v[1]} for k, v in LPP_LOGIC.items()])
m = df_price.merge(df_pl[["sku", "Company", "Category", "Subcategory"]], on="sku", how="left", indicator=True)
print("Price-list rows with no product-line match:", int((m["_merge"] != "both").sum()))

m = m.merge(lpp_table, on="Subcategory", how="left")
m["LPP_Percentage"] = [row[row["Company"]] if row["Company"] in ("HP", "DELL") else np.nan for _, row in m.iterrows()]
m["LPP_Percentage"] = pd.to_numeric(m["LPP_Percentage"], errors="coerce")
m["LPP"] = (m["MAP"] * (1 - m["LPP_Percentage"] / 100)).round(2)

no_rule = m[m["LPP"].isna()]
print(f"SKUs without an LPP (no rule for their company/sub-category or no MAP): {len(no_rule)}")
if len(no_rule):
    print(no_rule[["sku", "PL", "Company", "Subcategory", "MAP"]].head(15).to_string(index=False))
df_pricelist = m[["PL", "sku", "MAP", "LPP"]].copy()
df_pricelist.head()

# ----------------------------------------------------------------------
# Turns the offer grid into one row per quarter and category with the offer type extracted: percent off, dollar off, or a non-price perk (free service/a
# ----------------------------------------------------------------------
grid = pd.DataFrame(OFFER_GRID)
long = grid.melt(id_vars="Category", var_name="Quarter", value_name="Offer")
qm = long["Quarter"].str.extract(r"(Q\d)\s*\(([^)]+)\)")
long["Quarter"], long["Month"] = qm[0], qm[1]

long["OFFER_PCT"] = long["Offer"].str.extract(r"(\d+(?:\.\d+)?)\s*%")[0].astype(float)
long["DOLLAR"] = long["Offer"].str.extract(r"\$\s*([\d,.]+)")[0].str.replace(",", "", regex=False).astype(float)
sub = (long["Offer"]
       .str.replace(r"^\s*\d+(?:\.\d+)?\s*%\s*off\s*", "", regex=True)
       .str.replace(r"^\s*\$\s*[\d,.]+\s*off\s*", "", regex=True)
       .str.replace(r"^\s*Free\s*", "", regex=True, case=False).str.strip())
long["Subcategory"] = sub.replace("", pd.NA)
long["Category"] = long["Category"].map(OFFER_CATEGORY_MAP)
long["Subcategory"] = long["Subcategory"].map(OFFER_SUBCATEGORY_MAP).where(long["Subcategory"].notna(), pd.NA)
long["Offer type"] = np.where(long["OFFER_PCT"].notna(), "percent off", np.where(long["DOLLAR"].notna(), "dollar off", "non-price perk"))
df_offers = long[["Category", "Subcategory", "Quarter", "Month", "Offer", "OFFER_PCT", "DOLLAR", "Offer type"]]
df_offers

# ----------------------------------------------------------------------
# Reads the list of SKUs on promotion from the Excel file (column B, rows 16-115) and joins them to the offers: a SKU gets an offer when its category + 
# ----------------------------------------------------------------------
promo_skus = pd.read_excel(mc.find_raw(FILES["promo"]), usecols=PROMO_SKU_COLUMN, skiprows=PROMO_SKIP_ROWS,
                           nrows=PROMO_NROWS, header=None)
promo_skus.columns = ["sku"]
promo_skus = promo_skus.dropna().astype({"sku": str})
promo_skus["sku"] = promo_skus["sku"].str.strip()
promo_skus = promo_skus.drop_duplicates()
print("SKUs on the promotion list:", len(promo_skus))

base = promo_skus.merge(df_pl[["sku", "PL", "Category", "Subcategory"]], on="sku", how="left")
print("Promotion SKUs with no product line (will get no offer):", int(base["PL"].isna().sum()))

specific = base.merge(df_offers[df_offers["Subcategory"].notna()][["Category", "Subcategory", "Quarter", "OFFER_PCT", "DOLLAR"]],
                      on=["Category", "Subcategory"], how="inner")
catwide  = base.merge(df_offers[df_offers["Subcategory"].isna()][["Category", "Quarter", "OFFER_PCT", "DOLLAR"]],
                      on="Category", how="inner")
df_promotion = pd.concat([specific, catwide], ignore_index=True)[["PL", "sku", "Quarter", "OFFER_PCT", "DOLLAR"]]

# one promotion per SKU and quarter (the table's primary key)
dup_promo = df_promotion.duplicated(["sku", "Quarter"], keep=False)
if dup_promo.any():
    print(f"WARNING: {int(dup_promo.sum())} rows give a SKU two offers in the same quarter - keeping the first.")
    df_promotion = df_promotion.drop_duplicates(["sku", "Quarter"], keep="first")
df_promotion = df_promotion.reset_index(drop=True)
print("Promotion rows:", len(df_promotion))
print(df_promotion.groupby("Quarter").agg(rows=("sku", "size"), pct_offers=("OFFER_PCT", "count"), dollar_offers=("DOLLAR", "count")).to_string())
df_promotion.head()

# ----------------------------------------------------------------------
# Assembles the six final tables with upper-case column names, removes the helper columns, and checks that every SKU in a child table exists in the SKU 
# ----------------------------------------------------------------------
t_sku  = df_sku[["PN", "Sku"]].rename(columns=str.upper) if "PN" in df_sku.columns else df_sku.rename(columns=str.upper)
t_sku  = t_sku[["PN", "SKU"]]
t_pl   = df_pl[["sku", "PL", "Subcategory"]].rename(columns=str.upper)
t_price= df_pricelist.rename(columns=str.upper)[["PL", "SKU", "MAP", "LPP"]]
t_cat  = df_pl[["Category", "Subcategory", "PL", "sku"]].rename(columns=str.upper)
t_prom = df_promotion.rename(columns={"sku": "SKU", "Quarter": "QUARTER"})[["PL", "SKU", "QUARTER", "OFFER_PCT", "DOLLAR"]]
t_sell = df_seller.rename(columns={"Ssellers_name": "SSELLERS_NAME", "homologated_sellers": "HOMOLOGATED_SELLERS"})
t_sell = t_sell[["SSELLERS_NAME", "HOMOLOGATED_SELLERS"]].drop_duplicates("SSELLERS_NAME").reset_index(drop=True)

TABLES = {"SKU_TABLE": t_sku, "PRODUCTLINE_TABLE": t_pl, "PRICELIST_TABLE": t_price,
          "CATEGORYMAPPING_TABLE": t_cat, "PROMOTION_TABLE": t_prom, "SELLERMAPPING_TABLE": t_sell}

valid = set(t_sku["SKU"])
for name in ["PRODUCTLINE_TABLE", "PRICELIST_TABLE", "CATEGORYMAPPING_TABLE", "PROMOTION_TABLE"]:
    orphans = TABLES[name][~TABLES[name]["SKU"].isin(valid)]
    if len(orphans):
        print(f"WARNING {name}: {len(orphans)} row(s) reference a SKU missing from SKU_TABLE - dropped:", orphans["SKU"].head(5).tolist())
        TABLES[name] = TABLES[name][TABLES[name]["SKU"].isin(valid)].reset_index(drop=True)

print(f"{'table':<24}{'rows':>7}")
for name, frame in TABLES.items():
    print(f"{name:<24}{len(frame):>7}")

# ----------------------------------------------------------------------
# Saves the six tables as CSV files in `cleaned_data/` on your Drive.
# ----------------------------------------------------------------------
import os
for name, frame in TABLES.items():
    path = os.path.join(mc.CLEAN_DIR, f"{name}.csv")
    frame.to_csv(path, index=False)
    print("saved", os.path.relpath(path, mc.PROJECT_DIR))

# ----------------------------------------------------------------------
# Starts MySQL (restoring the Drive backup if this is a new Colab session) and connects.
# ----------------------------------------------------------------------
from sqlalchemy import text
engine = mc.connect_db()

# ----------------------------------------------------------------------
# Creates the six master tables if they do not exist yet, with primary keys, foreign keys to `SKU_TABLE` and exact column types (prices as DECIMAL, neve
# ----------------------------------------------------------------------
DDL = [
"DROP TABLE IF EXISTS SELLERMAPPING_TABLE",   # no dependants, so it is simply rebuilt
"""CREATE TABLE IF NOT EXISTS SKU_TABLE (
    PN  VARCHAR(100),
    SKU VARCHAR(50) NOT NULL,
    PRIMARY KEY (SKU)) ENGINE=InnoDB""",
"""CREATE TABLE IF NOT EXISTS PRODUCTLINE_TABLE (
    SKU VARCHAR(50) NOT NULL, PL VARCHAR(150), SUBCATEGORY VARCHAR(150),
    PRIMARY KEY (SKU),
    CONSTRAINT FK_PRODUCTLINE_SKU FOREIGN KEY (SKU) REFERENCES SKU_TABLE(SKU)) ENGINE=InnoDB""",
"""CREATE TABLE IF NOT EXISTS PRICELIST_TABLE (
    PL VARCHAR(150), SKU VARCHAR(50) NOT NULL, `MAP` DECIMAL(12,2), LPP DECIMAL(12,2),
    PRIMARY KEY (SKU),
    CONSTRAINT FK_PRICELIST_SKU FOREIGN KEY (SKU) REFERENCES SKU_TABLE(SKU)) ENGINE=InnoDB""",
"""CREATE TABLE IF NOT EXISTS CATEGORYMAPPING_TABLE (
    CATEGORY VARCHAR(150), SUBCATEGORY VARCHAR(150), PL VARCHAR(150), SKU VARCHAR(50) NOT NULL,
    PRIMARY KEY (SKU),
    CONSTRAINT FK_CATEGORYMAPPING_SKU FOREIGN KEY (SKU) REFERENCES SKU_TABLE(SKU)) ENGINE=InnoDB""",
"""CREATE TABLE IF NOT EXISTS PROMOTION_TABLE (
    PL VARCHAR(150), SKU VARCHAR(50) NOT NULL, `QUARTER` VARCHAR(10) NOT NULL,
    OFFER_PCT DECIMAL(5,2), DOLLAR DECIMAL(12,2),
    PRIMARY KEY (SKU, `QUARTER`),
    CONSTRAINT FK_PROMOTION_SKU FOREIGN KEY (SKU) REFERENCES SKU_TABLE(SKU)) ENGINE=InnoDB""",
"""CREATE TABLE IF NOT EXISTS SELLERMAPPING_TABLE (
    SSELLERS_NAME VARCHAR(255) NOT NULL, HOMOLOGATED_SELLERS VARCHAR(255),
    KEY IX_SELLERMAP_NAME (SSELLERS_NAME)) ENGINE=InnoDB""",
]
with engine.begin() as conn:
    for stmt in DDL:
        conn.execute(text(stmt))
print("Tables ready:", mc.table_count(engine))

# ----------------------------------------------------------------------
# Empties the six master tables (foreign-key checks switched off only for this moment) and loads the cleaned data in the right order: SKU table first, t
# ----------------------------------------------------------------------
ORDER = ["SKU_TABLE", "PRODUCTLINE_TABLE", "PRICELIST_TABLE", "CATEGORYMAPPING_TABLE", "PROMOTION_TABLE", "SELLERMAPPING_TABLE"]
with engine.begin() as conn:
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
    for name in reversed(ORDER):
        conn.execute(text(f"DELETE FROM `{name}`"))
    conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

for name in ORDER:
    TABLES[name].to_sql(name, con=engine, if_exists="append", index=False, chunksize=1000, method="multi")
    print(f"loaded {len(TABLES[name]):>5} rows into {name}")

# ----------------------------------------------------------------------
# Counts the rows in every table, checks they match the CSVs, tests for orphan SKUs and previews a few joined rows.
# ----------------------------------------------------------------------
with engine.connect() as conn:
    print(f"{'table':<24}{'in MySQL':>10}{'in CSV':>9}   status")
    for name in ORDER:
        n_db = conn.execute(text(f"SELECT COUNT(*) FROM `{name}`")).scalar()
        ok = "OK" if n_db == len(TABLES[name]) else "MISMATCH"
        print(f"{name:<24}{n_db:>10}{len(TABLES[name]):>9}   {ok}")
    orphan = conn.execute(text("""SELECT COUNT(*) FROM PRICELIST_TABLE p LEFT JOIN SKU_TABLE s ON p.SKU = s.SKU WHERE s.SKU IS NULL""")).scalar()
    print("\nPrice-list rows with an unknown SKU (should be 0):", orphan)
    no_price = conn.execute(text("""SELECT COUNT(*) FROM SKU_TABLE s LEFT JOIN PRICELIST_TABLE p ON p.SKU = s.SKU WHERE p.SKU IS NULL""")).scalar()
    print("SKUs that have no price list entry (cannot be monitored):", no_price)
    sample = pd.read_sql(text("""SELECT c.SKU, c.CATEGORY, c.SUBCATEGORY, p.`MAP`, p.LPP FROM CATEGORYMAPPING_TABLE c
                                 JOIN PRICELIST_TABLE p ON p.SKU = c.SKU LIMIT 8"""), conn)
sample

# ----------------------------------------------------------------------
# Saves a backup of the whole database to Drive.
# ----------------------------------------------------------------------
mc.db_backup()
