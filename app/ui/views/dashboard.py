import pandas as pd
import streamlit as st
from ui import db, queries as Q, settings_store
from ui.config import REPORT_DIR

def render():
    st.title("Dashboard")
    if not db.table_exists(Q.PM) or not Q.have_data():
        st.info("No monitoring results yet. Go to **Upload & run**, load the source files and run the pipeline.")
        return
    f = Q.filter_widgets("dash")
    where, params, exp = Q.where_clause(f)
    letter_at = int(settings_store.load()["LETTER_AT"])

    daily = db.query(
        f"SELECT Violation_date AS day, COUNT(*) AS obs, SUM(is_violation) AS viol, "
        f"SUM(CASE WHEN {Q.TYPE_EXPR} = 'Below LPP' THEN 1 ELSE 0 END) AS lpp, "
        f"SUM(CASE WHEN {Q.TYPE_EXPR} = 'Below MAP' THEN 1 ELSE 0 END) AS mp, "
        f"SUM(CASE WHEN {Q.TYPE_EXPR} = 'Cannot be judged' THEN 1 ELSE 0 END) AS unj "
        f"FROM {Q.PM} WHERE {where} GROUP BY Violation_date ORDER BY Violation_date", params, exp)
    if daily.empty:
        st.warning("No rows match these filters.")
        return
    daily = daily.astype({c: float for c in ["obs", "viol", "lpp", "mp", "unj"]})
    daily["day"] = pd.to_datetime(daily["day"])
    tot_obs, tot_v = daily["obs"].sum(), daily["viol"].sum()
    sellers = db.query(f"SELECT COUNT(DISTINCT COALESCE(homologated_name, seller_name)) AS n FROM {Q.PM} WHERE is_violation = 1 AND {where}", params, exp)["n"].iloc[0]
    strikes = Q.strikes_table(f["d2"], letter_at, f["marketplace"])

    c = st.columns(6)
    c[0].metric("Observations", f"{tot_obs:,.0f}")
    c[1].metric(f"Violations ({tot_v / tot_obs:.1%})", f"{tot_v:,.0f}", help=f"{tot_v / tot_obs:.1%} of all observations")
    c[2].metric("Below LPP (hard floor)", f"{daily['lpp'].sum():,.0f}")
    c[3].metric("Below MAP", f"{daily['mp'].sum():,.0f}")
    c[4].metric("Sellers in violation", f"{sellers:,}")
    c[5].metric(f"Letter stage (of {len(strikes):,})", f"{int((strikes['Strikes'] >= letter_at).sum()) if len(strikes) else 0:,}",
                help=f"out of {len(strikes):,} seller + marketplace pairs")
    if daily["unj"].sum():
        st.caption(f"{daily['unj'].sum():,.0f} observations could not be judged (missing price list entry or LPP rule). "
                   "They are not counted as violations.")

    left, right = st.columns(2)
    with left:
        st.subheader("Violation rate by day")
        rate = daily.assign(**{"Violation rate %": daily["viol"] / daily["obs"] * 100}).set_index("day")[["Violation rate %"]]
        st.line_chart(rate, color="#2a78d6")
    with right:
        st.subheader("Type of violation by day")
        st.bar_chart(daily.set_index("day")[["lpp", "mp"]].rename(columns={"lpp": "Below LPP", "mp": "Below MAP"}),
                     color=["#eb6834", "#2a78d6"])

    left, right = st.columns(2)
    with left:
        st.subheader("Top sellers by violations")
        top = db.query(f"SELECT COALESCE(homologated_name, seller_name) AS Seller, COUNT(*) AS Violations FROM {Q.PM} "
                       f"WHERE is_violation = 1 AND {where} GROUP BY Seller ORDER BY Violations DESC LIMIT 15", params, exp)
        if len(top):
            st.bar_chart(top.set_index("Seller").astype(float), horizontal=True, color="#2a78d6")
    with right:
        st.subheader("Violations by category")
        cat = db.query(f"SELECT COALESCE(Category, '(none)') AS Category, COALESCE(Sub_category, '(none)') AS Sub_category, "
                       f"COUNT(*) AS Violations FROM {Q.PM} WHERE is_violation = 1 AND {where} "
                       f"GROUP BY Category, Sub_category ORDER BY Violations DESC", params, exp)
        if len(cat):
            cat["label"] = cat["Category"] + " / " + cat["Sub_category"]
            st.bar_chart(cat.set_index("label")[["Violations"]].astype(float), horizontal=True, color="#2a78d6")

    st.subheader("Marketplace × region (violations)")
    mr = db.query(f"SELECT Marketplace, Region, COUNT(*) AS n FROM {Q.PM} WHERE is_violation = 1 AND {where} GROUP BY Marketplace, Region", params, exp)
    if len(mr):
        st.dataframe(mr.pivot_table(index="Marketplace", columns="Region", values="n", aggfunc="sum", fill_value=0)
                     .style.background_gradient(cmap="Blues", axis=None), width="stretch")

    st.subheader("Escalation stage of seller + marketplace pairs")
    if len(strikes):
        order = [f"Warning {i}" for i in range(1, letter_at)] + ["Violation Letter"]
        st.bar_chart(strikes["Stage"].value_counts().reindex(order, fill_value=0).rename("Pairs").to_frame(), color="#2a78d6")
        st.caption(f"Strikes counted from the start of the data up to {f['d2']}. Strike {letter_at} and above = Violation Letter.")

    pdfs = sorted(REPORT_DIR.glob("Compliance_Charts_*.pdf"), reverse=True)
    xlsx = sorted(REPORT_DIR.glob("Compliance_Report_*.xlsx"), reverse=True)
    if pdfs or xlsx:
        st.subheader("Latest generated reports")
        cols = st.columns(2)
        if pdfs:
            cols[0].download_button(f"Download {pdfs[0].name}", pdfs[0].read_bytes(), pdfs[0].name, "application/pdf")
        if xlsx:
            cols[1].download_button(f"Download {xlsx[0].name}", xlsx[0].read_bytes(), xlsx[0].name,
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
