"""Uplift model on the Hillstrom email experiment.

Customers were randomly assigned to a Men's email, a Women's email, or no email.
Because assignment was random, the difference in outcomes between emailed and
not-emailed customers is a fair estimate of what the email caused.

Method: T-learner with cross-fitting. One model predicts the chance of buying if
emailed, one predicts it if not emailed; uplift = difference in probability.
Each customer is scored by models that never saw them. Spend itself is too
sparse (about 1% of customers buy) to model directly.
"""
import os

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import KFold

DATA_PATH = "data/hillstrom.csv.gz"
OUT_PATH = "data/uplift_predictions.csv"
OUTCOME = "visit" # 1 = bought within two weeks. Try "visit" for a denser (less noisy) outcome
NUMERIC = ["recency", "history", "mens", "womens", "newbie"]
CATEGORICAL = ["zip_code", "channel"]


def load_data(path=DATA_PATH):
    return pd.read_csv(path)


def prepare(df):
    df = df.copy()
    df["treated"] = (df["segment"] != "No E-Mail").astype(int)  # either email vs none
    X = pd.get_dummies(df[NUMERIC + CATEGORICAL], columns=CATEGORICAL).astype(float)
    return df, X


def average_effect(df):
    print(f"Average spend  emailed: {df.loc[df['treated'] == 1, 'spend'].mean():.3f}   not emailed: {df.loc[df['treated'] == 0, 'spend'].mean():.3f}")
    t = df.loc[df["treated"] == 1, OUTCOME]
    c = df.loc[df["treated"] == 0, OUTCOME]
    diff = t.mean() - c.mean()
    se = np.sqrt(t.var(ddof=1) / len(t) + c.var(ddof=1) / len(c))
    p = stats.ttest_ind(t, c, equal_var=False).pvalue
    print(f"Average {OUTCOME} rate  emailed: {t.mean():.4f}   not emailed: {c.mean():.4f}")
    print(f"Average effect of an email on {OUTCOME}: {diff:+.4f} (95% CI {diff - 1.96 * se:+.4f} to {diff + 1.96 * se:+.4f}, p = {p:.4f})")
    return diff


def crossfit_uplift(X, treated, y, n_splits=5, seed=42):
    uplift = np.zeros(len(X))
    params = dict(n_estimators=150, max_depth=3, learning_rate=0.05,
                  min_samples_leaf=200, subsample=0.8, random_state=0)
    for tr, te in KFold(n_splits, shuffle=True, random_state=seed).split(X):
        Xtr, ttr, ytr = X.iloc[tr], treated[tr], y[tr]
        m1 = GradientBoostingClassifier(**params).fit(Xtr[ttr == 1], ytr[ttr == 1])
        m0 = GradientBoostingClassifier(**params).fit(Xtr[ttr == 0], ytr[ttr == 0])
        uplift[te] = m1.predict_proba(X.iloc[te])[:, 1] - m0.predict_proba(X.iloc[te])[:, 1]
    return uplift


def targeting_table(df, uplift):
    """If we email only the top share of customers ranked by predicted uplift,
    what did emailing actually add in that group? (valid because
    the email was assigned at random)."""
    d = df.assign(uplift=uplift).sort_values("uplift", ascending=False).reset_index(drop=True)
    rows = []
    for share in [0.1, 0.2, 0.3, 0.5, 0.7, 1.0]:
        top = d.iloc[: int(len(d) * share)]
        t = top.loc[top["treated"] == 1, OUTCOME]
        c = top.loc[top["treated"] == 0, OUTCOME]
        rows.append({"emailed share": f"{share:.0%}", "customers": len(top),
                     "actual extra " + OUTCOME + " rate": round(t.mean() - c.mean(), 4)})
    return pd.DataFrame(rows)


def decile_table(df, uplift):
    d = df.assign(uplift=uplift)
    d["decile"] = pd.qcut(d["uplift"].rank(method="first", ascending=False), 10, labels=range(1, 11))
    rows = []
    for dec, g in d.groupby("decile", observed=True):
        t = g.loc[g["treated"] == 1, OUTCOME]
        c = g.loc[g["treated"] == 0, OUTCOME]
        rows.append({"decile (1 = highest predicted uplift)": dec,
                     "predicted uplift": round(g["uplift"].mean(), 4),
                     "actual uplift": round(t.mean() - c.mean(), 4)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    raw = load_data()
    df, X = prepare(raw)
    print(f"Customers: {len(df)}   emailed: {df['treated'].mean():.1%}   bought: {(df['spend'] > 0).mean():.2%}")
    average_effect(df)
    uplift = crossfit_uplift(X, df["treated"].to_numpy(), df[OUTCOME].to_numpy())
    print("\nActual uplift by predicted-uplift decile:")
    print(decile_table(df, uplift).to_string(index=False))
    print("\nEmail only the top share of customers:")
    print(targeting_table(df, uplift).to_string(index=False))
    os.makedirs("data", exist_ok=True)
    out = df[["segment", "treated", "spend", "conversion", "visit"]].copy()
    out["predicted_uplift"] = uplift
    out.to_csv(OUT_PATH, index=False)
    print("\nSaved", OUT_PATH)
