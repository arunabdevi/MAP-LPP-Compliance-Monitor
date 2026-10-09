import pandas as pd
import streamlit as st
from ui import db, queries as Q, settings_store

SHOW_LIMIT = 5000
TYPES = ["Violations only", "Below LPP only", "Below MAP only", "Cannot be judged", "All observations"]

def _filters():
    f = Q.filter_widgets("viol")
    c1, c2, c3 = st.columns([1.4, 1, 1.2])
    sellers = db.query(f"SELECT DISTINCT COALESCE(homologated_name, seller_name) AS s FROM {Q.PM} ORDER BY 1")["s"].dropna().tolist()
    f["seller"] = c1.multiselect("Seller (recognised name)", sellers, key="viol_sellers")
    f["sku"] = c2.text_input("SKU contains", key="viol_sku").strip()
    f["type"] = c3.selectbox("Show", TYPES, key="viol_type")
    return f

def _sql_parts(f):
    where, params, exp = Q.where_clause(f, "p")
    extra = {"Violations only": "p.is_violation = 1",
             "Below LPP only": "LEFT(p.violation_reason, 9) = 'Below LPP'",
             "Below MAP only": "LEFT(p.violation_reason, 9) = 'Below MAP'",
             "Cannot be judged": "LEFT(p.violation_reason, 15) = 'Cannot classify'"}.get(f["type"])
    if extra:
        where += f" AND {extra}"
    if f["seller"]:
        where += " AND COALESCE(p.homologated_name, p.seller_name) IN :sellers"; params["sellers"] = f["seller"]; exp.append("sellers")
    if f["sku"]:
        where += " AND p.SKU LIKE :sku"; params["sku"] = f"%{f['sku']}%"
    return where, params, exp

COLUMNS = ("p.Violation_date AS Date, COALESCE(p.homologated_name, p.seller_name) AS Seller, p.Marketplace, p.Region, p.SKU, p.PL, "
           "p.Category, p.Sub_category, p.currency_local AS Currency, p.Advertised_price AS `Advertised (local)`, "
           "p.Advertised_price_base AS `Advertised (INR)`, p.MAP_Price AS MAP, p.LPP, p.Promotional_price AS `Promo price`, "
           "p.violation_reason AS Reason")

def render():
    st.title("Violations explorer")
    if not db.table_exists(Q.PM) or not Q.have_data():
        st.info("No monitoring results yet. Run the pipeline from **Upload & run**.")
        return
    tab1, tab2 = st.tabs(["Observations", "Seller strikes"])
    with tab1:
        f = _filters()
        where, params, exp = _sql_parts(f)
        total = int(db.query(f"SELECT COUNT(*) AS n FROM {Q.PM} p WHERE {where}", params, exp)["n"].iloc[0])
        st.write(f"**{total:,}** matching rows" + (f" - showing the first {SHOW_LIMIT:,}" if total > SHOW_LIMIT else ""))
        df = db.query(
            f"SELECT {COLUMNS}, o.live_link AS `Live link` FROM {Q.PM} p "
            f"LEFT JOIN SELLER_PRICE_OBSERVATIONS o ON o.file_date = p.Violation_date AND o.SKU = p.SKU "
            f"AND o.Marketplace = p.Marketplace COLLATE utf8mb4_bin AND o.Seller_name = p.seller_name COLLATE utf8mb4_bin "
            f"AND o.region = p.Region COLLATE utf8mb4_bin "
            f"WHERE {where} ORDER BY p.Violation_date DESC, Seller, p.Marketplace, p.SKU LIMIT {SHOW_LIMIT}", params, exp)
        st.dataframe(df, width="stretch", hide_index=True, height=480,
                     column_config={"Live link": st.column_config.LinkColumn("Live link", display_text="open"),
                                    "Advertised (local)": st.column_config.NumberColumn(format="%.2f"),
                                    "Advertised (INR)": st.column_config.NumberColumn(format="%.2f"),
                                    "MAP": st.column_config.NumberColumn(format="%.2f"),
                                    "LPP": st.column_config.NumberColumn(format="%.2f"),
                                    "Promo price": st.column_config.NumberColumn(format="%.2f")})
        if total:
            if st.checkbox(f"Prepare CSV of all {total:,} matching rows", key="viol_csv"):
                full = db.query(f"SELECT {COLUMNS} FROM {Q.PM} p WHERE {where} ORDER BY p.Violation_date, Seller, p.SKU", params, exp)
                st.download_button("Download CSV", full.to_csv(index=False).encode("utf-8-sig"), "violations.csv", "text/csv")
    with tab2:
        letter_at = int(settings_store.load()["LETTER_AT"])
        opt = Q.filter_options()
        d = st.date_input("Strikes counted up to", value=opt["hi"], min_value=opt["lo"], max_value=opt["hi"], key="strike_date")
        s = Q.strikes_table(d, letter_at)
        st.caption(f"One strike per day with at least one violation, per recognised seller and marketplace. "
                   f"Strike 1-{letter_at - 1} = warnings; strike {letter_at}+ = Violation Letter.")
        if s.empty:
            st.info("No violations up to this date.")
        else:
            st.dataframe(s, width="stretch", hide_index=True, height=480)
            st.download_button("Download CSV", s.to_csv(index=False).encode("utf-8-sig"), "seller_strikes.csv", "text/csv")
