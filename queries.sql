-- =====================================================================
-- Retention Decision Engine - Stage 1: SQL analysis (PostgreSQL)
-- Dataset : UCI Online Retail II (1 Dec 2009 - 9 Dec 2011)
-- Database: churn
-- Run the sections in order. Each section says what question it answers.
-- =====================================================================


-- ---------------------------------------------------------------------
-- 0. Staging table. Every column is TEXT so the CSV load cannot fail on
--    messy values; types are fixed in step 2.
--    Load the CSV with pgAdmin: right-click raw_retail -> Import/Export
--    Data (format csv, header on, delimiter ",", encoding UTF8).
--    Expected: 1,067,371 rows.
-- ---------------------------------------------------------------------
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


-- ---------------------------------------------------------------------
-- 1. Raw data checks: what is wrong with the data before cleaning?
-- ---------------------------------------------------------------------
SELECT * FROM raw_retail LIMIT 5;                                  -- columns line up?
SELECT COUNT(*) FROM raw_retail WHERE customer_id IS NULL;         -- 243,007
SELECT COUNT(*) FROM raw_retail WHERE quantity::numeric < 0;       -- 22,950
SELECT MIN(invoice_date), MAX(invoice_date) FROM raw_retail;       -- Dec 2009 to Dec 2011


-- ---------------------------------------------------------------------
-- 2. Cleaning: a typed table that only keeps rows tied to a real customer
--    and a real purchase.
--    Result: 805,549 rows, 5,878 customers (261,822 rows removed, ~25%).
-- ---------------------------------------------------------------------
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


-- ---------------------------------------------------------------------
-- 3. Revenue per month: is the business seasonal?
-- ---------------------------------------------------------------------
SELECT DATE_TRUNC('month', invoice_ts)::date AS month,
       ROUND(SUM(revenue), 2)                AS revenue
FROM transactions
GROUP BY 1
ORDER BY 1;


-- ---------------------------------------------------------------------
-- 4. Top 10 customers by revenue: how concentrated is revenue?
-- ---------------------------------------------------------------------
SELECT customer_id,
       COUNT(DISTINCT invoice) AS orders,
       ROUND(SUM(revenue), 2)  AS total_revenue
FROM transactions
GROUP BY customer_id
ORDER BY total_revenue DESC
LIMIT 10;

-- Optional outlier check (customer 16446: only 2 orders but ~$168k)
SELECT * FROM transactions WHERE customer_id = 16446 ORDER BY revenue DESC LIMIT 5;


-- ---------------------------------------------------------------------
-- 5. Cohort retention: of the customers who first bought in month X, what
--    share buy again 1, 2, 3 ... months later?
-- ---------------------------------------------------------------------
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


-- ---------------------------------------------------------------------
-- 6. Customer-level table with churn flags for two definitions
--    (no purchase for more than 90 days / more than 180 days, measured
--    from the last date in the data).
--    Result: 5,878 customers; churned_90 = 2,989; churned_180 = 2,400.
-- ---------------------------------------------------------------------
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


-- ---------------------------------------------------------------------
-- 7. Which churn window is right? Measure how long customers actually go
--    quiet between purchases (LAG window function).
--    Result: 5,254 gaps > 90 days, 1,970 gaps > 180 days, 27,229 gaps total.
-- ---------------------------------------------------------------------
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


-- ---------------------------------------------------------------------
-- 8. RFM segments (recency, frequency, monetary), saved as a view.
--    Descriptive only: uses data up to the end date, so recency cannot be
--    used to predict churn (it is the label).
-- ---------------------------------------------------------------------
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


-- ---------------------------------------------------------------------
-- 9. Indexes and key (schema polish). Provided; run and confirm in pgAdmin.
-- ---------------------------------------------------------------------
CREATE INDEX idx_transactions_customer ON transactions (customer_id);
CREATE INDEX idx_transactions_ts       ON transactions (invoice_ts);
ALTER TABLE customer_status ADD PRIMARY KEY (customer_id);
ANALYZE transactions;
