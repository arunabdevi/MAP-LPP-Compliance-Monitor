"""Settings that change how the pipeline runs. Saved in settings.json inside the project folder, so the web
app, scheduled runs (cron) and the command line all use the same values."""
import json
from ui.config import SETTINGS_FILE

DEFAULT_LPP = {  # sub-category: [HP %, DELL %]
    "LAPTOP": [3.4, 7.8], "MONITOR": [1.2, 5.6], "TONNER": [9.1, 2.3], "LASERJET": [6.5, 3.5],
    "INKJET": [1.2, 5.6], "DESKTOP": [9.1, 2.3], "INK": [6.5, 3.5]}

DEFAULTS = {
    "QUARTER_MODE": "fiscal",            # fiscal | calendar
    "FORCE_FX_REFRESH": False,
    "LETTER_AT": 3,
    "LETTER_FORMAT": "txt",              # txt | pdf | both
    "MANUFACTURER_NAME": "[Manufacturer Name]",
    "CONTACT_LINE": "[Channel Compliance Team | e-mail | phone]",
    "RESPONSE_DAYS": 7,
    "RUN_DATES": None,                   # None = latest | "ALL" | ["2026-01-05", ...]
    "REPLACE_EXISTING_DAYS": True,
    "FOCUS_DATE": None,                  # None = latest date in data
    "TOP_N": 20,
    "MAIL_SUBJECT": "Pricing policy notice - {action} - {seller}",   # {action} {seller} {marketplace} {strike} {company}
    "MAIL_FROM_NAME": "",
    "MAIL_FROM_ADDRESS": "",             # only needed together with a sender name; must be the signed-in Gmail address                # shown as the sender name, e.g. "Channel Compliance"
    "MAIL_BCC": "",                      # optional: a copy of every e-mail goes here
    "MAIL_ATTACH": True,                 # attach the letter file
    "LPP_LOGIC": DEFAULT_LPP,
}

def load():
    data = dict(DEFAULTS)
    if SETTINGS_FILE.exists():
        try:
            data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return data

def save(values):
    merged = load(); merged.update(values)
    SETTINGS_FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged
