# Colab notebooks

The same pipeline as the web app, split into one notebook per workflow. Every code cell is preceded by a
"What this cell does / Purpose" note.

| # | Notebook | What it does |
|---|---|---|
| 00 | Project_Setup | Drive folders, the shared helper `map_common.py`, MySQL ready |
| 01 | Architecture_Diagram | Draws the end-to-end architecture diagram |
| 02 | Data_Cleaning_and_MySQL_Tables | Cleans the source files and loads six master tables |
| 03 | Flipkart_Scraper | Exploratory proof of concept: collects live prices with a headless browser (optional) |
| 04 | Seller_Table_Update | Validates and loads the daily seller price files |
| 05 | MAP_LPP_Compliance_Logic | Classifies every price observation (MAP / LPP rules) |
| 06 | Enforcement_Letters_and_Summary | Strike logic, letters, Excel summary, approval queue |
| 07 | Charts_and_Reports | 15 charts, PDF pack, Excel report |

Run 00, 01, 02, then 04 to 07 (notebook 03 is optional) for each new day of seller data. Put your own (or the synthetic sample) files in
`raw_data/` and `seller_data/` on Google Drive. Notebook 03 is a stand-alone proof of concept for producing those files
automatically; check the site's terms of use before running it.

`map_common.py` is the shared helper (folders, database start-up, backup/restore, exchange rates). No password is
stored in any notebook: use the `MAP_DB_PASS` environment variable or a Colab Secret.
