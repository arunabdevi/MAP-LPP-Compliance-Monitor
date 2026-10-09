import streamlit as st

st.set_page_config(page_title="MAP / LPP Compliance", page_icon="📊", layout="wide")

from ui import auth, db                      # noqa: E402  (importing ui.config loads .env and the shared helper)
from ui.views import dashboard, upload_run, violations, review, settings   # noqa: E402

user = auth.require_login()

PAGES = ["Dashboard", "Upload & run", "Violations", "Review & approve", "Settings"]
st.sidebar.title("MAP / LPP Compliance")
page = st.sidebar.radio("Go to", PAGES, label_visibility="collapsed", key="nav")
st.sidebar.caption(f"Signed in as **{user}**")
auth.logout_button()
ok, err = db.connection_ok()
if not ok and page != "Settings":
    st.sidebar.error("Database not reachable")
    st.error(f"Cannot reach the database: {err}")
    st.info("Check the MAP_DB_* values in your `.env` file and make sure MySQL is running "
            "(for example `docker compose up -d`). Then reload this page.")
    st.stop()

if page == "Dashboard":
    dashboard.render()
elif page == "Upload & run":
    upload_run.render()
elif page == "Violations":
    violations.render()
elif page == "Review & approve":
    review.render(user)
else:
    settings.render(user)
