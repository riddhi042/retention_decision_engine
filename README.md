# Retention Decision Engine (Online Retail II)

Working out which customers are actually worth trying to keep, using real retail transaction data.

**Status: in progress.** The SQL stage is finished (PostgreSQL). Survival analysis, customer value and an uplift model are next. Only finished work is described below.

## The idea

A retention team cannot contact every customer, and contacting some customers is a waste (they would have stayed anyway) or even backfires. A plain "who will churn" model does not answer that. The plan for this project is to answer a more useful question: **who is worth contacting, and is it worth the cost?**

The plan has three layers:

1. **Survival analysis** to estimate when customers are likely to leave, not just whether they will.
2. **Uplift modelling** to estimate who is actually changed by outreach, using a separate randomized experiment.
3. **A decision rule** that contacts a customer only if the expected money saved is more than the cost of contacting them.

The first layer builds on the SQL work done so far.

## Data

- **UCI Online Retail II**: about 1.07 million purchase lines from a UK online gift retailer, December 2009 to December 2011. Not included in this repo; download it from the UCI Machine Learning Repository and check the page for licence and citation details.
- The data has no currency sign. The shop is in the UK, so amounts are probably pounds.
- It contains no campaign or treatment information. The uplift step will use a separate dataset (the Hillstrom email experiment), which is not added yet.

## What is done so far (SQL, PostgreSQL)

- **Loading:** converted the Excel file (two sheets) to one CSV with pandas, then loaded all 1,067,371 rows into a staging table with every column as text.
- **Cleaning:** kept only rows with a customer ID, no cancellations, and positive quantity and price. That left 805,549 rows and 5,878 customers (about a quarter of the raw rows were dropped).
- **Monthly revenue:** roughly 500k to 700k a month through August 2010, then a climb to 1.17M by November 2010. The business is seasonal.
- **Top customers:** revenue is concentrated in a few wholesale-style buyers. The top 10 customers add up to about 2.83M.
- **Cohort retention:** about 35% of a first-month cohort buys again the next month, and retention stays in the mid-30s to low-40s afterwards instead of falling to zero. Customers go quiet and come back later, especially around Christmas.
- **Churn definition:** compared "no purchase for 90 days" (50.9% of customers) with "180 days" (40.8%). A gap analysis using the `LAG` window function showed that 93% of purchase gaps are 180 days or shorter, and about 62% of gaps longer than 90 days ended with the customer coming back. I chose **180 days**.
- **RFM segments:** five segments from recency, frequency and spend scores. Champions are 25% of customers and, by a rough calculation, bring in about 69% of revenue. The "At Risk" group (824 customers) used to buy often and has gone quiet.
- **Schema polish:** indexes on customer and invoice date, and a primary key on the customer table.

The full SQL is in [`queries.sql`](queries.sql). My notes on each step, with results, are in [`docs/retention-sql-notes.md`](docs/retention-sql-notes.md).

## Repository contents

```
queries.sql                  all SQL, in the order it was run
convert_excel_2_csv.py       converts the two-sheet Excel file into one CSV
docs/retention-sql-notes.md  notes and results for each SQL step
```

## How to reproduce the SQL stage

1. Download Online Retail II from UCI and convert it to one CSV (edit the two paths at the top of `convert_excel_2_csv.py`, then run it; it needs `pandas` and `openpyxl`).
2. In PostgreSQL, create a database called `churn`.
3. Create the `raw_retail` table (the first block in `queries.sql`) and import the CSV, for example with pgAdmin's Import/Export dialog (CSV, header on, UTF8).
4. Run the rest of `queries.sql` in order. Each section says what it answers.

## Limitations and assumptions

- Churn is defined as no purchase for more than 180 days, counted from the last date in the data (9 December 2011). That is a judgement call. The gap analysis supports it but cannot prove it, because it only sees customers who came back.
- The first cohort (December 2009) includes customers who were already buying before the data starts, so it overstates truly new customers.
- This is one UK gift retailer with many wholesale buyers. Results may not carry over to other kinds of business.
- RFM cut-offs are my own choices. RFM computed at the end date describes customers but cannot be used to predict churn, because recency would give the answer away.
- The retention and revenue figures are descriptive. No predictive model has been built yet.

## Roadmap

- [x] Load and clean the data in PostgreSQL
- [x] Cohort retention, churn definition, RFM segments
- [x] Connect Python to PostgreSQL
- [x] Survival analysis (Kaplan-Meier curves, Cox model) on the 180-day churn labels
- [x] Customer lifetime value
- [ ] Features built only from data before a cutoff date, for any predictive modelling
- [x] Uplift model on the Hillstrom email experiment
- [x] Contact-or-not decision rule, with validation
- [ ] Final write-up of results

## Tools

PostgreSQL and pgAdmin, SQL (CTEs, window functions, views), Python (pandas) for data conversion. Survival analysis and modelling will use Python.
