"""Builds the small summary files the dashboard reads (dashboard/summary/).

Run it from the project folder, after the SQL tables, clv_model.py and
uplift_model.py have been run:  python export_dashboard_data.py

Only aggregated numbers are written (curves, deciles, counts), so the repo does
not need the raw transactions.
"""
import json
import os

import numpy as np
import pandas as pd
from lifelines import CoxPHFitter, KaplanMeierFitter
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

import decision_rule as dr
from survival_analysis import add_duration_and_event

OUT_DIR = "dashboard/summary"

SQL = {
    "monthly": """
        SELECT DATE_TRUNC('month', invoice_ts)::date AS month,
               ROUND(SUM(revenue), 2)                AS revenue,
               COUNT(DISTINCT customer_id)           AS customers
        FROM transactions GROUP BY 1 ORDER BY 1""",
    "cohort": """
        WITH first_purchase AS (
            SELECT customer_id, DATE_TRUNC('month', MIN(invoice_ts)) AS cohort_month
            FROM transactions GROUP BY customer_id),
        activity AS (
            SELECT DISTINCT customer_id, DATE_TRUNC('month', invoice_ts) AS active_month
            FROM transactions),
        cohort_activity AS (
            SELECT f.cohort_month, a.customer_id,
                   (EXTRACT(YEAR FROM a.active_month) - EXTRACT(YEAR FROM f.cohort_month)) * 12
                 + (EXTRACT(MONTH FROM a.active_month) - EXTRACT(MONTH FROM f.cohort_month)) AS month_number
            FROM first_purchase f JOIN activity a USING (customer_id)),
        cohort_size AS (
            SELECT cohort_month, COUNT(*) AS cohort_customers FROM first_purchase GROUP BY cohort_month)
        SELECT c.cohort_month::date AS cohort_month, c.month_number::int AS month_number,
               COUNT(DISTINCT c.customer_id) AS active_customers, s.cohort_customers,
               ROUND(100.0 * COUNT(DISTINCT c.customer_id) / s.cohort_customers, 1) AS retention_pct
        FROM cohort_activity c JOIN cohort_size s USING (cohort_month)
        GROUP BY c.cohort_month, c.month_number, s.cohort_customers
        ORDER BY c.cohort_month, c.month_number""",
    "segments": """
        SELECT segment, COUNT(*) AS customers,
               ROUND(AVG(total_revenue), 0) AS avg_revenue,
               ROUND(SUM(total_revenue), 0) AS revenue
        FROM v_rfm GROUP BY segment ORDER BY avg_revenue DESC""",
    "deciles": """
        WITH ranked AS (
            SELECT total_revenue, NTILE(10) OVER (ORDER BY total_revenue DESC) AS decile
            FROM customer_status)
        SELECT decile, COUNT(*) AS customers, ROUND(AVG(total_revenue), 0) AS avg_revenue,
               ROUND(100.0 * SUM(total_revenue) / SUM(SUM(total_revenue)) OVER (), 1) AS pct_of_revenue
        FROM ranked GROUP BY decile ORDER BY decile""",
    "survival_input": """
        SELECT s.customer_id, s.first_purchase, s.last_purchase, s.churned_180,
               e.country, e.first_order_value
        FROM customer_status s JOIN customer_early e USING (customer_id)""",
}


def fetch_tables():
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    url = URL.create("postgresql+psycopg2", username="postgres",
                     password=os.environ["PGPASSWORD"], host="localhost",
                     port=5432, database="churn")
    engine = create_engine(url)
    return {name: pd.read_sql(sql, engine) for name, sql in SQL.items()}


def survival_outputs(raw):
    df = add_duration_and_event(raw)
    df["country_group"] = np.where(df["country"] == "United Kingdom", "United Kingdom", "Other countries")
    med = df["first_order_value"].median()
    df["order_group"] = np.where(df["first_order_value"] >= med, "First order above median", "First order below median")

    rows = []
    def add(split, label, g):
        kmf = KaplanMeierFitter().fit(g["duration"], g["event"])
        sf = kmf.survival_function_.iloc[:, 0]
        ci = kmf.confidence_interval_
        grid = np.arange(0, int(g["duration"].max()) + 1, 5)
        for t in grid:
            i = sf.index.searchsorted(t, side="right") - 1
            i = max(i, 0)
            rows.append({"split": split, "group": label, "day": int(t), "survival": float(sf.iloc[i]),
                         "lower": float(ci.iloc[i, 0]), "upper": float(ci.iloc[i, 1]), "customers": len(g)})
    add("All customers", "All customers", df)
    for col, split in [("order_group", "First order size"), ("country_group", "Country")]:
        for label, g in df.groupby(col):
            add(split, label, g)
    km = pd.DataFrame(rows)

    model_df = pd.DataFrame({
        "duration": df["duration"], "event": df["event"],
        "is_uk": (df["country"] == "United Kingdom").astype(int),
        "log_first_order_value": np.log1p(df["first_order_value"].clip(lower=0))})
    cph = CoxPHFitter().fit(model_df, "duration", "event")
    s = cph.summary
    cox = pd.DataFrame({"covariate": s.index, "hazard_ratio": s["exp(coef)"].values,
                        "lower": s["exp(coef) lower 95%"].values, "upper": s["exp(coef) upper 95%"].values,
                        "p": s["p"].values})
    allkm = KaplanMeierFitter().fit(df["duration"], df["event"])
    at = {f"survival_{d}": float(allkm.predict(d)) for d in (90, 180, 365, 540)}
    return km, cox, at, {"customers": int(len(df)), "churned": int(df["event"].sum()),
                         "concordance": float(cph.concordance_index_)}


def clv_outputs(clv):
    auc = roc_auc_score(clv["active"], clv["p_active"])
    rho_model = spearmanr(clv["clv_180d"], clv["future_revenue"])[0]
    rho_hist = spearmanr(clv["revenue"], clv["future_revenue"])[0]
    total = clv["future_revenue"].sum()
    k = int(len(clv) * 0.10)
    metrics = {"clv_auc": float(auc), "clv_rho_model": float(rho_model), "clv_rho_hist": float(rho_hist),
               "clv_top10_model": float(clv.nlargest(k, "clv_180d")["future_revenue"].sum() / total),
               "clv_top10_hist": float(clv.nlargest(k, "revenue")["future_revenue"].sum() / total),
               "clv_customers": int(len(clv)), "clv_avg_predicted": float(clv["clv_180d"].mean()),
               "clv_avg_actual": float(clv["future_revenue"].mean())}
    d = clv.copy()
    d["decile"] = pd.qcut(d["clv_180d"].rank(method="first", ascending=False), 10, labels=range(1, 11)).astype(int)
    cal = d.groupby("decile").agg(customers=("customer_id", "size"), predicted=("clv_180d", "mean"),
                                  actual=("future_revenue", "mean")).reset_index().round(1)
    return cal, metrics


def uplift_outputs(up, n_boot=100):
    treated = up["treated"].to_numpy()
    spend = up["spend"].to_numpy(dtype=float)
    visit = up["visit"].to_numpy(dtype=float)
    pred = up["predicted_uplift"].to_numpy(dtype=float)

    d = up.copy()
    d["decile"] = pd.qcut(d["predicted_uplift"].rank(method="first", ascending=False), 10, labels=range(1, 11)).astype(int)
    rows = []
    for dec, g in d.groupby("decile"):
        t, c = g.loc[g["treated"] == 1, "visit"], g.loc[g["treated"] == 0, "visit"]
        diff = t.mean() - c.mean()
        se = np.sqrt(t.var(ddof=1) / len(t) + c.var(ddof=1) / len(c))
        rows.append({"decile": int(dec), "customers": len(g), "predicted": g["predicted_uplift"].mean(),
                     "actual": diff, "lower": diff - 1.96 * se, "upper": diff + 1.96 * se})
    deciles = pd.DataFrame(rows)

    t, c = visit[treated == 1], visit[treated == 0]
    ate = t.mean() - c.mean()
    se = np.sqrt(t.var(ddof=1) / len(t) + c.var(ddof=1) / len(c))
    v = dr.revenue_per_extra_visit(treated, spend, visit)
    summary = {"uplift_customers": int(len(up)), "visit_emailed": float(t.mean()), "visit_control": float(c.mean()),
               "visit_effect": float(ate), "visit_effect_lower": float(ate - 1.96 * se),
               "visit_effect_upper": float(ate + 1.96 * se),
               "spend_emailed": float(spend[treated == 1].mean()), "spend_control": float(spend[treated == 0].mean()),
               "revenue_per_extra_visit": float(v)}

    rng = np.random.default_rng(0)
    boots = [rng.integers(0, len(up), len(up)) for _ in range(n_boot)]
    rows = []
    for cost in np.round(np.arange(0.05, 3.0001, 0.05), 2):
        base = dr.run_policies(treated, spend, visit, pred, cost)
        diffs = []
        for idx in boots:
            r = dr.run_policies(treated[idx], spend[idx], visit[idx], pred[idx], cost)
            diffs.append(r["rule"] - r["all"])
        lo, hi = np.percentile(diffs, [2.5, 97.5])
        rows.append({"cost": cost, "share_contacted": base["share"], "net_all": base["all"] * 1000,
                     "net_rule": base["rule"] * 1000, "diff": (base["rule"] - base["all"]) * 1000,
                     "diff_lower": lo * 1000, "diff_upper": hi * 1000})
    return deciles, pd.DataFrame(rows), summary


def build_outputs(tables, clv, up, out_dir=OUT_DIR, n_boot=100):
    os.makedirs(out_dir, exist_ok=True)
    for name in ["monthly", "cohort", "segments", "deciles"]:
        tables[name].to_csv(f"{out_dir}/{name}.csv", index=False)
    km, cox, at, surv_meta = survival_outputs(tables["survival_input"])
    km.to_csv(f"{out_dir}/km_curves.csv", index=False)
    cox.to_csv(f"{out_dir}/cox.csv", index=False)
    cal, clv_metrics = clv_outputs(clv)
    cal.to_csv(f"{out_dir}/clv_calibration.csv", index=False)
    deciles, curve, up_summary = uplift_outputs(up, n_boot=n_boot)
    deciles.to_csv(f"{out_dir}/uplift_deciles.csv", index=False)
    curve.to_csv(f"{out_dir}/decision_curve.csv", index=False)
    top = tables["deciles"].iloc[0]
    summary = {**at, **surv_meta, **clv_metrics, **up_summary,
               "churn_rate": surv_meta["churned"] / surv_meta["customers"],
               "top_decile_revenue_share": float(top["pct_of_revenue"]) / 100}
    with open(f"{out_dir}/summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("Wrote files to", out_dir)


if __name__ == "__main__":
    build_outputs(fetch_tables(), pd.read_csv("data/clv_predictions.csv"), pd.read_csv("data/uplift_predictions.csv"))
