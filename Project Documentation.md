# MAP / LPP Compliance Monitor

### An End-to-End Pricing Intelligence, Compliance Automation & Audit Solution

## Project Overview

The MAP / LPP Compliance Monitor is an end-to-end proof of concept designed to automate manufacturer pricing-policy monitoring, reseller compliance checks, violation tracking, and enforcement workflows.

Manufacturers selling through multiple resellers and marketplaces face a recurring operational challenge: validating advertised prices against product-specific pricing policies, accounting for approved promotions, maintaining reliable evidence, and applying consistent enforcement actions.

This project addresses that challenge by integrating **data ingestion, data quality validation, pricing rule evaluation, relational database management, compliance reporting, and human-reviewed email enforcement** into a unified workflow.

Built with Python, pandas, MySQL, Streamlit, and the Gmail API, the solution transforms structured manufacturer data and daily reseller price files into traceable compliance decisions and actionable business insights.

## Business Problem

Manual pricing-policy monitoring becomes difficult to scale when product catalogs, reseller networks, marketplaces, currencies, and promotional exceptions increase.

The system is designed to address five key challenges:

* **Data quality:** Identify missing, invalid, duplicate, and unmapped product records before processing.
* **Pricing accuracy:** Evaluate advertised prices against MAP (Minimum Advertised Price) and LPP (Lowest Permitted Price) rules.
* **Promotion handling:** Apply approved price-promotion rules without allowing promotions to override LPP restrictions.
* **Consistent enforcement:** Track recurring violations and apply a configurable warning and violation-letter escalation process.
* **Auditability:** Preserve price history, document rejected records, and maintain a reviewable record of compliance and enforcement actions.

## Key Features

1. **Multi-format master-data ingestion** — Load manufacturer data from XML, JSON, YAML, and Excel into MySQL master tables.
2. **Data quality and validation** — Validate daily seller CSV files and quarantine rejected records with explanatory reasons instead of silently discarding them.
3. **MAP/LPP compliance engine** — Apply ordered pricing rules, promotional exceptions, and currency conversion to classify price observations.
4. **Seller-level escalation** — Track violations by seller and marketplace, issue configurable warnings, and generate violation letters after repeated violations.
5. **Human-in-the-loop enforcement** — Provide a Streamlit approval workflow to review, edit, approve, hold, and send enforcement letters.
6. **Reporting and analytics** — Generate interactive dashboards, 15 charts, PDF reports, and Excel summaries for compliance monitoring.
7. **Email automation safeguards** — Integrate the Gmail API with a dry-run workflow and controlled sending states to reduce duplicate or unintended emails.
8. **Exploratory price collection** — Include a separate Selenium-based scraper proof of concept that captures product prices, seller details, product identifiers, links, and screenshots where permitted.

## Technical Architecture

Manufacturer master files and daily reseller price files feed a validation and transformation pipeline. The pricing engine evaluates each observation against configured MAP, LPP, and promotion rules. Results are stored in MySQL to support strike tracking, enforcement workflows, dashboards, and audit reporting.

The solution is available through documented Google Colab notebooks and a Streamlit application, with command-line scripts for running the processing steps.

## Technology Stack

* **Programming & data processing:** Python, pandas
* **Database:** MySQL 8, SQLAlchemy
* **Data ingestion:** XML, JSON, YAML, Excel, CSV
* **Application & visualization:** Streamlit, matplotlib
* **Reporting:** openpyxl, ReportLab, Excel and PDF outputs
* **Automation & integration:** Gmail API, OAuth
* **Web data collection POC:** Selenium, headless Chrome
* **Development & deployment support:** Google Colab, Docker Compose

## Engineering Principles

The implementation emphasizes reliable and explainable processing:

* Missing values remain unknown rather than being silently converted to zero.
* Invalid records are quarantined with rejection reasons.
* Daily loads are designed to be safely rerun.
* Seller and marketplace identities are handled explicitly.
* Enforcement letters require human approval before sending.
* Email delivery uses controlled status transitions to reduce duplicate sends.
* Credentials are kept outside source code.

## Current Status and Scope

This is a proof of concept tested locally with MySQL 8 and synthetic sample data. The core application includes pricing-rule evaluation, reporting, review workflows, and Gmail integration.

The scraper is a separate exploratory component and is not connected to the main application pipeline. Cloud deployment has not been validated, and the application is intended for local or private-network use rather than direct public exposure.

**Data disclaimer:** The repository uses synthetic sample data. It does not contain real manufacturer, reseller, or marketplace pricing records. LPP percentages are illustrative configuration values.

## Skills Demonstrated

Data engineering · Data quality management · ETL pipelines · Relational database design · Business rule engines · Pricing analytics · Workflow automation · Human-in-the-loop controls · Dashboard development · Auditability · API integration

## Future Enhancements

Potential next steps include automated testing, role-based access control, secure cloud deployment, broader authorized marketplace integrations, and anomaly detection to complement the deterministic compliance rules.
