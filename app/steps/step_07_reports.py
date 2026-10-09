"""AUTO-GENERATED from 07_Charts_and_Reports.ipynb by build_steps.py - edit the notebook and regenerate, not this file."""
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
import os, re
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.backends.backend_pdf import PdfPages
from sqlalchemy import text
engine = mc.connect_db()

# ----------------------------------------------------------------------
# Settings (the day to highlight, how many sellers/products to show in ranked charts, the strike at which a letter is issued) and the chart style: one b
# ----------------------------------------------------------------------
FOCUS_DATE = _ov("FOCUS_DATE", None)        # None = latest date in the data | or "2026-01-05"
TOP_N = _ov("TOP_N", 20)               # how many sellers / products / product lines in ranked charts
LETTER_AT = _ov("LETTER_AT", 3)            # must equal the setting in notebook 06
CHART_DIR = mc.CHART_DIR

BLUE, ORANGE, GREY = "#2a78d6", "#eb6834", "#9b9a95"
INK, INK2, SURFACE, GRID = "#0b0b0b", "#52514e", "#fcfcfb", "#e3e2dd"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "axes.titlesize": 14, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "font.size": 10, "legend.frameon": False,
})
figures = []   # (filename, figure) - collected for the PDF

def finish(fig, name, title, subtitle=None):
    """Title + optional subtitle in a fixed-height header band, save PNG, remember for the PDF, show."""
    h = fig.get_figheight()
    head = 0.85 if subtitle else 0.55
    fig.text(0.01, 1 - 0.12 / h, title, ha="left", va="top", fontsize=14, fontweight="bold")
    if subtitle:
        fig.text(0.01, 1 - 0.46 / h, subtitle, ha="left", va="top", fontsize=10, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 1 - head / h))
    path = os.path.join(CHART_DIR, f"{name}.png")
    fig.savefig(path, dpi=150)
    figures.append((name, fig))
    plt.show()
    print("saved", os.path.relpath(path, mc.PROJECT_DIR))
print("Style ready.")

# ----------------------------------------------------------------------
# Reads the whole `PRICE_MONITORING_TABLE`, labels each violation as Below LPP or Below MAP, calculates how far below the broken floor each price is (as
# ----------------------------------------------------------------------
q = """SELECT SKU, Violation_date, PL, Category, Sub_category, Region, Marketplace, seller_name, homologated_name,
              MAP_Price, LPP, Advertised_price, currency_local, Advertised_price_base, Season, Promotional_price,
              is_violation, violation_reason FROM PRICE_MONITORING_TABLE"""
with engine.connect() as conn:
    df = pd.read_sql(text(q), conn)
if df.empty:
    raise RuntimeError("PRICE_MONITORING_TABLE is empty. Run notebook 05 first.")
for c in ["MAP_Price", "LPP", "Advertised_price", "Advertised_price_base", "Promotional_price"]:
    df[c] = pd.to_numeric(df[c], errors="coerce")
df["Violation_date"] = pd.to_datetime(df["Violation_date"]).dt.normalize()
df["Seller"] = df["homologated_name"].fillna(df["seller_name"])
df["is_violation"] = df["is_violation"].astype(bool)
reason = df["violation_reason"].fillna("")
df["unclassifiable"] = reason.str.startswith("Cannot classify")
df["viol_type"] = np.where(reason.str.startswith("Below LPP"), "Below LPP (hard floor)",
                  np.where(reason.str.startswith("Below MAP"), "Below MAP (no promotion cover)", None))
floor = np.where(df["viol_type"] == "Below LPP (hard floor)", df["LPP"], df["MAP_Price"])
df["depth_pct"] = np.where(df["is_violation"], (floor - df["Advertised_price_base"]) / floor * 100, np.nan)

viol = df[df["is_violation"]].copy()
if viol.empty:
    raise RuntimeError("No violations in the data - nothing to chart.")
dates = sorted(df["Violation_date"].unique())
focus = pd.Timestamp(FOCUS_DATE) if FOCUS_DATE else df["Violation_date"].max()
print(f"Rows: {len(df):,} | violations: {len(viol):,} ({len(viol) / len(df):.1%}) | cannot be judged: {int(df['unclassifiable'].sum()):,}")
print(f"Days: {len(dates)} ({pd.Timestamp(dates[0]).date()} to {pd.Timestamp(dates[-1]).date()}) | focus date: {focus.date()}")

# ----------------------------------------------------------------------
# Draws charts 1-4: violation rate by day (with average and the two highest days marked), type of violation by day (stacked LPP vs MAP), the number of o
# ----------------------------------------------------------------------
# Chart 1 -- violation rate per day
d = df.groupby("Violation_date").agg(total=("SKU", "size"), v=("is_violation", "sum")).reset_index()
d["rate"] = d["v"] / d["total"] * 100
fig, ax = plt.subplots(figsize=(11, 4.6))
ax.plot(d["Violation_date"], d["rate"], color=BLUE, lw=2, marker="o", ms=6)
ax.axhline(d["rate"].mean(), color=GREY, lw=1, ls="--")
ax.text(d["Violation_date"].iloc[0], d["rate"].mean() + 0.3, f"average {d['rate'].mean():.1f}%", color=INK2, fontsize=9)
for _, r in d.nlargest(2, "rate").iterrows():
    ax.annotate(f"{r['rate']:.1f}%", (r["Violation_date"], r["rate"]), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=9)
ax.set_ylim(0, d["rate"].max() * 1.25); ax.set_ylabel("% of observations in violation")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b")); ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
finish(fig, "01_violation_rate_over_time", "1. Violation rate by day", "Share of all price observations that day that were below their permitted floor")

# Chart 2 -- which floor was broken, by day (stacked)
t = viol.groupby(["Violation_date", "viol_type"]).size().unstack(fill_value=0).reindex(columns=["Below LPP (hard floor)", "Below MAP (no promotion cover)"], fill_value=0)
fig, ax = plt.subplots(figsize=(11, 4.6))
x = np.arange(len(t)); w = 0.7
ax.bar(x, t.iloc[:, 0], w, color=ORANGE, label="Below LPP (hard floor)", edgecolor=SURFACE, linewidth=1.5)
ax.bar(x, t.iloc[:, 1], w, bottom=t.iloc[:, 0], color=BLUE, label="Below MAP (no promotion cover)", edgecolor=SURFACE, linewidth=1.5)
ax.set_xticks(x); ax.set_xticklabels([pd.Timestamp(i).strftime("%d %b") for i in t.index], rotation=45, ha="right")
ax.set_ylabel("Violating observations"); ax.legend(loc="upper left", ncol=2)
finish(fig, "02_violation_type_by_day", "2. Type of violation by day", "LPP breaches can never be excused by a promotion; MAP breaches can")

# Chart 3 -- observations collected vs violations (volume behind the rate)
fig, ax = plt.subplots(figsize=(11, 4.6))
xx = np.arange(len(d))
ax.bar(xx, d["total"], 0.7, color="#d9d8d2", label="All observations")
ax.bar(xx, d["v"], 0.7, color=BLUE, label="Violations")
ax.set_xticks(xx); ax.set_xticklabels([i.strftime("%d %b") for i in d["Violation_date"]], rotation=45, ha="right")
ax.set_ylabel("Observations"); ax.set_ylim(0, d["total"].max() * 1.18); ax.legend(loc="upper left", ncol=2)
finish(fig, "03_volume_by_day", "3. Volume of data behind the rate", "Blue = violations within all observations collected that day")

# Chart 4 -- violation rate by weekday of collection
wd = df.assign(dow=df["Violation_date"].dt.day_name()).groupby("dow").agg(total=("SKU", "size"), v=("is_violation", "sum"))
wd["rate"] = wd["v"] / wd["total"] * 100
wd = wd.reindex([x for x in ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"] if x in wd.index])
fig, ax = plt.subplots(figsize=(8, 4.4))
bars = ax.bar(wd.index, wd["rate"], color=BLUE, width=0.6)
ax.bar_label(bars, labels=[f"{x:.1f}%" for x in wd["rate"]], padding=3, fontsize=9)
ax.set_ylabel("% of observations in violation"); ax.set_ylim(0, wd["rate"].max() * 1.2); ax.grid(axis="x", visible=False)
finish(fig, "04_violation_rate_by_weekday", "4. Violation rate by day of week", f"With only {len(dates)} days of data each weekday has few samples -- treat as indicative until more history exists")

# ----------------------------------------------------------------------
# Draws charts 5-8: violations by category and sub-category, top product lines, a marketplace × region heat map (counts) and violation *rate* by marketp
# ----------------------------------------------------------------------
# Chart 5 -- by category and sub-category
fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), gridspec_kw={"width_ratios": [1, 1.3]})
c = viol["Category"].value_counts().sort_values()
b = axes[0].barh(c.index, c.values, color=BLUE, height=0.55); axes[0].bar_label(b, padding=3, fmt="{:,.0f}")
axes[0].set_title("By category", fontsize=11, loc="left"); axes[0].grid(axis="y", visible=False); axes[0].set_xlim(0, c.max() * 1.15)
s = viol["Sub_category"].value_counts().head(TOP_N).sort_values()
b = axes[1].barh(s.index, s.values, color=BLUE, height=0.55); axes[1].bar_label(b, padding=3, fmt="{:,.0f}")
axes[1].set_title("By sub-category", fontsize=11, loc="left"); axes[1].grid(axis="y", visible=False); axes[1].set_xlim(0, s.max() * 1.15)
finish(fig, "05_violations_by_category", "5. Where the violations are: category and sub-category", "Number of violating observations (all days)")

# Chart 6 -- top product lines
p = viol["PL"].value_counts().head(TOP_N).sort_values()
fig, ax = plt.subplots(figsize=(9, 0.32 * len(p) + 1.6))
b = ax.barh(p.index, p.values, color=BLUE, height=0.6); ax.bar_label(b, padding=3, fmt="{:,.0f}")
ax.grid(axis="y", visible=False); ax.set_xlim(0, p.max() * 1.12)
finish(fig, "06_top_product_lines", f"6. Top {len(p)} product lines by violations", f"These {len(p)} lines account for {p.sum()/len(viol):.0%} of all violations")

# Chart 7 -- marketplace x region heat map (counts)
h = viol.pivot_table(index="Marketplace", columns="Region", values="SKU", aggfunc="size", fill_value=0)
fig, ax = plt.subplots(figsize=(8.5, 0.9 * len(h) + 1.8))
im = ax.imshow(h.values, cmap="Blues", aspect="auto", vmin=0); ax.grid(False)
ax.set_xticks(range(h.shape[1])); ax.set_xticklabels(h.columns); ax.set_yticks(range(h.shape[0])); ax.set_yticklabels(h.index)
for i in range(h.shape[0]):
    for j in range(h.shape[1]):
        v = h.values[i, j]; ax.text(j, i, f"{v:,}", ha="center", va="center", color="white" if v > h.values.max() * 0.55 else INK, fontsize=10)
for sp in ax.spines.values(): sp.set_visible(False)
fig.colorbar(im, ax=ax, shrink=0.8, label="Violations")
finish(fig, "07_marketplace_by_region", "7. Violations by marketplace and region", "Darker = more violations; the number is the count")

# Chart 8 -- violation RATE by marketplace and by region
fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
for ax, col in zip(axes, ["Marketplace", "Region"]):
    r = df.groupby(col).agg(total=("SKU", "size"), v=("is_violation", "sum")); r["rate"] = r["v"] / r["total"] * 100
    r = r.sort_values("rate")
    b = ax.barh(r.index, r["rate"], color=BLUE, height=0.55); ax.bar_label(b, labels=[f"{x:.1f}%" for x in r["rate"]], padding=3, fontsize=9)
    ax.set_title(f"By {col.lower()}", fontsize=11, loc="left"); ax.grid(axis="y", visible=False); ax.set_xlim(0, r["rate"].max() * 1.2)
finish(fig, "08_violation_rate_marketplace_region", "8. Violation rate by marketplace and region", "% of that marketplace's / region's observations that were violations (fair comparison regardless of volume)")

# ----------------------------------------------------------------------
# Draws charts 9-12: top sellers by violations, a seller × day heat map showing consistency, the current escalation stage of every seller + marketplace 
# ----------------------------------------------------------------------
# Strikes per seller + marketplace (same rule as Step 5)
daily = viol.groupby(["Seller", "Marketplace", "Violation_date"]).size().rename("n").reset_index()
strikes = daily.groupby(["Seller", "Marketplace"]).size().rename("Strike").reset_index()
strikes["Stage"] = strikes["Strike"].apply(lambda s: "Violation Letter" if s >= LETTER_AT else f"Warning {s}")

# Chart 9 -- top sellers
sv = viol["Seller"].value_counts().head(TOP_N).sort_values()
fig, ax = plt.subplots(figsize=(9, 0.32 * len(sv) + 1.6))
b = ax.barh(sv.index, sv.values, color=BLUE, height=0.6); ax.bar_label(b, padding=3, fmt="{:,.0f}")
ax.grid(axis="y", visible=False); ax.set_xlim(0, sv.max() * 1.12)
finish(fig, "09_top_sellers", f"9. Top {len(sv)} sellers by violations", "Recognised (homologated) seller names, all marketplaces combined")

# Chart 10 -- seller x day consistency heat map for the top sellers
top = viol["Seller"].value_counts().head(TOP_N).index
g = viol[viol["Seller"].isin(top)].pivot_table(index="Seller", columns="Violation_date", values="SKU", aggfunc="size", fill_value=0).loc[top]
fig, ax = plt.subplots(figsize=(11, 0.3 * len(g) + 1.8))
im = ax.imshow(g.values, cmap="Blues", aspect="auto", vmin=0); ax.grid(False)
ax.set_yticks(range(len(g))); ax.set_yticklabels(g.index)
ax.set_xticks(range(g.shape[1])); ax.set_xticklabels([pd.Timestamp(i).strftime("%d %b") for i in g.columns], rotation=45, ha="right")
for sp in ax.spines.values(): sp.set_visible(False)
fig.colorbar(im, ax=ax, shrink=0.8, label="Violations that day")
finish(fig, "10_seller_consistency", "10. How consistent are the top offenders?", "A solid dark row = violating almost every day; a patchy row = occasional")

# Chart 11 -- current escalation stage
order = [f"Warning {i}" for i in range(1, LETTER_AT)] + ["Violation Letter"]
st = strikes["Stage"].value_counts().reindex(order, fill_value=0)
fig, ax = plt.subplots(figsize=(8, 4.4))
cols = [BLUE] * (len(order) - 1) + [ORANGE]
b = ax.bar(order, st.values, color=cols, width=0.55); ax.bar_label(b, padding=3, fmt="{:,.0f}")
ax.set_ylabel("Seller + marketplace pairs"); ax.set_ylim(0, max(st.max(), 1) * 1.15); ax.grid(axis="x", visible=False)
finish(fig, "11_escalation_stage", "11. Where sellers stand on the escalation ladder", f"Current stage of {len(strikes):,} seller + marketplace pairs that have violated at least once (letter from strike {LETTER_AT})")

# Chart 12 -- strike distribution + new vs repeat offenders per day
fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
sd = strikes["Strike"].value_counts().sort_index()
axes[0].bar(sd.index.astype(str), sd.values, color=BLUE, width=0.7); axes[0].set_xlabel("Strikes accumulated"); axes[0].set_ylabel("Seller + marketplace pairs")
axes[0].set_title("Strike distribution", fontsize=11, loc="left"); axes[0].grid(axis="x", visible=False)
first = daily.groupby(["Seller", "Marketplace"])["Violation_date"].transform("min")
daily["kind"] = np.where(daily["Violation_date"] == first, "First-time", "Repeat")
nr = daily.groupby(["Violation_date", "kind"]).size().unstack(fill_value=0).reindex(columns=["First-time", "Repeat"], fill_value=0)
x = np.arange(len(nr))
axes[1].bar(x, nr["Repeat"], color=ORANGE, label="Repeat", edgecolor=SURFACE, linewidth=1.2)
axes[1].bar(x, nr["First-time"], bottom=nr["Repeat"], color=BLUE, label="First-time", edgecolor=SURFACE, linewidth=1.2)
axes[1].set_xticks(x); axes[1].set_xticklabels([pd.Timestamp(i).strftime("%d %b") for i in nr.index], rotation=60, ha="right", fontsize=8)
axes[1].set_title("Offenders per day: first-time vs repeat", fontsize=11, loc="left"); axes[1].set_ylim(0, (nr.sum(axis=1).max()) * 1.2); axes[1].legend(loc="upper left", ncol=2)
finish(fig, "12_strikes_and_repeat_offenders", "12. Strike distribution and repeat offenders", "Most of the problem is repeat behaviour, not new offenders -- the case for escalation")

# ----------------------------------------------------------------------
# Draws charts 13-15: how far below the floor sellers go, advertised price range against the MAP/LPP band for the focus date's worst products, and promo
# ----------------------------------------------------------------------
# Chart 13 -- depth of violation
fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=False)
for ax, (typ, colr) in zip(axes, [("Below LPP (hard floor)", ORANGE), ("Below MAP (no promotion cover)", BLUE)]):
    x = viol.loc[viol["viol_type"] == typ, "depth_pct"].dropna().clip(upper=60)
    ax.hist(x, bins=30, color=colr, edgecolor=SURFACE)
    if len(x): ax.axvline(x.median(), color=INK2, lw=1, ls="--"); ax.text(x.median(), ax.get_ylim()[1] * 0.92, f"  median {x.median():.1f}%", color=INK2, fontsize=9)
    ax.set_title(f"{typ}  (n={len(x):,})", fontsize=11, loc="left"); ax.set_xlabel("% below the broken floor (capped at 60%)"); ax.set_ylabel("Observations")
finish(fig, "13_depth_of_violation", "13. How far below the floor do sellers go?", "Distance below LPP (left) and below MAP (right), as a % of that floor")

# Chart 14 -- price position vs MAP/LPP band for the focus date (top SKUs)
f = df[(df["Violation_date"] == focus) & (~df["unclassifiable"])].copy()
f["adv_pct"] = f["Advertised_price_base"] / f["MAP_Price"] * 100
f["lpp_pct"] = f["LPP"] / f["MAP_Price"] * 100
k = f.groupby("SKU").agg(lo=("adv_pct", "min"), hi=("adv_pct", "max"), lpp=("lpp_pct", "first"), nviol=("is_violation", "sum"))
k = k[k["nviol"] > 0].sort_values("lo").head(30).iloc[::-1]
fig, ax = plt.subplots(figsize=(10, 0.28 * len(k) + 1.8))
y = np.arange(len(k))
ax.hlines(y, k["lo"], k["hi"], color=BLUE, lw=5, alpha=0.8, label="Advertised price range")
ax.scatter(k["lo"], y, color=BLUE, s=22, zorder=3)
ax.scatter(k["lpp"], y, marker="|", s=150, color=ORANGE, linewidths=2.5, label="LPP (hard floor)", zorder=3)
ax.axvline(100, color=INK, lw=1.2); ax.text(100, len(k) - 0.3, " MAP = 100%", fontsize=9, va="bottom")
ax.set_yticks(y); ax.set_yticklabels(k.index, fontsize=8); ax.set_xlabel("Advertised price as % of MAP"); ax.grid(axis="y", visible=False)
ax.legend(loc="lower right")
finish(fig, "14_price_band_focus_date", f"14. Advertised price vs MAP and LPP -- {focus.date()}", f"The {len(k)} products with the deepest undercutting that day; left of the orange tick = below LPP")

# Chart 15 -- promotion impact + products with no price-list entry
pr = df[df["Promotional_price"].notna() & ~df["unclassifiable"]].copy()
bad_promo = (pr["Promotional_price"] <= 0).sum()
pr = pr[pr["Promotional_price"] > 0]
pr["promo_pct"] = pr["Promotional_price"] / pr["MAP_Price"] * 100
pr["lpp_pct"] = pr["LPP"] / pr["MAP_Price"] * 100
pp = pr.groupby(["SKU", "Season"]).agg(promo=("promo_pct", "first"), lpp=("lpp_pct", "first")).reset_index()
pp["gap"] = 100 - pp["promo"]; pp = pp.sort_values("gap", ascending=False).head(25).iloc[::-1]
fig, axes = plt.subplots(1, 2, figsize=(12, 0.3 * max(len(pp), 8) + 1.8), gridspec_kw={"width_ratios": [1.5, 1]})
ax = axes[0]; y = np.arange(len(pp))
ax.hlines(y, pp["promo"], 100, color=BLUE, lw=5, alpha=0.8, label="Prices newly allowed by the promotion")
ax.scatter(pp["lpp"], y, marker="|", s=150, color=ORANGE, linewidths=2.5, label="LPP (never excused)", zorder=3)
ax.axvline(100, color=INK, lw=1.2)
ax.set_yticks(y); ax.set_yticklabels([f"{s} ({q})" for s, q in zip(pp["SKU"], pp["Season"])], fontsize=8)
ax.set_xlabel("% of MAP"); ax.grid(axis="y", visible=False); ax.legend(loc="lower left", fontsize=8)
ax.set_title("Promotion: extra room below MAP", fontsize=11, loc="left")
miss = df[df["unclassifiable"]].groupby("SKU").size().sort_values().tail(12)
ax = axes[1]
if len(miss):
    b = ax.barh(miss.index, miss.values, color=GREY, height=0.6); ax.bar_label(b, padding=3, fmt="{:,.0f}")
    ax.set_xlim(0, miss.max() * 1.18)
ax.grid(axis="y", visible=False); ax.set_title("Cannot be judged: missing price / LPP data", fontsize=11, loc="left"); ax.set_xlabel("Observations")
note = f"{bad_promo:,} promotion rows with a non-positive promotional price were excluded -- check the promotion data (notebook 02) and promotion logic (notebook 05)." if bad_promo else "All promotion rows had a valid promotional price."
finish(fig, "15_promotion_impact_and_data_gaps", "15. Promotion impact and price-list gaps", note)

# ----------------------------------------------------------------------
# Writes all the charts into one PDF, `Compliance_Charts_<focus date>.pdf`, in `outputs/reports/`.
# ----------------------------------------------------------------------
pdf_path = os.path.join(mc.REPORT_DIR, f"Compliance_Charts_{focus.strftime('%Y-%m-%d')}.pdf")
with PdfPages(pdf_path) as pdf:
    for name, fig in figures:
        pdf.savefig(fig)
print(f"{len(figures)} charts -> {os.path.relpath(CHART_DIR, mc.PROJECT_DIR)}/*.png and {os.path.relpath(pdf_path, mc.PROJECT_DIR)}")
assert len(figures) == 15, f"Expected 15 charts, drew {len(figures)}"

# ----------------------------------------------------------------------
# Builds the Excel report workbook with seven sheets (KPIs, daily trend, category, marketplace × region, seller scorecard, violations on the focus date,
# ----------------------------------------------------------------------
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

daily_t = df.groupby("Violation_date").agg(Observations=("SKU", "size"), Violations=("is_violation", "sum")).reset_index()
daily_t["Violation rate %"] = (daily_t["Violations"] / daily_t["Observations"] * 100).round(2)
lt = viol.groupby("Violation_date")["viol_type"].value_counts().unstack(fill_value=0)
daily_t = daily_t.merge(lt.rename(columns={"Below LPP (hard floor)": "Below LPP", "Below MAP (no promotion cover)": "Below MAP"}).reset_index(),
                        on="Violation_date", how="left").fillna(0)
daily_t = daily_t.rename(columns={"Violation_date": "Date"})

cat_t = df.groupby(["Category", "Sub_category"], dropna=False).agg(Observations=("SKU", "size"), Violations=("is_violation", "sum")).reset_index()
cat_t["Violation rate %"] = (cat_t["Violations"] / cat_t["Observations"] * 100).round(2)
cat_t = cat_t.sort_values("Violations", ascending=False)

mr = df.groupby(["Marketplace", "Region"]).agg(Observations=("SKU", "size"), Violations=("is_violation", "sum")).reset_index()
mr["Violation rate %"] = (mr["Violations"] / mr["Observations"] * 100).round(2)
mr = mr.sort_values("Violations", ascending=False)

dly = viol.groupby(["Seller", "Marketplace", "Violation_date"]).size().rename("n").reset_index()
card = dly.groupby(["Seller", "Marketplace"]).agg(Strikes=("Violation_date", "nunique"), First_violation=("Violation_date", "min"),
                                                   Last_violation=("Violation_date", "max")).reset_index()
vv = viol.groupby(["Seller", "Marketplace"]).agg(Violating_observations=("SKU", "size"), Distinct_SKUs=("SKU", "nunique"),
                                                  Avg_depth_below_floor_pct=("depth_pct", "mean")).round(2).reset_index()
card = card.merge(vv, on=["Seller", "Marketplace"])
card["Current stage"] = card["Strikes"].apply(lambda s: "Violation Letter" if s >= LETTER_AT else f"Warning {s}")
card = card.sort_values(["Strikes", "Violating_observations"], ascending=False)
card["First_violation"] = card["First_violation"].dt.date; card["Last_violation"] = card["Last_violation"].dt.date

detail = viol[viol["Violation_date"] == focus][["Violation_date", "Seller", "Marketplace", "Region", "SKU", "PL", "Category", "Sub_category",
          "currency_local", "Advertised_price", "Advertised_price_base", "MAP_Price", "LPP", "Promotional_price", "viol_type", "depth_pct"]].copy()
detail["Violation_date"] = detail["Violation_date"].dt.date
detail = detail.rename(columns={"viol_type": "Violation type", "depth_pct": "Below floor %"}).round(2).sort_values(["Seller", "Marketplace", "SKU"])

un = df[df["unclassifiable"]].copy()
un["Cause"] = np.select([un["MAP_Price"].isna(), un["LPP"].isna()], ["No price list entry (no MAP)", "No LPP rule for company/sub-category"], "Unknown region/currency or bad price")
cannot = (un.groupby(["SKU", "PL", "Category", "Sub_category", "Cause"], dropna=False).size().rename("Observations").reset_index()
            .sort_values("Observations", ascending=False))

kpi = pd.DataFrame([
    ("Period covered", f"{pd.Timestamp(dates[0]).date()} to {pd.Timestamp(dates[-1]).date()} ({len(dates)} days)"),
    ("Price observations", f"{len(df):,}"),
    ("Violations", f"{len(viol):,} ({len(viol) / len(df):.1%})"),
    ("  of which below LPP (hard floor)", f"{int((viol['viol_type'] == 'Below LPP (hard floor)').sum()):,}"),
    ("  of which below MAP (no promotion cover)", f"{int((viol['viol_type'] == 'Below MAP (no promotion cover)').sum()):,}"),
    ("Observations that could not be judged", f"{int(df['unclassifiable'].sum()):,}"),
    ("Recognised sellers with a violation", f"{viol['Seller'].nunique():,}"),
    ("Seller + marketplace pairs at Violation Letter stage", f"{int((card['Strikes'] >= LETTER_AT).sum()):,} of {len(card):,}"),
    ("Median depth below the broken floor", f"{viol['depth_pct'].median():.1f}%"),
    ("Focus date", str(focus.date())),
], columns=["Measure", "Value"])

xlsx_path = os.path.join(mc.REPORT_DIR, f"Compliance_Report_{focus.strftime('%Y-%m-%d')}.xlsx")
sheets = {"KPIs": kpi, "Daily trend": daily_t, "By category": cat_t, "Marketplace x Region": mr,
          "Seller scorecard": card, f"Violations {focus.date()}": detail, "Cannot be judged": cannot}
with pd.ExcelWriter(xlsx_path, engine="openpyxl", datetime_format="yyyy-mm-dd", date_format="yyyy-mm-dd") as xw:
    for name, frame in sheets.items():
        frame.to_excel(xw, sheet_name=name[:31], index=False)
        ws = xw.sheets[name[:31]]
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="1F3864")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for i, col in enumerate(frame.columns, 1):
            width = max([len(str(col))] + [len(str(x)) for x in frame[col].head(200)]) + 2
            ws.column_dimensions[get_column_letter(i)].width = min(max(width, 10), 60)
        ws.freeze_panes = "A2"
        if name != "KPIs":
            ws.auto_filter.ref = ws.dimensions
print("Excel report:", os.path.relpath(xlsx_path, mc.PROJECT_DIR))
print({k: len(v) for k, v in sheets.items()})
kpi
