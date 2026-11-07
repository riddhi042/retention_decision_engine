"""Customer lifetime value (180-day) model.

Reads customer_cutoff (features known on 9 June 2011, plus what each customer
did in the following 180 days). Expected value = P(buys again) x expected spend
if they do. Every customer gets an out-of-fold prediction, so no customer is
scored by a model that saw their own outcome.
"""
import os

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import KFold

FEATURES = ["recency_days", "tenure_days", "orders", "revenue",
            "avg_order_value", "order_rate"]
OUT_PATH = "data/clv_predictions.csv"


def load_data():
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    url = URL.create("postgresql+psycopg2", username="postgres",
                     password=os.environ["PGPASSWORD"], host="localhost",
                     port=5432, database="churn")
    return pd.read_sql("SELECT * FROM customer_cutoff", create_engine(url))


def add_features(df):
    df = df.copy()
    for c in ["revenue", "future_revenue"]:
        df[c] = df[c].astype(float)
    df["avg_order_value"] = df["revenue"] / df["orders"]
    df["order_rate"] = df["orders"] / (df["tenure_days"] + 1) * 365  # orders per year so far
    df["active"] = 1 - df["churned_future"]
    return df


def out_of_fold_clv(df, n_splits=5, seed=42):
    p_active = np.zeros(len(df))
    spend = np.zeros(len(df))
    for tr, te in KFold(n_splits, shuffle=True, random_state=seed).split(df):
        train, test = df.iloc[tr], df.iloc[te]

        clf = GradientBoostingClassifier(random_state=0)
        clf.fit(train[FEATURES], train["active"])
        p_active[te] = clf.predict_proba(test[FEATURES])[:, 1]

        buyers = train[train["active"] == 1]
        y = np.log1p(buyers["future_revenue"])
        reg = GradientBoostingRegressor(random_state=0).fit(buyers[FEATURES], y)
        smear = np.mean(np.exp(y - reg.predict(buyers[FEATURES])))  # corrects the bias from modelling log spend
        spend[te] = np.exp(reg.predict(test[FEATURES])) * smear

    out = df[["customer_id"]].copy()
    out["p_active"] = p_active
    out["expected_spend"] = spend
    out["clv_180d"] = p_active * spend
    return out


def evaluate(df, pred):
    d = df.merge(pred, on="customer_id")
    auc = roc_auc_score(d["active"], d["p_active"])
    rho_model = spearmanr(d["clv_180d"], d["future_revenue"])[0]
    rho_hist = spearmanr(d["revenue"], d["future_revenue"])[0]

    total = d["future_revenue"].sum()
    k = int(len(d) * 0.10)
    top_model = d.nlargest(k, "clv_180d")["future_revenue"].sum() / total
    top_hist = d.nlargest(k, "revenue")["future_revenue"].sum() / total

    print(f"Customers: {len(d)}   bought again within 180 days: {d['active'].mean():.1%}")
    print(f"AUC for 'buys again' (0.5 = coin flip): {auc:.3f}")
    print(f"Rank correlation with real future revenue:  model {rho_model:.3f}   past revenue only {rho_hist:.3f}")
    print(f"Share of real future revenue in top 10%:   model {top_model:.1%}   past revenue only {top_hist:.1%}")
    print(f"Average predicted {d['clv_180d'].mean():.0f}  vs  average actual {d['future_revenue'].mean():.0f}")
    return d


if __name__ == "__main__":
    data = add_features(load_data())
    preds = out_of_fold_clv(data)
    result = evaluate(data, preds)
    os.makedirs("data", exist_ok=True)
    result.to_csv(OUT_PATH, index=False)
    print("Saved", OUT_PATH)
