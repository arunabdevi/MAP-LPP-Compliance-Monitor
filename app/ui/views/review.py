import re
from datetime import datetime
import pandas as pd
import streamlit as st
from ui import db, mailer
from ui.config import PROJECT_DIR, LETTER_DIR

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
STATUSES = ["Pending", "Approved", "Held", "Rejected", "Sent"]
EDITOR_STATUSES = STATUSES + ["Sending"]      # "Sending" exists only while an e-mail is being sent

def _letter_text(rel_path):
    """Reads a letter, but only from inside the letters folder (the path comes from the database)."""
    if not rel_path:
        return None
    p = (PROJECT_DIR / rel_path).resolve()
    if LETTER_DIR.resolve() not in p.parents:
        return "(letter path is outside the letters folder - not shown)"
    if not p.exists():
        return "(letter file not found on disk)"
    if p.suffix.lower() != ".txt":
        return f"(letter is a {p.suffix} file - open it from outputs/letters)"
    return p.read_text(encoding="utf-8", errors="replace")

def _clean(v):
    """Blank, None and NaN all mean 'no value'."""
    if v is None or (isinstance(v, float) and v != v):
        return None
    return str(v).strip() or None


def _send_section(run_date):
    st.subheader("Send approved letters")
    stuck = mailer.stuck_sending()
    if len(stuck):
        st.error(f"{len(stuck)} letter(s) are stuck in 'Sending' (the app was closed during a send). They may or may not have been "
                 "delivered - check the Sent folder of the Gmail account first. If they were NOT delivered, release them below.")
        st.dataframe(stuck, hide_index=True, width="stretch")
        c1, c2 = st.columns(2)
        if c1.button("They were delivered - mark as Sent"):
            db.execute("UPDATE ENFORCEMENT_QUEUE SET status = 'Sent', sent_at = NOW() WHERE status = 'Sending'"); st.rerun()
        if c2.button("They were NOT delivered - back to Approved"):
            db.execute("UPDATE ENFORCEMENT_QUEUE SET status = 'Approved' WHERE status = 'Sending'"); st.rerun()
        return
    plan = mailer.preview(run_date)
    if not plan:
        st.caption("No letters with status Approved for this run date.")
        return
    bad = [p for p in plan if p["problem"]]
    st.write(f"**{len(plan)}** approved letter(s) for {pd.Timestamp(run_date):%Y-%m-%d}; **{len(plan) - len(bad)}** can be sent now.")
    shown = pd.DataFrame([{"Seller": p["seller"], "Marketplace": p["marketplace"], "To": p["recipient_email"],
                           "Subject": p.get("subject"), "Problem": p["problem"], "Last send error": p.get("error")} for p in plan])
    with st.expander("Dry run - exactly what would be sent (nothing is sent by looking at this)", expanded=True):
        st.dataframe(shown, hide_index=True, width="stretch")
    if bad:
        st.warning(f"{len(bad)} letter(s) have a problem and will be skipped (they stay Approved).")
    state, why = mailer.status()
    if state != "ready":
        st.info(f"Gmail is not connected yet. {why}  (Settings > Gmail)")
        return
    limit = st.number_input("Send only the first N letters (use 1 for a first test; 0 = all)", 0, 1000, 1)
    sure = st.checkbox("I checked the list above and the letter wording. Send these e-mails now.")
    if st.button("Send approved letters", type="primary", disabled=not sure):
        box, lines = st.empty(), []
        def on_result(r):
            lines.append(("OK     " if r["ok"] else "FAILED ") + f"{r['seller']} / {r['marketplace']} -> {r['to']}"
                         + ("" if r["ok"] else f"  ({r['error']})"))
            box.code("\n".join(lines), language="text")
        try:
            with st.spinner("Sending..."):
                results = mailer.send_approved(run_date, limit=int(limit) or None, progress=on_result)
        except Exception as exc:
            st.error(f"Could not send: {exc}"); return
        ok = sum(r["ok"] for r in results)
        (st.success if ok == len(results) else st.warning)(f"{ok} of {len(results)} sent. Failed ones stay Approved - the reason is shown in the table above after you reload the page.")
        st.session_state["sent_msg"] = True


def render(user):
    st.title("Review & approve letters")
    st.caption("Approving only marks a letter as ready. Nothing is e-mailed until you use \"Send approved letters\" further down this page.")
    try:
        db.ensure_ui_tables()
        dates = db.query("SELECT DISTINCT run_date FROM ENFORCEMENT_QUEUE ORDER BY run_date DESC")["run_date"].tolist()
    except Exception as exc:
        st.error(f"Cannot read the approval queue: {str(exc)[:200]}"); return
    if not dates:
        st.info("The queue is empty. Run step **06** (Upload & run) to create letters for review.")
        return
    c1, c2, c3 = st.columns([1, 1.4, 1.4])
    run_date = c1.selectbox("Run date", dates, format_func=lambda d: pd.Timestamp(d).strftime("%Y-%m-%d"))
    actions = c2.multiselect("Action", ["Warning 1", "Warning 2", "Violation Letter"], default=[])
    status_filter = c3.multiselect("Status", STATUSES, default=[])
    q = db.query("SELECT queue_id, seller, marketplace, strike, action, skus, recipient_email, status, comment, approved_by, "
                 "approved_at, sent_at, letter_path FROM ENFORCEMENT_QUEUE WHERE run_date = :d ORDER BY strike DESC, seller, marketplace",
                 {"d": run_date})
    # fill empty recipient e-mails from the contact list (exact marketplace first, then the '*' entry)
    contacts = db.query("SELECT homologated_name AS seller, marketplace, email FROM SELLER_CONTACT WHERE email IS NOT NULL AND email <> ''")
    if not contacts.empty:
        exact = {(r.seller, r.marketplace): r.email for r in contacts.itertuples()}
        def lookup(r):
            return r.recipient_email if isinstance(r.recipient_email, str) and r.recipient_email else \
                exact.get((r.seller, r.marketplace)) or exact.get((r.seller, "*"))
        q["recipient_email"] = [lookup(r) for r in q.itertuples()]
    if actions:
        q = q[q["action"].isin(actions)]
    if status_filter:
        q = q[q["status"].isin(status_filter)]
    counts = db.query("SELECT status, COUNT(*) AS n FROM ENFORCEMENT_QUEUE WHERE run_date = :d GROUP BY status", {"d": run_date})
    cm = dict(zip(counts["status"], counts["n"]))
    m = st.columns(5)
    for col, s in zip(m, STATUSES):
        col.metric(s, int(cm.get(s, 0)))
    no_email = int((q["recipient_email"].isna() | (q["recipient_email"] == "")).sum())
    if no_email:
        st.warning(f"{no_email} letter(s) in this view have no recipient e-mail. Type one in the table, or add contacts on the Settings page.")

    flash = st.session_state.pop("review_flash", None)
    if flash:
        getattr(st, flash[0])(flash[1])

    view = q[["queue_id", "seller", "marketplace", "strike", "action", "skus", "recipient_email", "status", "comment"]].reset_index(drop=True)
    edited = st.data_editor(
        view, hide_index=True, width="stretch", height=420, key=f"queue_{run_date}_{len(view)}",
        disabled=["queue_id", "seller", "marketplace", "strike", "action", "skus"],
        column_config={"queue_id": None, "seller": "Seller", "marketplace": "Marketplace",
                       "strike": st.column_config.NumberColumn("Strike", width="small"), "action": "Action", "skus": "SKUs",
                       "recipient_email": st.column_config.TextColumn("Recipient e-mail"),
                       "status": st.column_config.SelectboxColumn("Status", options=EDITOR_STATUSES, required=True),
                       "comment": st.column_config.TextColumn("Comment", max_chars=500)})

    b1, b2, b3 = st.columns([1, 1.4, 3])
    save = b1.button("💾 Save changes", type="primary")
    approve_all = b2.button("Approve all pending with an e-mail")
    if save or approve_all:
        work = edited.copy()
        if approve_all:
            ok_mask = (work["status"] == "Pending") & work["recipient_email"].map(lambda e: bool(_clean(e) and EMAIL_RE.match(_clean(e))))
            work.loc[ok_mask, "status"] = "Approved"
            n_pending = int((edited["status"] == "Pending").sum())
            n_ok, n_noemail = int(ok_mask.sum()), n_pending - int(ok_mask.sum())
            if n_pending == 0:
                st.info("There are no Pending letters in the table above (check the Status filter).")
            elif n_ok == 0:
                st.warning(f"None of the {n_pending} pending letters has a valid recipient e-mail, so nothing was approved. "
                           "Type an address in the 'Recipient e-mail' column (then click Save changes), or add the seller's "
                           "address under Settings > Seller contacts.")
            elif n_noemail:
                st.session_state["approve_note"] = f"{n_noemail} pending letter(s) were left Pending because they have no valid e-mail."
        orig = view.set_index("queue_id")
        problems, changed = [], 0
        for r in work.itertuples():
            o = orig.loc[r.queue_id]
            new_email = _clean(r.recipient_email)
            new_comment = _clean(r.comment)
            if (r.status, new_email, new_comment) == (o["status"], _clean(o["recipient_email"]), _clean(o["comment"])):
                continue
            if o["status"] in ("Sent", "Sending"):
                problems.append(f"{r.seller} / {r.marketplace}: already {o['status'].lower()} - cannot be changed"); continue
            if r.status == "Sending":
                problems.append(f"{r.seller} / {r.marketplace}: 'Sending' is set only by the sending step"); continue
            if r.status == "Sent":
                problems.append(f"{r.seller} / {r.marketplace}: 'Sent' is set only by the sending step"); continue
            if new_email and not EMAIL_RE.match(new_email):
                problems.append(f"{r.seller} / {r.marketplace}: '{new_email}' is not a valid e-mail address"); continue
            if r.status == "Approved" and not new_email:
                problems.append(f"{r.seller} / {r.marketplace}: cannot approve without a recipient e-mail"); continue
            became_approved = r.status == "Approved" and o["status"] != "Approved"
            db.execute("UPDATE ENFORCEMENT_QUEUE SET status = :s, recipient_email = :e, comment = :c, "
                       "approved_by = CASE WHEN :s = 'Approved' THEN COALESCE(:u, approved_by) ELSE NULL END, "
                       "approved_at = CASE WHEN :s = 'Approved' THEN IF(:b, NOW(), approved_at) ELSE NULL END WHERE queue_id = :id AND status NOT IN ('Sent', 'Sending')",
                       {"s": r.status, "e": new_email, "c": new_comment, "u": user if r.status == "Approved" else None,
                        "b": 1 if became_approved else 0, "id": int(r.queue_id)})
            changed += 1
        note = st.session_state.pop("approve_note", "")
        if changed:
            msg = f"{changed} letter(s) updated." + (f" {note}" if note else "")
            if not problems:
                st.session_state["review_flash"] = ("success", msg)
                st.rerun()
            st.success(msg)
        elif not approve_all and not problems:
            st.info("Nothing to save - no changes were made in the table.")
        for p in problems:
            st.error(p)

    _send_section(run_date)

    st.subheader("Letter preview")
    if view.empty:
        st.caption("No letters match the filters.")
        return
    labels = {int(r.queue_id): f"{r.seller}  |  {r.marketplace}  |  {r.action}" for r in view.itertuples()}
    pick = st.selectbox("Choose a letter", list(labels), format_func=labels.get)
    path = q.loc[q["queue_id"] == pick, "letter_path"].iloc[0]
    st.code(_letter_text(path) or "(no letter file recorded)", language="text")

    approved = q[q["status"] == "Approved"]
    if len(approved):
        st.download_button(f"Download list of {len(approved)} approved letter(s) (CSV)",
                           approved[["seller", "marketplace", "strike", "action", "recipient_email", "approved_by", "approved_at", "letter_path"]]
                           .to_csv(index=False).encode("utf-8-sig"), f"approved_{pd.Timestamp(run_date):%Y-%m-%d}.csv", "text/csv")
