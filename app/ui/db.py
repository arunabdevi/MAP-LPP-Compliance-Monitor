"""Database access for the web app (uses the same settings as the notebooks)."""
import pandas as pd
import streamlit as st
from sqlalchemy import text, bindparam
from ui.config import mc

UI_TABLES_DDL = [
    """CREATE TABLE IF NOT EXISTS SELLER_CONTACT (
        homologated_name VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
        marketplace      VARCHAR(150) COLLATE utf8mb4_bin NOT NULL DEFAULT '*',
        email            VARCHAR(255),
        contact_person   VARCHAR(255),
        PRIMARY KEY (homologated_name, marketplace)) ENGINE=InnoDB""",
    """CREATE TABLE IF NOT EXISTS ENFORCEMENT_QUEUE (
        queue_id         INT AUTO_INCREMENT PRIMARY KEY,
        run_date         DATE NOT NULL,
        seller           VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
        marketplace      VARCHAR(150) COLLATE utf8mb4_bin NOT NULL,
        strike           INT,
        action           VARCHAR(30),
        skus             TEXT,
        letter_path      VARCHAR(1000),
        recipient_email  VARCHAR(255),
        status           VARCHAR(20) NOT NULL DEFAULT 'Pending',
        comment          VARCHAR(500),
        approved_by      VARCHAR(100),
        approved_at      DATETIME,
        sent_at          DATETIME,
        gmail_message_id VARCHAR(100),
        error            VARCHAR(500),
        created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY UQ_QUEUE (run_date, seller, marketplace)) ENGINE=InnoDB""",
]

@st.cache_resource(show_spinner=False)
def engine():
    mc.start_mysql()                       # in remote mode: just makes sure the database exists
    return mc.get_engine()

def connection_ok():
    try:
        with engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, ""
    except Exception as exc:               # shown to the user, never contains the password
        return False, str(exc).splitlines()[0][:300]

def ensure_ui_tables():
    with engine().begin() as conn:
        for stmt in UI_TABLES_DDL:
            conn.execute(text(stmt))

def table_exists(name):
    with engine().connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = :d AND table_name = :t"),
                            {"d": mc.DB_NAME, "t": name}).scalar() > 0

def query(sql, params=None, expanding=()):
    """Run a SELECT and return a DataFrame. Names listed in `expanding` are lists used with IN :name."""
    stmt = text(sql)
    if expanding:
        stmt = stmt.bindparams(*[bindparam(n, expanding=True) for n in expanding])
    with engine().connect() as conn:
        return pd.read_sql(stmt, conn, params=params or {})

def execute(sql, params=None):
    with engine().begin() as conn:
        return conn.execute(text(sql), params or {}).rowcount

def table_counts(names):
    out = {}
    with engine().connect() as conn:
        for n in names:
            try:
                out[n] = conn.execute(text(f"SELECT COUNT(*) FROM `{n}`")).scalar()
            except Exception:
                out[n] = None
    return out
