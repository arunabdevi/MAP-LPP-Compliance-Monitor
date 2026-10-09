import re
import pandas as pd
import streamlit as st
from ui import db, settings_store, mailer
from ui.config import mc, PROJECT_DIR, SETTINGS_FILE, RAW_DIR, SELLER_DIR

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TABLES = ["SKU_TABLE", "PRODUCTLINE_TABLE", "PRICELIST_TABLE", "CATEGORYMAPPING_TABLE", "PROMOTION_TABLE", "SELLERMAPPING_TABLE",
          "SELLER_PRICE_OBSERVATIONS", "PRICE_MONITORING_TABLE", "SELLER_CONTACT", "ENFORCEMENT_QUEUE"]

def _rules(s):
    st.caption("These rules are used the next time the pipeline runs.")
    with st.form("rules"):
        c1, c2 = st.columns(2)
        quarter = c1.selectbox("Quarter definition", ["fiscal", "calendar"], index=["fiscal", "calendar"].index(s["QUARTER_MODE"]),
                               help="fiscal: Nov-Jan = Q1, Feb-Apr = Q2, May-Jul = Q3, Aug-Oct = Q4 (matches the offer grid). calendar: Jan-Mar = Q1 ...")
        letter_at = c2.number_input("Strike that triggers a Violation Letter", 2, 10, int(s["LETTER_AT"]),
                                    help="Strike 1..(n-1) give warnings; strike n and above give a formal Violation Letter.")
        fx = c1.checkbox("Fetch fresh exchange rates on every run", value=bool(s["FORCE_FX_REFRESH"]))
        replace = c2.checkbox("Reload seller days that are already in the database", value=bool(s["REPLACE_EXISTING_DAYS"]))
        mode = c1.radio("Letters are created for", ["Latest date", "Every date", "Specific dates"],
                        index=0 if s["RUN_DATES"] is None else 1 if s["RUN_DATES"] == "ALL" else 2, horizontal=True)
        dates_txt = c2.text_input("Specific dates (YYYY-MM-DD, comma separated)",
                                  value=", ".join(s["RUN_DATES"]) if isinstance(s["RUN_DATES"], list) else "")
        fmt = c1.selectbox("Letter file format", ["txt", "pdf", "both"], index=["txt", "pdf", "both"].index(s["LETTER_FORMAT"]))
        top_n = c2.number_input("Rows in ranked charts (top N)", 5, 50, int(s["TOP_N"]))
        focus = c1.text_input("Focus date for reports (blank = latest)", value=s["FOCUS_DATE"] or "")
        if st.form_submit_button("Save rules", type="primary"):
            errs, run_dates = [], None
            date_ok = lambda x: bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", x))
            if mode == "Every date":
                run_dates = "ALL"
            elif mode == "Specific dates":
                run_dates = [x.strip() for x in dates_txt.split(",") if x.strip()]
                if not run_dates or not all(date_ok(x) for x in run_dates):
                    errs.append("Enter specific dates as YYYY-MM-DD, separated by commas.")
            if focus.strip() and not date_ok(focus.strip()):
                errs.append("Focus date must be YYYY-MM-DD or blank.")
            if errs:
                for e in errs: st.error(e)
            else:
                settings_store.save({"QUARTER_MODE": quarter, "LETTER_AT": int(letter_at), "FORCE_FX_REFRESH": fx,
                                     "REPLACE_EXISTING_DAYS": replace, "RUN_DATES": run_dates, "LETTER_FORMAT": fmt,
                                     "TOP_N": int(top_n), "FOCUS_DATE": focus.strip() or None})
                st.success("Saved.")

def _company(s):
    st.caption("This text is printed on every letter. Replace the placeholders and have the wording approved before anything is sent.")
    with st.form("company"):
        name = st.text_input("Manufacturer name", value=s["MANUFACTURER_NAME"])
        contact = st.text_input("Contact line (team | e-mail | phone)", value=s["CONTACT_LINE"])
        days = st.number_input("Days a seller has to correct a listing", 1, 90, int(s["RESPONSE_DAYS"]))
        if st.form_submit_button("Save", type="primary"):
            settings_store.save({"MANUFACTURER_NAME": name.strip(), "CONTACT_LINE": contact.strip(), "RESPONSE_DAYS": int(days)})
            st.success("Saved. Letters created from now on use this text.")
    if "[" in s["MANUFACTURER_NAME"] or "[" in s["CONTACT_LINE"]:
        st.warning("Placeholders in square brackets are still in use.")

def _lpp(s):
    st.caption("LPP = MAP × (1 − percentage ÷ 100). The percentage depends on the company in the product line (HP or DELL) and the sub-category. "
               "Changes apply after you run **Full setup** (step 02) and then step 05 again.")
    df = pd.DataFrame([{"Sub-category": k, "HP %": v[0], "DELL %": v[1]} for k, v in s["LPP_LOGIC"].items()])
    ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key="lpp_editor",
                        column_config={"HP %": st.column_config.NumberColumn(min_value=0, max_value=100, format="%.2f"),
                                       "DELL %": st.column_config.NumberColumn(min_value=0, max_value=100, format="%.2f")})
    if st.button("Save LPP percentages", type="primary"):
        ed = ed.dropna(subset=["Sub-category", "HP %", "DELL %"])
        names = ed["Sub-category"].str.strip().str.upper()
        if names.duplicated().any() or (names == "").any():
            st.error("Each sub-category must appear once and not be blank.")
        else:
            settings_store.save({"LPP_LOGIC": {n: [float(h), float(d)] for n, h, d in zip(names, ed["HP %"], ed["DELL %"])}})
            st.success("Saved. Run Full setup, then step 05, to apply.")
    st.caption("Sub-categories with no row here (for example SCANNER) cannot be judged and are listed in the unclassifiable report.")

def _contacts(user):
    st.caption("Recipient of each letter. Use marketplace * for 'any marketplace'. A specific marketplace entry wins over *.")
    db.ensure_ui_tables()
    df = db.query("SELECT homologated_name AS seller, marketplace, email, contact_person FROM SELLER_CONTACT ORDER BY 1, 2")
    known = db.query("SELECT DISTINCT COALESCE(homologated_name, seller_name) AS s FROM PRICE_MONITORING_TABLE ORDER BY 1")["s"].tolist() \
        if db.table_exists("PRICE_MONITORING_TABLE") else []
    ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key="contacts_editor",
                        column_config={"seller": st.column_config.TextColumn("Seller (recognised name)", required=True),
                                       "marketplace": st.column_config.TextColumn("Marketplace (* = any)", default="*"),
                                       "email": "E-mail", "contact_person": "Contact person"})
    if known:
        missing = [k for k in known if k not in set(ed["seller"].dropna())]
        if missing:
            st.caption(f"{len(missing)} seller(s) with violations have no contact yet, for example: {', '.join(missing[:6])}")
    if st.button("Save contacts", type="primary"):
        ed = ed.dropna(subset=["seller"]).copy()
        ed["marketplace"] = ed["marketplace"].fillna("*").astype(str).str.strip()
        ed["marketplace"] = ed["marketplace"].where(~ed["marketplace"].str.lower().isin(["", "any", "all", "*"]), "*")   # "any" means every marketplace
        ed["email"] = ed["email"].fillna("").astype(str).str.strip()
        ed["contact_person"] = ed["contact_person"].fillna("").astype(str).str.strip()   # blank cells arrive as NaN
        bad = ed[(ed["email"] != "") & ~ed["email"].map(lambda e: bool(EMAIL_RE.match(e)))]
        if not bad.empty:
            st.error(f"Invalid e-mail address for: {', '.join(bad['seller'])}")
        elif ed.duplicated(["seller", "marketplace"]).any():
            st.error("Each seller + marketplace pair can appear only once.")
        else:
            with db.engine().begin() as conn:
                from sqlalchemy import text
                conn.execute(text("DELETE FROM SELLER_CONTACT"))
                for r in ed.itertuples():
                    conn.execute(text("INSERT INTO SELLER_CONTACT (homologated_name, marketplace, email, contact_person) "
                                      "VALUES (:s, :m, :e, :p)"),
                                 {"s": r.seller.strip(), "m": r.marketplace.strip(), "e": r.email or None, "p": r.contact_person or None})
            st.success(f"Saved {len(ed)} contact(s).")

def _seller_map():
    st.caption("Maps each spelling of a seller name to one recognised (homologated) seller, so strikes are counted per real seller. "
               "Note: running step 02 reloads this table from Seller Mapping Table.xlsx, so keep the Excel file up to date too.")
    if not db.table_exists("SELLERMAPPING_TABLE"):
        st.info("Run step 02 first."); return
    df = db.query("SELECT SSELLERS_NAME AS `Seller name as seen`, HOMOLOGATED_SELLERS AS `Recognised seller` FROM SELLERMAPPING_TABLE ORDER BY 2, 1")
    ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key="map_editor")
    if st.button("Save seller mapping", type="primary"):
        ed = ed.dropna().copy()
        ed.iloc[:, 0] = ed.iloc[:, 0].astype(str).str.strip(); ed.iloc[:, 1] = ed.iloc[:, 1].astype(str).str.strip()
        ed = ed[(ed.iloc[:, 0] != "") & (ed.iloc[:, 1] != "")].drop_duplicates(subset=ed.columns[0])
        from sqlalchemy import text
        with db.engine().begin() as conn:
            conn.execute(text("DELETE FROM SELLERMAPPING_TABLE"))
            for a, b in zip(ed.iloc[:, 0], ed.iloc[:, 1]):
                conn.execute(text("INSERT INTO SELLERMAPPING_TABLE (SSELLERS_NAME, HOMOLOGATED_SELLERS) VALUES (:a, :b)"), {"a": a, "b": b})
        st.success(f"Saved {len(ed)} mapping(s). Run step 05 to apply them to existing observations.")

def _system():
    ok, err = db.connection_ok()
    c = st.columns(3)
    c[0].metric("Database", "connected" if ok else "NOT connected")
    c[1].metric("Server", f"{mc.DB_HOST}:{mc.DB_PORT}")
    c[2].metric("Database name", mc.DB_NAME)
    if not ok:
        st.error(err); st.stop()
    counts = db.table_counts(TABLES)
    st.dataframe(pd.DataFrame([{"Table": k, "Rows": v if v is not None else "(missing)"} for k, v in counts.items()]),
                 hide_index=True, width="stretch")
    if st.button("Create / repair the app's own tables (SELLER_CONTACT, ENFORCEMENT_QUEUE)"):
        db.ensure_ui_tables(); st.success("Done.")
    st.write("**Folders**")
    st.code(f"Project folder : {PROJECT_DIR}\nSource files   : {RAW_DIR}\nSeller files   : {SELLER_DIR}\nSettings file  : {SETTINGS_FILE}")

def _gmail(s):
    state, why = mailer.status()
    st.write("**Connection**")
    if state == "ready":
        st.success("Signed in to Gmail (send-only permission).")
        if st.button("Sign out of Gmail"):
            mailer.sign_out(); st.rerun()
    else:
        st.warning(why)
        if state == "need_signin" and st.button("Sign in with Google", type="primary"):
            try:
                with st.spinner("A Google sign-in page opens in your browser - choose the sending account and allow access..."):
                    mailer.sign_in()
                st.rerun()
            except Exception as exc:
                st.error(f"Sign-in failed: {str(exc)[:300]}")
        with st.expander("One-time Google Cloud setup (about 10 minutes)"):
            st.markdown(
                "1. Open https://console.cloud.google.com and create a project (any name).\n"
                "2. **APIs & Services > Library**: search **Gmail API** and click **Enable**.\n"
                "3. **APIs & Services > OAuth consent screen**: choose **External** (a personal Gmail) or **Internal** (Workspace), "
                "fill the app name and your e-mail, save. Under **Audience / Test users** add the Gmail address that will send.\n"
                "4. **APIs & Services > Credentials > Create credentials > OAuth client ID**, type **Desktop app**. Download the JSON.\n"
                f"5. Rename it **credentials.json** and put it in `{mailer.GMAIL_DIR}` (create the folder), then reload this page.\n"
                "6. Click **Sign in with Google**. While the app is in *Testing* mode Google shows an 'unverified app' notice - "
                "choose Advanced > continue; that is expected for your own app.\n\n"
                "Note: in Testing mode the sign-in expires after 7 days. If sending later says the sign-in expired, sign in again "
                "(or publish the consent screen to 'In production').")
    st.divider()
    st.write("**E-mail content**")
    with st.form("mail"):
        subj = st.text_input("Subject", value=s["MAIL_SUBJECT"], help="You can use {action} {seller} {marketplace} {strike} {company}")
        frm = st.text_input("Sender name (optional)", value=s["MAIL_FROM_NAME"])
        frm_addr = st.text_input("Sender address (needed only if you set a sender name; the same Gmail account you signed in with)",
                                 value=s["MAIL_FROM_ADDRESS"])
        bcc = st.text_input("Send a copy (Bcc) of every e-mail to (optional)", value=s["MAIL_BCC"])
        att = st.checkbox("Attach the letter file as well as showing it in the e-mail body", value=bool(s["MAIL_ATTACH"]))
        if st.form_submit_button("Save", type="primary"):
            error = None
            try:
                subj.format(action="a", seller="s", marketplace="m", strike=1, company="c")
            except (KeyError, IndexError, ValueError) as exc:
                error = f"The subject has an unknown or broken placeholder: {exc}"
            if not error and bcc.strip() and not mailer.EMAIL_RE.match(bcc.strip()):
                error = "The Bcc address is not a valid e-mail address."
            if not error and frm_addr.strip() and not mailer.EMAIL_RE.match(frm_addr.strip()):
                error = "The sender address is not a valid e-mail address."
            if error:
                st.error(error)
            else:
                settings_store.save({"MAIL_SUBJECT": subj.strip(), "MAIL_FROM_NAME": frm.strip(), "MAIL_FROM_ADDRESS": frm_addr.strip(),
                                     "MAIL_BCC": bcc.strip(), "MAIL_ATTACH": bool(att)})
                st.success("Saved.")


def render(user):
    st.title("Settings & master data")
    s = settings_store.load()
    t = st.tabs(["Run rules", "Company & letters", "LPP percentages", "Seller contacts", "Seller mapping", "Gmail", "System"])
    with t[0]: _rules(s)
    with t[1]: _company(s)
    with t[2]: _lpp(s)
    with t[3]: _contacts(user)
    with t[4]: _seller_map()
    with t[5]: _gmail(s)
    with t[6]: _system()
