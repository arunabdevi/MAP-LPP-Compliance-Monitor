"""Shared queries and filter widgets for the Dashboard and Violations pages."""
import pandas as pd
import streamlit as st
from ui import db

PM = "PRICE_MONITORING_TABLE"
TYPE_EXPR = ("CASE WHEN violation_reason IS NULL THEN NULL WHEN LEFT(violation_reason, 9) = 'Below LPP' THEN 'Below LPP' "
             "WHEN LEFT(violation_reason, 9) = 'Below MAP' THEN 'Below MAP' WHEN LEFT(violation_reason, 15) = 'Cannot classify' "
             "THEN 'Cannot be judged' ELSE 'Other' END")

def have_data():
    return db.table_exists(PM) and db.query(f"SELECT COUNT(*) AS n FROM {PM}")["n"].iloc[0] > 0

@st.cache_data(ttl=60, show_spinner=False)
def filter_options():
    q = lambda col: db.query(f"SELECT DISTINCT {col} AS v FROM {PM} WHERE {col} IS NOT NULL ORDER BY 1")["v"].tolist()
    dates = db.query(f"SELECT MIN(Violation_date) AS lo, MAX(Violation_date) AS hi FROM {PM}").iloc[0]
    return {"lo": pd.Timestamp(dates["lo"]).date(), "hi": pd.Timestamp(dates["hi"]).date(),
            "marketplace": q("Marketplace"), "region": q("Region"), "category": q("Category")}

def filter_widgets(key, extra_sellers=False):
    """Draws the filter row; returns a dict of the chosen filters."""
    opt = filter_options()
    c1, c2, c3, c4 = st.columns([1.3, 1, 1, 1])
    dr = c1.date_input("Dates", value=(opt["lo"], opt["hi"]), min_value=opt["lo"], max_value=opt["hi"], key=f"{key}_dates")
    d1, d2 = (dr[0], dr[1]) if isinstance(dr, (list, tuple)) and len(dr) == 2 else (opt["lo"], opt["hi"])
    f = {"d1": d1, "d2": d2,
         "marketplace": c2.multiselect("Marketplace", opt["marketplace"], key=f"{key}_mk"),
         "region": c3.multiselect("Region", opt["region"], key=f"{key}_rg"),
         "category": c4.multiselect("Category", opt["category"], key=f"{key}_ct")}
    return f

def where_clause(f, alias=""):
    p = f"{alias}." if alias else ""
    clauses, params, expanding = [f"{p}Violation_date BETWEEN :d1 AND :d2"], {"d1": f["d1"], "d2": f["d2"]}, []
    for key, col in [("marketplace", "Marketplace"), ("region", "Region"), ("category", "Category")]:
        if f.get(key):
            clauses.append(f"{p}{col} IN :{key}"); params[key] = list(f[key]); expanding.append(key)
    return " AND ".join(clauses), params, expanding

def strikes_table(upto_date, letter_at, marketplaces=None):
    """One strike per day with a violation, per recognised seller + marketplace, counted up to a date."""
    sql = (f"SELECT COALESCE(homologated_name, seller_name) AS Seller, Marketplace, COUNT(DISTINCT Violation_date) AS Strikes, "
           f"MIN(Violation_date) AS First_violation, MAX(Violation_date) AS Last_violation, COUNT(*) AS Violating_observations "
           f"FROM {PM} WHERE is_violation = 1 AND Violation_date <= :d ")
    params, expanding = {"d": upto_date}, []
    if marketplaces:
        sql += "AND Marketplace IN :mk "; params["mk"] = list(marketplaces); expanding = ["mk"]
    sql += "GROUP BY Seller, Marketplace ORDER BY Strikes DESC, Violating_observations DESC"
    df = db.query(sql, params, expanding)
    if df.empty:
        return df
    df["Stage"] = df["Strikes"].apply(lambda s: "Violation Letter" if s >= letter_at else f"Warning {s}")
    return df
