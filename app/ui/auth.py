import hmac
import streamlit as st
from ui.config import APP_USER, APP_PASSWORD

def require_login():
    """Returns the signed-in user name. Without APP_PASSWORD there is no login (local use only)."""
    if not APP_PASSWORD:
        st.sidebar.warning("No login configured (APP_PASSWORD is empty). Use only on your own computer.")
        return APP_USER or "local"
    if st.session_state.get("user"):
        return st.session_state["user"]
    st.title("MAP / LPP Compliance")
    with st.form("login"):
        u = st.text_input("User")
        p = st.text_input("Password", type="password")
        ok = st.form_submit_button("Sign in", type="primary")
    if ok:
        if hmac.compare_digest(u.encode(), APP_USER.encode()) & hmac.compare_digest(p.encode(), APP_PASSWORD.encode()):
            st.session_state["user"] = u
            st.rerun()
        else:
            st.error("Wrong user or password.")
    st.stop()

def logout_button():
    if APP_PASSWORD and st.sidebar.button("Sign out"):
        st.session_state.pop("user", None)
        st.rerun()
