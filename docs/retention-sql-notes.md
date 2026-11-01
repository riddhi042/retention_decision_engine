# Retention project: SQL notes

UCI Online Retail II, PostgreSQL. Notes from the SQL part, November 2026.

These are my notes on the SQL part of a customer retention project. The data is the UCI Online Retail II dataset: about 1.07 million purchase lines from a UK online gift retailer, December 2009 to December 2011. The goal of the whole project is to work out which customers are worth trying to keep, but first I needed to clean the data and see how customers actually behave. The full SQL is in `queries.sql`. Amounts have no currency sign because the data does not say; the shop is in the UK, so it is probably pounds.

## 1. Loading the data

The data came as an Excel file with two sheets, one per year. I joined the sheets into one CSV with a short pandas script and loaded it into a table called `raw_retail`. I made every column text on purpose, so the import could not fail on a bad value, and fixed the types afterwards. The table ended up with 1,067,371 rows, which matches what the script wrote out.

```sql
CREATE TABLE raw_retail (
    invoice       TEXT,
    stock_code    TEXT,
    description   TEXT,
    quantity      TEXT,
    invoice_date  TEXT,
    price         TEXT,
    customer_id   TEXT,
    country       TEXT
);

SELECT COUNT(*) FROM raw_retail;
```

## 2. Checking what is wrong with it

Before cleaning anything I wanted to know how bad it was. A sample of five rows showed the columns lined up. Then I counted the problems.

```sql
SELECT * FROM raw_retail LIMIT 5;                                  -- columns line up?
SELECT COUNT(*) FROM raw_retail WHERE customer_id IS NULL;         -- 243,007
SELECT COUNT(*) FROM raw_retail WHERE quantity::numeric < 0;       -- 22,950
SELECT MIN(invoice_date), MAX(invoice_date) FROM raw_retail;       -- Dec 2009 to Dec 2011
```

| Check | Result |
|---|---:|
| Rows with no customer ID | 243,007 (about 23%) |
| Rows with negative quantity | 22,950 (about 2%) |
| First invoice | 2009-12-01 |
| Last invoice | 2011-12-09 |

Rows without a customer ID are no use for studying customers over time, so they have to go. The negative quantities are mostly returns.

## 3. Cleaning

I made a new table, `transactions`, with proper types and a `revenue` column (quantity times price). I kept rows that have a customer ID, are not cancellations (invoice numbers starting with C), and have a positive quantity and price. That left 805,549 rows and 5,878 customers, so 261,822 rows (roughly a quarter) were dropped.

```sql
CREATE TABLE transactions AS
SELECT
    invoice,
    stock_code,
    quantity::numeric::int             AS quantity,
    invoice_date::timestamp            AS invoice_ts,
    price::numeric                     AS price,
    customer_id::numeric::int          AS customer_id,
    country,
    quantity::numeric * price::numeric AS revenue
FROM raw_retail
WHERE customer_id IS NOT NULL          -- cannot track customers with no ID
  AND invoice NOT LIKE 'C%'            -- 'C' invoices are cancellations / returns
  AND quantity::numeric > 0
  AND price::numeric > 0;

SELECT COUNT(*), COUNT(DISTINCT customer_id), MIN(invoice_ts), MAX(invoice_ts)
FROM transactions;
```

## 4. Revenue by month

First question: is the business seasonal?

```sql
SELECT DATE_TRUNC('month', invoice_ts)::date AS month,
       ROUND(SUM(revenue), 2)                AS revenue
FROM transactions
GROUP BY 1
ORDER BY 1;
```

| Month | Revenue |
|---|---:|
| 2009-12 | 686,654.16 |
| 2010-01 | 557,319.06 |
| 2010-02 | 506,371.07 |
| 2010-03 | 699,608.99 |
| 2010-04 | 594,609.19 |
| 2010-05 | 599,985.79 |
| 2010-06 | 639,066.58 |
| 2010-07 | 591,636.74 |
| 2010-08 | 604,242.65 |
| 2010-09 | 831,615.00 |
| 2010-10 | 1,036,680.00 |
| 2010-11 | 1,172,336.04 |

Revenue sits at roughly 500k to 700k a month from December 2009 through August 2010. Then it climbs: 832k in September, 1.04M in October and 1.17M in November 2010. It looks like a Christmas buying season, so yes, this business is seasonal. I have only looked at the first 12 of the 25 months so far.

## 5. Biggest customers

Which customers matter most?

```sql
SELECT customer_id,
       COUNT(DISTINCT invoice) AS orders,
       ROUND(SUM(revenue), 2)  AS total_revenue
FROM transactions
GROUP BY customer_id
ORDER BY total_revenue DESC
LIMIT 10;

-- Optional outlier check (customer 16446: only 2 orders but ~$168k)
SELECT * FROM transactions WHERE customer_id = 16446 ORDER BY revenue DESC LIMIT 5;
```

| Customer | Orders | Total revenue |
|---|---:|---:|
| 18102 | 145 | 608,821.65 |
| 14646 | 151 | 528,602.52 |
| 14156 | 156 | 313,946.37 |
| 14911 | 398 | 295,972.63 |
| 17450 | 51 | 246,973.09 |
| 13694 | 143 | 196,482.81 |
| 17511 | 60 | 175,603.55 |
| 16446 | 2 | 168,472.50 |
| 16684 | 55 | 147,142.77 |
| 12415 | 28 | 144,458.37 |

Revenue is concentrated: the top 10 customers add up to about 2.83M. Customer 18102 is the biggest, about 609k over 145 orders. Customer 16446 is odd, with only 2 orders but about 168k, so those must be very large orders. I have not looked into that one properly yet. Many of the top customers place 50 to 400 orders, which looks like businesses buying wholesale, not individual shoppers.

## 6. Cohort retention

I grouped customers by the month of their first purchase and checked what share came back in each later month. The table below is just the December 2009 cohort (955 customers).

```sql
WITH first_purchase AS (
    SELECT customer_id,
           DATE_TRUNC('month', MIN(invoice_ts)) AS cohort_month
    FROM transactions
    GROUP BY customer_id
),
activity AS (
    SELECT DISTINCT customer_id,
           DATE_TRUNC('month', invoice_ts) AS active_month
    FROM transactions
),
cohort_activity AS (
    SELECT f.cohort_month,
           a.customer_id,
           (EXTRACT(YEAR  FROM a.active_month) - EXTRACT(YEAR  FROM f.cohort_month)) * 12
         + (EXTRACT(MONTH FROM a.active_month) - EXTRACT(MONTH FROM f.cohort_month))
           AS month_number
    FROM first_purchase f
    JOIN activity a USING (customer_id)
),
cohort_size AS (
    SELECT cohort_month, COUNT(*) AS cohort_customers
    FROM first_purchase
    GROUP BY cohort_month
)
SELECT c.cohort_month::date,
       c.month_number::int,
       COUNT(DISTINCT c.customer_id) AS active_customers,
       s.cohort_customers,
       ROUND(100.0 * COUNT(DISTINCT c.customer_id) / s.cohort_customers, 1)
           AS retention_pct
FROM cohort_activity c
JOIN cohort_size s USING (cohort_month)
GROUP BY c.cohort_month, c.month_number, s.cohort_customers
ORDER BY c.cohort_month, c.month_number;
```

| Months after first purchase | Active customers | Retention % |
|---:|---:|---:|
| 0 | 955 | 100.0 |
| 1 | 337 | 35.3 |
| 2 | 319 | 33.4 |
| 3 | 406 | 42.5 |
| 4 | 363 | 38.0 |
| 5 | 343 | 35.9 |
| 6 | 360 | 37.7 |
| 7 | 327 | 34.2 |
| 8 | 321 | 33.6 |
| 9 | 346 | 36.2 |
| 10 | 403 | 42.2 |
| 11 | 473 | 49.5 |

The query returns 325 rows, which is 25 cohorts. Month 0 is 100 percent for every cohort, which is a good sign the query is right. In this cohort about 35 percent buy again the next month, and it then stays between 33 and 43 percent through month 10. At month 11 (November 2010) it rises to 49.5 percent, the Christmas effect again. The main thing I take from it is that retention does not fall towards zero: customers go quiet and come back later. One caveat is that the data starts in December 2009, so this first cohort includes people who were already customers before then.

## 7. Defining churn

A customer only has a last purchase date, so churn has to be defined by a gap. I tried two rules, no purchase for more than 90 days and for more than 180 days, counted from the last date in the data.

```sql
CREATE TABLE customer_status AS
WITH bounds AS (
    SELECT MAX(invoice_ts) AS obs_end FROM transactions
),
cust AS (
    SELECT customer_id,
           MIN(invoice_ts)         AS first_purchase,
           MAX(invoice_ts)         AS last_purchase,
           COUNT(DISTINCT invoice) AS orders,
           SUM(revenue)            AS total_revenue
    FROM transactions
    GROUP BY customer_id
)
SELECT c.*,
       (b.obs_end::date - c.last_purchase::date) AS days_since_last,
       CASE WHEN b.obs_end - c.last_purchase > INTERVAL '90 days'  THEN 1 ELSE 0 END
           AS churned_90,
       CASE WHEN b.obs_end - c.last_purchase > INTERVAL '180 days' THEN 1 ELSE 0 END
           AS churned_180
FROM cust c CROSS JOIN bounds b;

SELECT COUNT(*) AS customers,
       SUM(churned_90)  AS churned_90,
       SUM(churned_180) AS churned_180
FROM customer_status;
```

| Rule | Churned customers | Share of 5,878 |
|---|---:|---:|
| More than 90 days | 2,989 | 50.9% |
| More than 180 days | 2,400 | 40.8% |

The two rules disagree on 589 customers (10 percentage points). Given the seasonality above, I suspected many of those are seasonal buyers who just come back later, so I wanted to check with data before choosing.

## 8. Choosing between 90 and 180 days

I looked at the gaps between each customer's purchases, using `LAG` to compare each purchase date with the one before it.

```sql
WITH days AS (
    SELECT DISTINCT customer_id, invoice_ts::date AS d
    FROM transactions
),
gaps AS (
    SELECT customer_id,
           d - LAG(d) OVER (PARTITION BY customer_id ORDER BY d) AS gap_days
    FROM days
)
SELECT COUNT(*) FILTER (WHERE gap_days > 90)  AS gaps_over_90,
       COUNT(*) FILTER (WHERE gap_days > 180) AS gaps_over_180,
       COUNT(gap_days)                        AS total_gaps
FROM gaps;
```

| Measure | Count |
|---|---:|
| All gaps between purchases | 27,229 |
| Gaps over 90 days | 5,254 (19%) |
| Gaps over 180 days | 1,970 (7%) |
| Gaps between 90 and 180 days | 3,284 |

About 93 percent of all gaps are 180 days or shorter. Of the gaps longer than 90 days, 3,284 (about 62 percent) ended before day 180 with the customer coming back, so a 90-day rule would call a lot of returning customers churned. I am going with 180 days. The limit of this check is that it only sees customers who did come back, so it supports 180 days but does not prove it.

## 9. RFM segments

RFM scores each customer on how recently they bought, how often, and how much they spent. I split each into five groups with `NTILE` and turned the scores into five named segments, saved as a view.

```sql
CREATE VIEW v_rfm AS
WITH scored AS (
    SELECT customer_id, days_since_last, orders, total_revenue,
           NTILE(5) OVER (ORDER BY days_since_last DESC) AS r_score,
           NTILE(5) OVER (ORDER BY orders)               AS f_score,
           NTILE(5) OVER (ORDER BY total_revenue)        AS m_score
    FROM customer_status
)
SELECT *,
       CASE
           WHEN r_score >= 4 AND f_score >= 4 THEN 'Champions'
           WHEN r_score >= 3 AND f_score >= 3 THEN 'Loyal'
           WHEN r_score <= 2 AND f_score >= 3 THEN 'At Risk'
           WHEN r_score <= 2 AND f_score <= 2 THEN 'Hibernating'
           ELSE 'Developing'
       END AS segment
FROM scored;

SELECT segment, COUNT(*) AS customers, ROUND(AVG(total_revenue), 0) AS avg_revenue
FROM v_rfm
GROUP BY segment
ORDER BY avg_revenue DESC;
```

| Segment | Customers | Share | Average revenue |
|---|---:|---:|---:|
| Champions | 1,472 | 25.0% | 8,332 |
| Loyal | 1,230 | 20.9% | 2,094 |
| At Risk | 824 | 14.0% | 1,983 |
| Developing | 824 | 14.0% | 727 |
| Hibernating | 1,528 | 26.0% | 438 |

Champions are 25 percent of customers and average about 8,332 each; by my rough math, using the rounded averages, they bring in around 69 percent of revenue. The At Risk group (824 customers, about 1,983 each) used to buy often and has gone quiet, which makes them the obvious group to try to win back. Hibernating is the biggest segment (26 percent) but worth the least, about 438 each. The cut-offs are my own choices, so a different rule would shift the numbers. This view also uses data up to the end date, so recency in it cannot be used to predict churn later, because it would give away the answer.

## 10. Indexes

I added indexes on customer and on invoice date, and a primary key on `customer_status`. I checked in `pg_indexes` that all three exist.

```sql
CREATE INDEX idx_transactions_customer ON transactions (customer_id);
CREATE INDEX idx_transactions_ts       ON transactions (invoice_ts);
ALTER TABLE customer_status ADD PRIMARY KEY (customer_id);
ANALYZE transactions;
```

## Things I am not sure about

- Churn is defined as no purchase for more than 180 days, counted from 9 December 2011. That is a judgement call.
- The first cohort (December 2009) is mixed with customers who started earlier.
- It is one UK gift shop with a lot of wholesale buyers, so the results may not carry over to other businesses.
- The RFM groups depend on cut-offs I chose.
- This data has nothing about any campaign, so the who-to-contact part will use a separate dataset (the Hillstrom email experiment).

## Next

Connect Python to the database, fit a survival model on the 180-day churn labels, then work out customer value.
