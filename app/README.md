# MAP / LPP Compliance – web UI (local test)

A Streamlit app on top of the MAP/LPP pipeline. Pages: **Dashboard**, **Upload & run**, **Violations**,
**Review & approve**, **Settings**. Approving a letter only marks it *Approved* in the database –
nothing is e-mailed until you use **Send approved letters** (Gmail; see the last section).

## 1. One-time setup
You need Python 3.10+ and a MySQL 8 server. Easiest MySQL: Docker Desktop.

```bash
cd map_ui
python -m venv .venv
.venv\Scripts\activate            # Windows      (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt

docker compose up -d              # starts MySQL 8 (root password: change-me)
copy .env.example .env            # Mac/Linux: cp .env.example .env   -> then edit the passwords
```
No Docker? Install MySQL yourself and set `MAP_DB_HOST/USER/PASS` in `.env`. The app creates the
database `map_compliance` itself. For AWS RDS, only those `MAP_DB_*` values change.

## 2. Start
```bash
streamlit run app.py
```
Open http://localhost:8501 and sign in with `APP_USER` / `APP_PASSWORD` from `.env`
(leave `APP_PASSWORD` empty to switch the login off – own computer only).

## 3. First run with the sample data
1. **Upload & run** → *Copy sample data into the project* (synthetic data, 300 SKUs, 15 days).
2. Choose **Full setup** and press **Run now** (about a minute).
3. Look at **Dashboard** and **Violations**; open **Review & approve**, add recipient e-mails
   (or add contacts in **Settings → Seller contacts**), then approve.

With your real files: upload the five source files and the daily seller CSVs (`YYYY-MM-DD.csv`)
in step 1 instead. Day to day, run **Daily run** after dropping in a new seller file.

## Notes
* Files (letters, charts, Excel reports, logs, settings.json) go to `./MAP_Compliance_Project`
  (change with `MAP_PROJECT_DIR`, e.g. `C:/MAP_Compliance_Project`).
* Settings changes (quarter definition, strike that triggers a letter, LPP percentages, company
  name, …) apply from the next run. If a seller's action changes (e.g. Warning 2 → Violation Letter),
  its queue row goes back to *Pending*; rows already *Sent* never change.
* Exchange rates come from open.er-api.com; offline, the last saved rates or a built-in fallback are used
  (the run log says which).
* The same pipeline runs without the UI: `python run_step.py daily` (or `full`, or step numbers like `05 06`)
  – this is what cron will call on AWS.
* `steps/` is generated from the Colab notebooks by `python build_steps.py <notebook folder>`.

## Sending the approved letters by Gmail
1. One-time: **Settings > Gmail** shows the Google Cloud steps (Gmail API, OAuth consent screen, Desktop-app
   credentials). Save the downloaded file as `credentials.json` in `MAP_Compliance_Project/gmail/`, reload,
   then click **Sign in with Google**. The permission asked for is *send only*.
2. Set the subject, sender name and an optional Bcc copy address in the same tab.
3. **Review & approve > Send approved letters** shows a dry run (who gets what). Tick the confirmation box and
   send. The box is set to send only **1** letter by default - use that first and send it to your own address.
4. A letter becomes *Sent* only after Gmail accepts it. Failures stay *Approved* with the error shown; a letter
   already *Sent* can never be sent again.

`credentials.json` and `token.json` give access to the sending mailbox: keep them private and never share the folder.
