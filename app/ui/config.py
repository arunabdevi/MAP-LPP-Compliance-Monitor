"""Paths, environment and the shared helper module. Imported first by everything else."""
import os, sys, shutil
from pathlib import Path
from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent.parent
load_dotenv(APP_DIR / ".env")
os.environ.setdefault("MAP_DB_MODE", "remote")        # never try to install MySQL on your own computer
os.environ.setdefault("MPLBACKEND", "Agg")

PROJECT_DIR = Path(os.environ.get("MAP_PROJECT_DIR") or APP_DIR / "MAP_Compliance_Project").resolve()
PROJECT_DIR.mkdir(parents=True, exist_ok=True)

# keep the shared helper next to the data folders (it treats its own folder as the project folder)
_src, _dst = APP_DIR / "map_common.py", PROJECT_DIR / "map_common.py"
if _src.exists() and (not _dst.exists() or _dst.read_bytes() != _src.read_bytes()):
    shutil.copyfile(_src, _dst)
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
import map_common as mc          # noqa: E402
mc.ensure_dirs()

RAW_DIR, SELLER_DIR = Path(mc.RAW_DIR), Path(mc.SELLER_DIR)
LETTER_DIR, REPORT_DIR, CHART_DIR = Path(mc.LETTER_DIR), Path(mc.REPORT_DIR), Path(mc.CHART_DIR)
LOG_DIR = PROJECT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = PROJECT_DIR / "settings.json"
SAMPLE_DIR = APP_DIR / "sample_data"

REQUIRED_RAW = {   # exact names the cleaning step looks for
    "SKU Table.xml": ["xml"], "PL Table.json": ["json"], "Price List Table.yaml": ["yaml", "yml"],
    "Seller Mapping Table.xlsx": ["xlsx"], "Promotion Table.xlsx": ["xlsx"],
}
SELLER_COLUMNS = ["SKU", "Marketplace", "Seller_name", "region", "adv_price", "Screenshot", "live_link"]

APP_USER = os.environ.get("APP_USER", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
