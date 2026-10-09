"""Sends the APPROVED letters through the Gmail API (scope: gmail.send only - it cannot read your mailbox).

Safety rules built in:
  * only rows with status 'Approved' are ever sent;
  * a row is claimed ('Sending') in the database BEFORE the e-mail goes out, so two clicks, two browser tabs
    or a scheduled job can never send the same letter twice;
  * a row becomes 'Sent' only after Gmail accepted the message; on any error it goes back to 'Approved'
    with the error text, so it can be retried;
  * a dry run lists exactly what would be sent and sends nothing.
"""
import base64, mimetypes, re
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from ui import db, settings_store
from ui.config import PROJECT_DIR, LETTER_DIR

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
GMAIL_DIR = PROJECT_DIR / "gmail"                   # holds credentials.json (you add) and token.json (created at sign-in)
CREDENTIALS_FILE = GMAIL_DIR / "credentials.json"
TOKEN_FILE = GMAIL_DIR / "token.json"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ----------------------------------------------------------------------------- sign-in
def status():
    """('ready' | 'need_signin' | 'need_credentials' | 'missing_libs', explanation)"""
    try:
        import google.oauth2.credentials, googleapiclient.discovery, google_auth_oauthlib.flow  # noqa: F401
    except ImportError:
        return "missing_libs", "Run: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
    if not CREDENTIALS_FILE.exists() and not TOKEN_FILE.exists():
        return "need_credentials", f"Put the credentials.json file from Google Cloud into: {GMAIL_DIR}"
    if not TOKEN_FILE.exists():
        return "need_signin", "credentials.json found. Click 'Sign in with Google' once."
    return "ready", "Signed in."


def sign_in():
    """Opens the Google sign-in page in your browser (works only when the app runs on the computer you are using)."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    GMAIL_DIR.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", open_browser=True,
                                  authorization_prompt_message="", success_message="Signed in. You can close this tab.")
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    try:
        TOKEN_FILE.chmod(0o600)
    except OSError:
        pass


def sign_out():
    TOKEN_FILE.unlink(missing_ok=True)


def gmail_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        else:
            raise RuntimeError("The Gmail sign-in has expired. Sign in with Google again.")
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def sender_address(service=None):
    """The send-only permission cannot look up the account's address (that needs a wider scope), so the From header
    is left to Gmail (it always uses the signed-in account). An address typed in Settings is used only for the
    display name; Gmail ignores a From address that is not the signed-in account."""
    return (settings_store.load().get("MAIL_FROM_ADDRESS") or "").strip()


# ----------------------------------------------------------------------------- building a message
def _letter_files(rel_path):
    """Returns (txt_path or None, pdf_path or None) for a queue row. Only files inside the letters folder."""
    if not rel_path:
        return None, None
    base = (PROJECT_DIR / rel_path).resolve()
    out = {}
    for ext in (".txt", ".pdf"):
        p = base.with_suffix(ext)
        if p.exists() and LETTER_DIR.resolve() in p.parents:
            out[ext] = p
    return out.get(".txt"), out.get(".pdf")


def build_message(row, sender, settings, bcc=None):
    """row: dict with seller, marketplace, action, strike, recipient_email, letter_path."""
    txt, pdf = _letter_files(row["letter_path"])
    if not txt and not pdf:
        raise FileNotFoundError("letter file not found on disk")
    subject_tpl = settings.get("MAIL_SUBJECT") or "Pricing policy notice - {action} - {seller}"
    subject = subject_tpl.format(action=row["action"], seller=row["seller"], marketplace=row["marketplace"],
                                 strike=row["strike"], company=settings.get("MANUFACTURER_NAME", ""))
    subject = re.sub(r"[\r\n]+", " ", subject).strip()               # no header injection
    msg = EmailMessage()
    msg["To"] = row["recipient_email"]
    name = (settings.get("MAIL_FROM_NAME") or "").strip()
    if sender and name:
        msg["From"] = formataddr((name, sender))
    elif sender:
        msg["From"] = sender            # otherwise no From header: Gmail fills in the signed-in account
    msg["Subject"] = subject
    if bcc:
        msg["Bcc"] = bcc
    if txt:
        msg.set_content(txt.read_text(encoding="utf-8", errors="replace"))
    else:
        msg.set_content(f"Please find the {row['action']} regarding {row['seller']} on {row['marketplace']} attached.")
    if settings.get("MAIL_ATTACH", True):
        for p in (txt, pdf):
            if p:
                ctype, _ = mimetypes.guess_type(p.name)
                main, sub = (ctype or "application/octet-stream").split("/", 1)
                msg.add_attachment(p.read_bytes(), maintype=main, subtype=sub, filename=p.name)
    return msg


# ----------------------------------------------------------------------------- sending
APPROVED_SQL = ("SELECT queue_id, seller, marketplace, strike, action, recipient_email, letter_path, run_date, error "
                "FROM ENFORCEMENT_QUEUE WHERE status = 'Approved' ")


def approved_rows(run_date=None, ids=None):
    sql, params = APPROVED_SQL, {}
    if run_date:
        sql += "AND run_date = :d "; params["d"] = str(run_date)
    sql += "ORDER BY seller, marketplace"
    df = db.query(sql, params)
    if ids is not None:
        df = df[df["queue_id"].isin(ids)]
    return df


def preview(run_date=None):
    """Dry run: one line per letter, with a problem text if it could not be sent."""
    settings = settings_store.load()
    out = []
    for r in approved_rows(run_date).to_dict("records"):
        problem = None
        if not r["recipient_email"] or not EMAIL_RE.match(str(r["recipient_email"])):
            problem = "no valid recipient e-mail"
        else:
            try:
                msg = build_message(r, "me@example.com", settings)
                r["subject"] = msg["Subject"]
            except Exception as exc:
                problem = str(exc)
        r["problem"] = problem
        out.append(r)
    return out


def send_approved(run_date=None, service=None, sender=None, ids=None, limit=None, progress=None):
    """Sends the approved letters. Returns a list of result dicts. `service` can be replaced in tests."""
    settings = settings_store.load()
    service = service or gmail_service()
    sender = sender_address(service) if sender is None else sender
    bcc = (settings.get("MAIL_BCC") or "").strip() or None
    if bcc and not EMAIL_RE.match(bcc):
        raise ValueError(f"The Bcc address '{bcc}' is not a valid e-mail address (Settings > Company & letters).")
    rows = approved_rows(run_date, ids).to_dict("records")
    if limit:
        rows = rows[:limit]
    results = []
    for r in rows:
        qid = int(r["queue_id"])
        res = {"queue_id": qid, "seller": r["seller"], "marketplace": r["marketplace"], "to": r["recipient_email"]}
        # claim the row; if somebody else already did, rowcount is 0 and we skip it
        claimed = db.execute("UPDATE ENFORCEMENT_QUEUE SET status = 'Sending', error = NULL "
                             "WHERE queue_id = :id AND status = 'Approved'", {"id": qid})
        if not claimed:
            res.update(ok=False, error="skipped - no longer in 'Approved' status"); results.append(res); continue
        try:
            if not r["recipient_email"] or not EMAIL_RE.match(str(r["recipient_email"])):
                raise ValueError("no valid recipient e-mail")
            msg = build_message(r, sender, settings, bcc)
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"[:490]
            db.execute("UPDATE ENFORCEMENT_QUEUE SET status = 'Approved', error = :e WHERE queue_id = :id",
                       {"e": err, "id": qid})
            res.update(ok=False, error=err)
        else:
            db.execute("UPDATE ENFORCEMENT_QUEUE SET status = 'Sent', sent_at = NOW(), gmail_message_id = :m, error = NULL "
                       "WHERE queue_id = :id", {"m": sent.get("id"), "id": qid})
            res.update(ok=True, message_id=sent.get("id"))
        results.append(res)
        if progress:
            progress(res)
    return results


def stuck_sending():
    """Rows left in 'Sending' (the app was closed mid-send). They may or may not have been delivered."""
    return db.query("SELECT queue_id, seller, marketplace, recipient_email FROM ENFORCEMENT_QUEUE WHERE status = 'Sending'")
