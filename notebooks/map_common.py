"""
map_common.py  --  shared helpers for the MAP/LPP Compliance project (Google Colab).

This file lives in your project folder on Google Drive. It is written there by notebook
00_Project_Setup and imported by notebooks 02-07, so the folder layout, the database start-up
and the exchange-rate logic exist in ONE place instead of being copied into every notebook.
"""
import os, sys, json, glob, shutil, subprocess, time, getpass, importlib
from datetime import date, datetime

# ----------------------------------------------------------------------------- folders
# The project folder is simply the folder this file sits in.
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

def _p(*parts):
    return os.path.join(PROJECT_DIR, *parts)

RAW_DIR      = _p("raw_data")                 # the manufacturer's source files (xml/json/yaml/xlsx)
CLEAN_DIR    = _p("cleaned_data")             # the six cleaned tables as CSV
SELLER_DIR   = _p("seller_data")              # daily seller price files, one per day: YYYY-MM-DD.csv
SCRAPER_DIR  = _p("scraper_output")           # Flipkart scraper CSV + screenshots
OUT_DIR      = _p("outputs")
ARCH_DIR     = _p("outputs", "architecture")
LETTER_DIR   = _p("outputs", "letters")
SUMMARY_DIR  = _p("outputs", "summaries")
CHART_DIR    = _p("outputs", "charts")
REPORT_DIR   = _p("outputs", "reports")
BACKUP_DIR   = _p("db_backup")                # MySQL dump so the database survives Colab restarts
CACHE_DIR    = _p("cache")                    # exchange-rate snapshots

ALL_DIRS = [RAW_DIR, CLEAN_DIR, SELLER_DIR, SCRAPER_DIR, OUT_DIR, ARCH_DIR, LETTER_DIR,
            SUMMARY_DIR, CHART_DIR, REPORT_DIR, BACKUP_DIR, CACHE_DIR]

def ensure_dirs():
    for d in ALL_DIRS:
        os.makedirs(d, exist_ok=True)

def find_raw(filename):
    """Find a raw source file in raw_data/ (or, for convenience, directly in the project folder)."""
    for folder in (RAW_DIR, PROJECT_DIR):
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        f"'{filename}' was not found in {RAW_DIR} (or {PROJECT_DIR}). "
        f"Upload the source file to that Drive folder and run the cell again.")

def ensure_packages(packages):
    """pip-install any package that is missing. packages = {import_name: pip_name}."""
    missing = []
    for imp, pip_name in packages.items():
        try:
            importlib.import_module(imp)
        except ImportError:
            missing.append(pip_name)
    if missing:
        print("Installing:", ", ".join(missing))
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", *missing], check=True)

# ----------------------------------------------------------------------------- database settings
DB_MODE = os.environ.get("MAP_DB_MODE", "colab_local")   # "colab_local" or "remote"
DB_HOST = os.environ.get("MAP_DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("MAP_DB_PORT", "3306"))
DB_USER = os.environ.get("MAP_DB_USER", "root")
DB_NAME = os.environ.get("MAP_DB_NAME", "map_compliance")
_PASSWORD = None

def _db_password():
    """Password lookup order: environment variable -> Colab Secret 'MAP_DB_PASS' -> default for the
    throw-away MySQL inside the Colab VM -> prompt (remote mode only). Never stored in a notebook."""
    global _PASSWORD
    if _PASSWORD:
        return _PASSWORD
    pw = os.environ.get("MAP_DB_PASS")
    if not pw:
        try:
            from google.colab import userdata
            pw = userdata.get("MAP_DB_PASS")
        except Exception:
            pw = None
    if not pw:
        pw = "colab_local_pw" if DB_MODE == "colab_local" else getpass.getpass("MySQL password: ")
    _PASSWORD = pw
    return pw

def _run(cmd, check=True, stdin=None, stdout=None, env=None):
    res = subprocess.run(cmd, check=False, stdin=stdin, stdout=stdout,
                         stderr=subprocess.PIPE, text=True, env=env)
    if check and res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {' '.join(cmd[:3])} ...\n{(res.stderr or '').strip()}")
    return res

def _mysql_env():
    env = dict(os.environ)
    env["MYSQL_PWD"] = _db_password()          # keeps the password off the command line
    return env

def _can_connect():
    import pymysql
    try:
        c = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=_db_password(), connect_timeout=3)
        c.close()
        return True
    except Exception:
        return False

def start_mysql():
    """Colab mode: install MySQL 8 inside this Colab VM (first time only), start it, set the root
    password. Both modes: make sure the project database exists (remote mode needs no install)."""
    ensure_packages({"pymysql": "pymysql", "sqlalchemy": "sqlalchemy", "cryptography": "cryptography"})
    if DB_MODE == "colab_local":
        if _can_connect():
            print("MySQL is already running and reachable.")
        else:
            if shutil.which("mysqld") is None:
                print("Installing MySQL server in this Colab VM (about 1-2 minutes, first time per session)...")
                env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
                _run(["apt-get", "update", "-qq"], check=False, env=env)
                _run(["apt-get", "install", "-y", "-qq", "mysql-server"], env=env)
            print("Starting MySQL...")
            _run(["service", "mysql", "start"], check=False)
            for _ in range(60):                                   # wait up to ~60 s for the server
                if _run(["mysqladmin", "ping", "--silent"], check=False).returncode == 0 or _can_connect():
                    break
                time.sleep(1)
            if not _can_connect():                                # fresh install: root has no password yet
                pw = _db_password().replace("\\", "\\\\").replace("'", "\\'")
                _run(["mysql", "-uroot", "-e",
                      f"ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '{pw}'; FLUSH PRIVILEGES;"])
            if not _can_connect():
                raise RuntimeError("MySQL started but the connection test failed. Re-run the cell, or "
                                   "Runtime > Restart session and try again.")
    else:
        print("DB_MODE = remote -> using the MySQL server at", DB_HOST)
        if not _can_connect():
            raise RuntimeError(f"Cannot connect to MySQL at {DB_HOST}:{DB_PORT} as '{DB_USER}'. Check MAP_DB_HOST / MAP_DB_PORT / "
                               f"MAP_DB_USER / MAP_DB_PASS, that the server is running and that its firewall allows this computer.")
    import pymysql                                   # create the database without needing the mysql command-line tool
    conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=_db_password(), connect_timeout=10)
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.commit()
    finally:
        conn.close()
    print(f"MySQL ready. Database '{DB_NAME}' exists.")

def get_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL
    url = URL.create("mysql+pymysql", username=DB_USER, password=_db_password(),
                     host=DB_HOST, port=DB_PORT, database=DB_NAME)
    return create_engine(url, pool_pre_ping=True)

def table_count(engine):
    from sqlalchemy import text
    with engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = :d"),
                            {"d": DB_NAME}).scalar()

# ----------------------------------------------------------------------------- backup / restore
LATEST_DUMP = _p("db_backup", "map_compliance_latest.sql")

def db_backup(keep=3):
    """Save the whole database to Drive so the next notebook (a new Colab VM) can restore it."""
    if DB_MODE != "colab_local":
        print("Remote database: no backup needed here (it already persists on the server).")
        return None
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stamped = _p("db_backup", f"map_compliance_{stamp}.sql")
    with open(stamped, "w", encoding="utf-8") as f:
        _run(["mysqldump", f"-h{DB_HOST}", f"-P{DB_PORT}", f"-u{DB_USER}", "--single-transaction",
              "--routines", "--no-tablespaces", DB_NAME], stdout=f, env=_mysql_env())
    shutil.copyfile(stamped, LATEST_DUMP)
    old = sorted(glob.glob(_p("db_backup", "map_compliance_2*.sql")))
    for path in old[:-keep]:
        os.remove(path)
    print(f"Database backed up to Drive: {LATEST_DUMP}  ({os.path.getsize(LATEST_DUMP)/1e6:.1f} MB)")
    return LATEST_DUMP

def db_restore(engine=None):
    """If this VM's database is empty and a backup exists on Drive, load the backup."""
    if DB_MODE != "colab_local":
        return False
    engine = engine or get_engine()
    if table_count(engine) > 0:
        print(f"Database already contains {table_count(engine)} table(s) - nothing to restore.")
        return False
    if not os.path.exists(LATEST_DUMP):
        print("No database backup found yet (normal for the first run).")
        return False
    print("Restoring database from the Drive backup...")
    with open(LATEST_DUMP, "r", encoding="utf-8") as f:
        _run(["mysql", f"-h{DB_HOST}", f"-P{DB_PORT}", f"-u{DB_USER}", DB_NAME], stdin=f, env=_mysql_env())
    print(f"Restored. Tables now in database: {table_count(engine)}")
    return True

def connect_db():
    """One call used by every notebook: start MySQL if needed, restore the backup, return an engine."""
    ensure_dirs()
    start_mysql()
    engine = get_engine()
    db_restore(engine)
    return engine

# ----------------------------------------------------------------------------- exchange rates
FALLBACK_FX = {"USD": 0.010373, "GBP": 0.007857, "AED": 0.038083, "CAD": 0.014795, "INR": 1.0}

def get_fx_rates(base="INR", force_refresh=False):
    """Rates are 'units of currency per 1 unit of base' (so 1 INR buys 0.0104 USD).
    Order: today's cached snapshot -> live API (open.er-api.com) -> newest older snapshot -> built-in
    fallback. Every successful live call is saved, so any run can be reproduced later.
    Returns (rates_dict, source_description)."""
    import requests
    os.makedirs(CACHE_DIR, exist_ok=True)
    today = date.today().isoformat()
    cache = _p("cache", f"fx_rates_{base}_{today}.json")
    if os.path.exists(cache) and not force_refresh:
        with open(cache) as f:
            return json.load(f), f"cached snapshot of {today}"
    try:
        resp = requests.get(f"https://open.er-api.com/v6/latest/{base}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("result") != "success":
            raise RuntimeError(f"FX API did not return success: {data}")
        with open(cache, "w") as f:
            json.dump(data["rates"], f)
        return data["rates"], "live API (open.er-api.com)"
    except Exception as exc:
        older = sorted(glob.glob(_p("cache", f"fx_rates_{base}_*.json")))
        if older:
            with open(older[-1]) as f:
                return json.load(f), f"OLDER cached snapshot {os.path.basename(older[-1])} (live API failed: {exc})"
        return dict(FALLBACK_FX), f"BUILT-IN FALLBACK rates from the 5 Jan 2026 run (live API failed: {exc})"
