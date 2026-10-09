"""AUTO-GENERATED from 01_Architecture_Diagram.ipynb by build_steps.py - edit the notebook and regenerate, not this file."""
# ----------------------------------------------------------------------
# Connects Google Drive, finds your project folder and loads the shared helper module `map_common`.
# ----------------------------------------------------------------------
import os
import map_common as mc          # run_step.py has already put the project folder on the import path
mc.ensure_dirs()
print("Project folder:", mc.PROJECT_DIR)

# ----------------------------------------------------------------------
# Holds all the text that appears in the diagram (input cards, the six stages, their data stores, the output row) and the colour of each stage.
# ----------------------------------------------------------------------
TITLE    = "MAP/LPP Compliance Monitoring - End-to-End Architecture"
SUBTITLE = "From manufacturer data to enforcement and insights"

INPUTS = [  # (number, name, line 1, line 2, colour)
    (1, "SKU",            "Product master",        "SKUs & part numbers",       "#2a78d6"),
    (2, "PL",             "Product line code",     "brand + category + type",       "#2f9e5b"),
    (3, "Price List",     "Approved MAP price",    "one per SKU",               "#7a4fd1"),
    (4, "Category",       "Category & sub-category","derived from the PL",      "#e08a1e"),
    (5, "Promo",          "Quarterly offers",      "+ SKUs on promotion",       "#14a3a3"),
    (6, "Seller Mapping", "Seller name variants",  "-> one recognised seller",  "#d6336c"),
]

STAGES = [  # (number, title, notebook, bullets, data-store title, data-store lines, colour)
    (1, "Ingestion & Validation", "Notebook 02",
        ["Read the manufacturer files (XML, JSON, YAML, Excel)",
         "Clean: split product line, remove conflicting duplicates",
         "Derive LPP from MAP (% depends on company + sub-category)",
         "Load six master tables into MySQL and back them up"],
        "MySQL master tables",
        ["SKU_TABLE", "PRODUCTLINE_TABLE", "PRICELIST_TABLE  (MAP, LPP)", "CATEGORYMAPPING_TABLE", "PROMOTION_TABLE"], "#2a78d6"),
    (2, "Web Scraping", "Notebook 03",
        ["Open Flipkart search + product pages (headless Chrome)",
         "Extract price, seller, product id, live link, screenshot",
         "Save raw results as CSV + screenshots"],
        "Raw marketplace data",
        ["scraper_output/*.csv", "scraper_output/screenshots/", "seller_data/YYYY-MM-DD.csv  (daily files)"], "#2f9e5b"),
    (3, "Normalisation", "Notebook 04",
        ["Validate every daily file: missing SKU, bad price,",
         "   same-day duplicates, SKU not in the master list",
         "Quarantine problem rows (never silently dropped)",
         "Load clean rows, safe to re-run for the same day"],
        "Identity & normalisation",
        ["SELLER_PRICE_OBSERVATIONS", "SELLERMAPPING_TABLE", "quarantined_rows_<date>.csv"], "#7a4fd1"),
    (4, "MAP / LPP Rule Engine", "Notebook 05",
        ["Convert each advertised price to INR (live FX, cached)",
         "Promotion price = MAP less % off, or less $ off in INR",
         "Below LPP -> VIOLATION (a promotion never excuses this)",
         "Covered by a promotion -> OK;  below MAP -> VIOLATION"],
        "Pricing policy",
        ["LPP % by company + sub-category", "Promotion: percent or dollar", "Fiscal quarter (Nov-Jan = Q1)", "FX snapshot per day"], "#e08a1e"),
    (5, "Price Monitoring", "Notebook 05",
        ["One row per price observation -> PRICE_MONITORING_TABLE",
         "Tag violation reason and depth below the floor",
         "Flag rows that cannot be judged (e.g. no price list entry)"],
        "Price monitoring",
        ["PRICE_MONITORING_TABLE", "unclassifiable_skus.csv", "Full daily history = audit trail"], "#14a3a3"),
    (6, "Enforcement Workflow", "Notebook 06",
        ["One strike per day with a violation, per seller + marketplace",
         "Strike 1 -> Warning 1      Strike 2 -> Warning 2",
         "Strike >= 3 -> Violation Letter",
         "Letters written as text (PDF optional) + Excel summary"],
        "Letters & summary",
        ["Warning_1/   Warning_2/", "Violation_Letter/", "Summary_<date>.xlsx", "Letters_<date>.zip"], "#d6336c"),
]

OUTPUTS = [  # (title, subtitle, colour)
    ("Warnings",         "Strike 1 and 2",               "#e0a100"),
    ("Violation Letter", "Strike 3 and above",           "#d6336c"),
    ("Charts",           "15 charts + PDF (nb 07)",      "#2a78d6"),
    ("Excel report",     "KPIs, sellers, detail (nb 07)","#2f9e5b"),
    ("Audit trail",      "full price history in MySQL",  "#7a4fd1"),
]
print("Diagram content loaded:", len(INPUTS), "inputs,", len(STAGES), "stages,", len(OUTPUTS), "outputs")

# ----------------------------------------------------------------------
# Draws the diagram with matplotlib: a title banner, the six input cards, six stage boxes (each with its data-store box on the right and a notebook tag)
# ----------------------------------------------------------------------
import textwrap
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle, FancyArrowPatch

INK, INK2, BG = "#10233f", "#52514e", "#fbfaf7"

def tint(hex_colour, amount=0.88):
    """Very light version of a colour, used as a box background."""
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(int(c + (255 - c) * amount) for c in (r, g, b))

def box(ax, x, y, w, h, edge, face=None, lw=1.8, r=1.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=face or tint(edge), ec=edge, lw=lw, zorder=1))

def badge(ax, x, y, n, colour, rad=1.7):
    ax.add_patch(Circle((x, y), rad, fc=colour, ec="white", lw=1.5, zorder=3))
    ax.text(x, y, str(n), ha="center", va="center", color="white", fontsize=11, fontweight="bold", zorder=4)

def arrow(ax, x1, y1, x2, y2, colour=INK):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=16, lw=1.8, color=colour, zorder=2))

fig = plt.figure(figsize=(10.5, 18.4), facecolor=BG)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 100); ax.set_ylim(176, 0); ax.axis("off")

# --- title banner
box(ax, 3, 2, 94, 10, "#2a78d6", tint("#2a78d6", 0.9), lw=2.2)
ax.text(50, 6.0, TITLE, ha="center", va="center", fontsize=17, fontweight="bold", color=INK)
ax.text(50, 9.6, SUBTITLE, ha="center", va="center", fontsize=11.5, color=INK2, style="italic")

# --- input cards
box(ax, 3, 14.5, 94, 25, "#2a78d6", BG, lw=2.2)
ax.text(50, 18, "INPUT TABLES", ha="center", va="center", fontsize=13, fontweight="bold", color=INK)
cw, gap, x0 = 13.4, 1.6, 5.8
for i, (n, name, l1, l2, col) in enumerate(INPUTS):
    x = x0 + i * (cw + gap)
    box(ax, x, 21, cw, 16.5, col, tint(col, 0.9))
    badge(ax, x + 2.2, 23.3, n, col, 1.5)
    ax.text(x + cw / 2, 28.2, name, ha="center", va="center", fontsize=11, fontweight="bold", color=col)
    ax.text(x + cw / 2, 32, textwrap.fill(l1, 17), ha="center", va="center", fontsize=7.6, color=INK2)
    ax.text(x + cw / 2, 35.2, textwrap.fill(l2, 17), ha="center", va="center", fontsize=7.6, color=INK2)
arrow(ax, 50, 39.6, 50, 43.4)

# --- six stages
top, pitch, sh = 44.5, 19.2, 16.0
for i, (n, title, nbk, bullets, ds_title, ds_lines, col) in enumerate(STAGES):
    y = top + i * pitch
    box(ax, 3, y, 62, sh, col, tint(col, 0.9))
    badge(ax, 6.6, y + 3.6, n, col, 2.0)
    ax.text(10.2, y + 3.6, f"Stage {n}:  {title}", ha="left", va="center", fontsize=13.5, fontweight="bold", color=col)
    ax.text(63.6, y + 2.2, nbk, ha="right", va="center", fontsize=8.5, color="white", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", fc=col, ec="none"))
    for j, b in enumerate(bullets):
        line = ("   " + b.strip()) if b.startswith(" ") else ("\u2022 " + b)
        ax.text(8.0, y + 7.4 + j * 2.1, line, ha="left", va="center", fontsize=8.6, color=INK)
    box(ax, 69, y + 0.5, 28, sh - 1, col, BG, lw=1.6)
    ax.text(70.4, y + 3.3, ds_title, ha="left", va="center", fontsize=10, fontweight="bold", color=col)
    ax.plot([70.2, 95.8], [y + 4.8, y + 4.8], color=col, lw=0.8)
    for j, line in enumerate(ds_lines):
        ax.text(70.6, y + 6.8 + j * 1.8, "\u2022 " + line, ha="left", va="center", fontsize=7.7, color=INK)
    arrow(ax, 65.3, y + sh / 2, 68.7, y + sh / 2, col)
    if i < len(STAGES) - 1:
        arrow(ax, 34, y + sh + 0.1, 34, y + pitch - 0.1)

# --- outputs row
yo = top + 5 * pitch + sh + 3.2
arrow(ax, 34, yo - 2.8, 34, yo - 0.2)
box(ax, 3, yo, 94, 15.5, "#10233f", BG, lw=2.2)
ax.text(50, yo + 3.2, "OUTPUTS", ha="center", va="center", fontsize=13, fontweight="bold", color=INK)
ow = 94 / len(OUTPUTS)
for i, (t, s, col) in enumerate(OUTPUTS):
    cx = 3 + ow * (i + 0.5)
    ax.add_patch(Circle((cx, yo + 7.6), 1.5, fc=col, ec="none", zorder=3))
    ax.text(cx, yo + 11.0, t, ha="center", va="center", fontsize=10.5, fontweight="bold", color=col)
    ax.text(cx, yo + 13.4, textwrap.fill(s, 22), ha="center", va="center", fontsize=7.6, color=INK2)
    if i:
        ax.plot([3 + ow * i] * 2, [yo + 5, yo + 14], color="#c9c8c2", lw=1)
plt.show()

# ----------------------------------------------------------------------
# Saves the diagram as a PNG (for documents) and a PDF (vector, sharp at any size) into `outputs/architecture/` in your Drive project folder.
# ----------------------------------------------------------------------
import os
png = os.path.join(mc.ARCH_DIR, "MAP_LPP_Architecture.png")
pdf = os.path.join(mc.ARCH_DIR, "MAP_LPP_Architecture.pdf")
fig.savefig(png, dpi=170, facecolor=BG)
fig.savefig(pdf, facecolor=BG)
print("Saved:", png); print("Saved:", pdf)
