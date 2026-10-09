"""AUTO-GENERATED from 05_MAP_LPP_Compliance_Logic.ipynb by build_steps.py - edit the notebook and regenerate, not this file."""
# ----------------------------------------------------------------------
# Connects Google Drive, finds your project folder and loads the shared helper module `map_common`.
# ----------------------------------------------------------------------
import os
import map_common as mc          # run_step.py has already put the project folder on the import path
mc.ensure_dirs()
print("Project folder:", mc.PROJECT_DIR)

# ----------------------------------------------------------------------
# Starts MySQL (restoring the Drive backup in a new Colab session) and connects.
# ----------------------------------------------------------------------
import numpy as np
import pandas as pd
from sqlalchemy import text
engine = mc.connect_db()

# ----------------------------------------------------------------------
# Settings: quarter definition, base currency, which currency dollar promotions are quoted in, and the mapping from region name to currency.
# ----------------------------------------------------------------------
QUARTER_MODE = _ov("QUARTER_MODE", "fiscal")          # "fiscal" (Nov-Jan = Q1 ...) matches the offer grid | "calendar" (Jan-Mar = Q1 ...)
BASE_CURRENCY = "INR"            # MAP and LPP are stored in this currency
DOLLAR_PROMO_CURRENCY = "USD"    # '$10 off' means 10 US dollars
FORCE_FX_REFRESH = _ov("FORCE_FX_REFRESH", False)         # True = ignore today's saved rates and fetch again
REGION_TO_CURRENCY = {"USA": "USD", "US": "USD", "UK": "GBP", "GB": "GBP", "UAE": "AED",
                      "CAN": "CAD", "CANADA": "CAD", "IN": "INR", "IND": "INR", "INDIA": "INR"}
assert QUARTER_MODE in ("fiscal", "calendar")
print("Quarter mode:", QUARTER_MODE)

# ----------------------------------------------------------------------
# Gets exchange rates (units of each currency per 1 INR) from the shared helper, which saves a snapshot per day and falls back to older/built-in rates i
# ----------------------------------------------------------------------
fx_rates, fx_source = mc.get_fx_rates(BASE_CURRENCY, FORCE_FX_REFRESH)
print("FX source:", fx_source)
print({k: round(fx_rates[k], 6) for k in sorted(set(REGION_TO_CURRENCY.values())) if k in fx_rates})
missing_ccy = sorted(set(REGION_TO_CURRENCY.values()) - set(fx_rates))
if missing_ccy:
    print("WARNING: no exchange rate for", missing_ccy, "- rows in those regions cannot be judged")
if "BUILT-IN" in fx_source or "OLDER" in fx_source:
    print("NOTE: not today's live rates - results are approximate. Re-run later with internet access for exact rates.")

# ----------------------------------------------------------------------
# Reads the observations and the master tables (category, price list with MAP/LPP, seller mapping, promotions) from MySQL.
# ----------------------------------------------------------------------
with engine.connect() as conn:
    obs       = pd.read_sql(text("SELECT * FROM SELLER_PRICE_OBSERVATIONS"), conn)
    catmap    = pd.read_sql(text("SELECT SKU, CATEGORY, SUBCATEGORY, PL FROM CATEGORYMAPPING_TABLE"), conn)
    pricelist = pd.read_sql(text("SELECT SKU, `MAP` AS MAP_Price, LPP FROM PRICELIST_TABLE"), conn)
    sellermap = pd.read_sql(text("SELECT SSELLERS_NAME AS Seller_name, HOMOLOGATED_SELLERS AS homologated_name FROM SELLERMAPPING_TABLE"), conn)
    promo     = pd.read_sql(text("SELECT SKU, `QUARTER` AS Season, OFFER_PCT, DOLLAR FROM PROMOTION_TABLE"), conn)
if obs.empty:
    raise RuntimeError("SELLER_PRICE_OBSERVATIONS is empty. Run notebook 04 first.")
for frame, cols in [(obs, ["adv_price"]), (pricelist, ["MAP_Price", "LPP"]), (promo, ["OFFER_PCT", "DOLLAR"])]:
    for c in cols:
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
obs["file_date"] = pd.to_datetime(obs["file_date"])
sellermap = sellermap.drop_duplicates("Seller_name", keep="first")   # one recognised name per spelling
print(f"Observations {len(obs):,} | category rows {len(catmap):,} | price list {len(pricelist):,} | "
      f"seller spellings {len(sellermap):,} | promotions {len(promo):,}")

# ----------------------------------------------------------------------
# Labels each observation with its quarter (Q1-Q4) using the chosen quarter definition and shows how many observations fall in each.
# ----------------------------------------------------------------------
month = obs["file_date"].dt.month
if QUARTER_MODE == "fiscal":
    q = ((month - 11) % 12) // 3 + 1          # Nov,Dec,Jan -> 1 ; Feb-Apr -> 2 ; May-Jul -> 3 ; Aug-Oct -> 4
else:
    q = obs["file_date"].dt.quarter
obs["Season"] = "Q" + q.astype(str)
print(obs.groupby("Season")["file_date"].agg(["count", "min", "max"]).to_string())

# ----------------------------------------------------------------------
# Joins the observations to category, MAP/LPP, recognised seller name and the promotion for that SKU and quarter. Checks that the joins did not add or l
# ----------------------------------------------------------------------
n0 = len(obs)
pm = obs.merge(catmap, on="SKU", how="left")
pm = pm.merge(pricelist, on="SKU", how="left")
pm = pm.merge(sellermap, on="Seller_name", how="left")
pm = pm.merge(promo, on=["SKU", "Season"], how="left")
assert len(pm) == n0, f"Joins changed the row count ({n0} -> {len(pm)}): a master table has duplicate keys."
print("Rows:", f"{len(pm):,}", "(unchanged by joins)")
print("Rows without category mapping :", int(pm["CATEGORY"].isna().sum()))
print("Rows without a price list entry:", int(pm["MAP_Price"].isna().sum()))
print("Rows without LPP               :", int(pm["LPP"].isna().sum()))
print("Rows with seller not in mapping:", int(pm["homologated_name"].isna().sum()), "(raw seller name is used for strikes)")
print("Rows with an active promotion  :", int((pm["OFFER_PCT"].fillna(0).gt(0) | pm["DOLLAR"].fillna(0).gt(0)).sum()))

# ----------------------------------------------------------------------
# Defines `calc_promo()` - the promotional price: percent offer → `MAP × (1 − pct/100)`; dollar offer → `MAP − dollar ÷ USD-per-INR`; no price offer → e
# ----------------------------------------------------------------------
def calc_promo(map_price, pct, dollar, usd_per_base):
    """Returns (promotional_price, dollar_discount_in_base_currency). Empty (NaN) when no price-based offer applies.
    Dollar offers take precedence over percent offers if a row somehow has both."""
    has_dol = dollar.fillna(0) > 0
    has_pct = (pct.fillna(0) > 0) & ~has_dol
    dol_base = (dollar / usd_per_base).round(2).where(has_dol)
    price = pd.Series(np.nan, index=map_price.index)
    price = price.mask(has_dol, map_price - dol_base)
    price = price.mask(has_pct, map_price * (1 - pct / 100))
    return price.clip(lower=0).round(2), dol_base

# --- hand-worked tests: 10% off 1000 = 900 | $10 at 0.01 USD per INR = 1000 INR off | no offer = empty
t = pd.DataFrame({"map": [1000.0, 5000.0, 1000.0, 1000.0], "pct": [10.0, np.nan, np.nan, np.nan], "dol": [np.nan, 10.0, 0.0, np.nan]})
tp, td = calc_promo(t["map"], t["pct"], t["dol"], 0.01)
assert tp.iloc[0] == 900.0 and tp.iloc[1] == 4000.0 and np.isnan(tp.iloc[2]) and np.isnan(tp.iloc[3]), tp.tolist()
assert td.iloc[1] == 1000.0
print("calc_promo hand tests passed")

usd = fx_rates[DOLLAR_PROMO_CURRENCY]
pm["Promotional_price"], pm["promo_dollar_base"] = calc_promo(pm["MAP_Price"], pm["OFFER_PCT"], pm["DOLLAR"], usd)
pm["fx_rate_used"] = np.where(pm["promo_dollar_base"].notna(), usd, np.nan)
print("Rows with a promotional price:", int(pm["Promotional_price"].notna().sum()),
      "| percent:", int((pm["OFFER_PCT"].fillna(0).gt(0) & pm["promo_dollar_base"].isna()).sum()),
      "| dollar:", int(pm["promo_dollar_base"].notna().sum()))

# ----------------------------------------------------------------------
# Converts each advertised price from the seller's local currency to INR: finds the currency from the region, divides by the rate (units per 1 INR), and
# ----------------------------------------------------------------------
pm["currency_local"] = pm["region"].astype(str).str.strip().str.upper().map(REGION_TO_CURRENCY)
unknown_regions = sorted(pm.loc[pm["currency_local"].isna(), "region"].dropna().unique())
if unknown_regions:
    print("WARNING: no currency for region(s):", unknown_regions, "- add them to REGION_TO_CURRENCY (these rows cannot be judged)")
rate = pm["currency_local"].map(fx_rates)
pm["Advertised_price_base"] = (pm["adv_price"] / rate.where(rate > 0)).round(2)
print("Rows converted:", int(pm["Advertised_price_base"].notna().sum()), "of", len(pm))
pm.groupby("currency_local", dropna=False)["Advertised_price_base"].describe()[["count", "min", "50%", "max"]].round(0)

# ----------------------------------------------------------------------
# Defines `classify()` - the decision order above, applied to all rows at once - and tests it on seven hand-worked cases (below LPP, promotion not enoug
# ----------------------------------------------------------------------
R_UNCLASS = "Cannot classify -- missing price data or unmapped currency"
R_LPP     = "Below LPP (hard floor) -- violation regardless of any promotion"
R_MAP     = "Below MAP with no active/sufficient promotion to authorize it"

def classify(adv, map_p, lpp, promo):
    unclass   = adv.isna() | map_p.isna() | lpp.isna()
    below_lpp = adv < lpp
    covered   = promo.notna() & (adv >= promo)
    below_map = adv < map_p
    reason = np.select([unclass, below_lpp, covered, below_map], [R_UNCLASS, R_LPP, "", R_MAP], default="")
    violation = ~unclass & (below_lpp | (~covered & below_map))
    return violation.to_numpy(), pd.Series(reason, index=adv.index).replace("", None).to_numpy(dtype=object)

nan = np.nan
cases = pd.DataFrame([  # adv, MAP, LPP, promo, expected violation, expected reason
    (700,  1000, 800, nan, True,  R_LPP),      # below LPP
    (850,  1000, 800, 900, True,  R_MAP),      # promo exists but price is under even the promo price
    (950,  1000, 800, 900, False, None),       # promotion covers a below-MAP price
    (950,  1000, 800, nan, True,  R_MAP),      # below MAP, no promotion
    (1000, 1000, 800, nan, False, None),       # at MAP
    (nan,  1000, 800, nan, False, R_UNCLASS),  # missing price
    (700,  1000, 800, 600, True,  R_LPP),      # promotion never excuses an LPP breach
], columns=["adv", "map", "lpp", "promo", "exp_v", "exp_r"])
v, r = classify(cases["adv"].astype(float), cases["map"].astype(float), cases["lpp"].astype(float), cases["promo"].astype(float))
assert list(v) == list(cases["exp_v"]), (list(v), list(cases["exp_v"]))
assert [x if x is not None else None for x in r] == list(cases["exp_r"]), list(r)
print("classify hand tests passed:", len(cases), "cases")

# ----------------------------------------------------------------------
# Applies the rules to every observation, then re-checks a random sample of 5,000 rows plus every unclassifiable row with a separate, deliberately simpl
# ----------------------------------------------------------------------
pm["is_violation"], pm["violation_reason"] = classify(pm["Advertised_price_base"], pm["MAP_Price"], pm["LPP"], pm["Promotional_price"])

def classify_row(adv, map_p, lpp, promo):            # the plain, slow reference version
    if pd.isna(adv) or pd.isna(map_p) or pd.isna(lpp):
        return False, R_UNCLASS
    if adv < lpp:
        return True, R_LPP
    if pd.notna(promo) and adv >= promo:
        return False, None
    if adv < map_p:
        return True, R_MAP
    return False, None

check = pd.concat([pm.sample(min(5000, len(pm)), random_state=1), pm[pm["violation_reason"] == R_UNCLASS]]).drop_duplicates()
mismatch = 0
for r_ in check.itertuples():
    exp = classify_row(r_.Advertised_price_base, r_.MAP_Price, r_.LPP, r_.Promotional_price)
    got_reason = r_.violation_reason if isinstance(r_.violation_reason, str) else None   # empty = None
    if (bool(r_.is_violation), got_reason) != exp:
        mismatch += 1
assert mismatch == 0, f"{mismatch} row(s) differ between fast and reference classification"
print(f"Self-check passed on {len(check):,} rows: fast and row-by-row rules agree on every row.")

# ----------------------------------------------------------------------
# Prints the headline numbers (rows judged, violations, split by hard-floor vs MAP breach, rows that cannot be judged) and breaks the unjudgeable rows d
# ----------------------------------------------------------------------
total = len(pm); n_v = int(pm["is_violation"].sum())
n_un = int((pm["violation_reason"] == R_UNCLASS).sum())
print(f"Observations                : {total:,}")
print(f"Violations                  : {n_v:,} ({n_v / total:.1%})")
print(f"   below LPP (hard floor)   : {int((pm['violation_reason'] == R_LPP).sum()):,}")
print(f"   below MAP (no promo cover): {int((pm['violation_reason'] == R_MAP).sum()):,}")
print(f"Cannot be judged            : {n_un:,}")
un = pm[pm["violation_reason"] == R_UNCLASS].copy()
un["cause"] = np.select([un["MAP_Price"].isna(), un["LPP"].isna(), un["currency_local"].isna() | un["Advertised_price_base"].isna()],
                        ["no price list entry (no MAP)", "no LPP rule for this company/sub-category", "unknown region/currency or bad price"], "other")
print("\nCannot-be-judged rows by cause:"); print(un["cause"].value_counts().to_string())

# ----------------------------------------------------------------------
# Saves the list of products that could not be judged (SKU, product line, category, cause, number of observations) to `outputs/reports/unclassifiable_sk
# ----------------------------------------------------------------------
if len(un):
    fix = (un.groupby(["SKU", "PL", "CATEGORY", "SUBCATEGORY", "cause"], dropna=False).size().rename("observations")
             .reset_index().sort_values("observations", ascending=False))
    path = os.path.join(mc.REPORT_DIR, "unclassifiable_skus.csv"); fix.to_csv(path, index=False)
    print(f"{len(fix)} SKU(s) -> {os.path.relpath(path, mc.PROJECT_DIR)}")
else:
    fix = pd.DataFrame(); print("Every observation could be judged.")
fix.head(10)

# ----------------------------------------------------------------------
# Arranges the result into the 21 columns of `PRICE_MONITORING_TABLE`, drops and re-creates that table, and loads all rows.
# ----------------------------------------------------------------------
pm_final = pm.rename(columns={"file_date": "Violation_date", "region": "Region", "Seller_name": "seller_name", "CATEGORY": "Category",
                              "SUBCATEGORY": "Sub_category", "adv_price": "Advertised_price", "MAP_Price": "MAP_Price"})[[
    "SKU", "Violation_date", "PL", "Category", "Sub_category", "Region", "Marketplace", "seller_name", "homologated_name",
    "MAP_Price", "LPP", "Advertised_price", "currency_local", "Advertised_price_base", "Season", "Promotional_price",
    "promo_dollar_base", "fx_rate_used", "is_violation", "violation_reason"]].copy()
pm_final["Violation_date"] = pm_final["Violation_date"].dt.date

with engine.begin() as conn:
    conn.execute(text("DROP TABLE IF EXISTS PRICE_MONITORING_TABLE"))
    conn.execute(text("""
        CREATE TABLE PRICE_MONITORING_TABLE (
            monitoring_id          INT AUTO_INCREMENT PRIMARY KEY,
            SKU                    VARCHAR(50) NOT NULL,
            Violation_date         DATE NOT NULL,
            PL                     VARCHAR(100),
            Category               VARCHAR(100),
            Sub_category           VARCHAR(100),
            Region                 VARCHAR(50),
            Marketplace            VARCHAR(150),
            seller_name            VARCHAR(255),
            homologated_name       VARCHAR(255),
            MAP_Price              DECIMAL(12,2),
            LPP                    DECIMAL(12,2),
            Advertised_price       DECIMAL(12,2),
            currency_local         VARCHAR(10),
            Advertised_price_base  DECIMAL(12,2),
            Season                 VARCHAR(10),
            Promotional_price      DECIMAL(12,2),
            promo_dollar_base      DECIMAL(12,2),
            fx_rate_used           DECIMAL(12,8),
            is_violation           BOOLEAN,
            violation_reason       VARCHAR(255),
            INDEX IX_PM_DATE (Violation_date),
            INDEX IX_PM_VIOL (is_violation),
            CONSTRAINT FK_PRICEMON_SKU FOREIGN KEY (SKU) REFERENCES SKU_TABLE(SKU)
        ) ENGINE=InnoDB"""))
    pm_final.to_sql("PRICE_MONITORING_TABLE", con=conn, if_exists="append", index=False, chunksize=1000, method="multi")
print(f"Loaded {len(pm_final):,} rows into PRICE_MONITORING_TABLE.")

# ----------------------------------------------------------------------
# Reads the table back and confirms the row count and violation count equal what was calculated, and shows violations per day.
# ----------------------------------------------------------------------
with engine.connect() as conn:
    n_db = conn.execute(text("SELECT COUNT(*) FROM PRICE_MONITORING_TABLE")).scalar()
    v_db = conn.execute(text("SELECT COALESCE(SUM(is_violation), 0) FROM PRICE_MONITORING_TABLE")).scalar()
    daily = pd.read_sql(text("""SELECT Violation_date AS day, COUNT(*) AS observations, SUM(is_violation) AS violations
                                FROM PRICE_MONITORING_TABLE GROUP BY Violation_date ORDER BY Violation_date"""), conn)
print(f"Rows in table: {n_db:,} (expected {len(pm_final):,}) | violations: {int(v_db):,} (expected {n_v:,})")
assert n_db == len(pm_final) and int(v_db) == n_v, "Stored results differ from calculated results"
daily["violation_rate_%"] = (daily["violations"].astype(float) / daily["observations"] * 100).round(1)
daily

# ----------------------------------------------------------------------
# Saves a backup of the database to Drive.
# ----------------------------------------------------------------------
mc.db_backup()
