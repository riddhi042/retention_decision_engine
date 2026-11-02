"""Survival analysis of customer churn (Online Retail II).

Reads customer_status and customer_early from PostgreSQL, builds a duration and
event for each customer, then fits Kaplan-Meier curves and a Cox model.
"""
import os

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")  # save figures to files instead of opening windows
import matplotlib.pyplot as plt
from lifelines import KaplanMeierFitter, CoxPHFitter

FIG_DIR = "docs/figures"


def load_data():
    from sqlalchemy import create_engine
    from sqlalchemy.engine import URL

    url = URL.create("postgresql+psycopg2", username="postgres",
                     password=os.environ["PGPASSWORD"], host="localhost",
                     port=5432, database="churn")
    engine = create_engine(url)
    query = """
        SELECT s.customer_id, s.first_purchase, s.last_purchase, s.churned_180,
               e.country, e.first_order_value
        FROM customer_status s
        JOIN customer_early e USING (customer_id)
    """
    return pd.read_sql(query, engine)


def add_duration_and_event(df):
    """event = 1 if the customer churned (no purchase for 180+ days before the end of the data).
    duration = days from first purchase to last purchase for churned customers,
    or to the end of the data for customers who are still active (censored)."""
    df = df.copy()
    df["first_purchase"] = pd.to_datetime(df["first_purchase"])
    df["last_purchase"] = pd.to_datetime(df["last_purchase"])
    obs_end = df["last_purchase"].max()

    active_span = (df["last_purchase"] - df["first_purchase"]).dt.days + 1  # +1 so one-time buyers are > 0
    observed_span = (obs_end - df["first_purchase"]).dt.days + 1
    df["event"] = df["churned_180"].astype(int)
    df["duration"] = np.where(df["event"] == 1, active_span, observed_span)
    return df


def analyse(df):
    os.makedirs(FIG_DIR, exist_ok=True)
    print(f"Customers: {len(df)}  churned: {df['event'].sum()}  censored: {(df['event'] == 0).sum()}")

    # 1. Overall Kaplan-Meier curve
    kmf = KaplanMeierFitter()
    kmf.fit(df["duration"], event_observed=df["event"], label="All customers")
    print("Median survival (days):", kmf.median_survival_time_)
    print(kmf.predict([90, 180, 365, 540]))
    ax = kmf.plot_survival_function()
    ax.set_xlabel("Days since first purchase")
    ax.set_ylabel("Share of customers still active")
    ax.set_title("How long customers stay active")
    plt.savefig(f"{FIG_DIR}/km_overall.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 2. Compare groups known at the start (not leaky): UK vs other, small vs large first order
    df = df.copy()
    df["group_country"] = np.where(df["country"] == "United Kingdom", "United Kingdom", "Other countries")
    median_value = df["first_order_value"].median()
    df["group_first_order"] = np.where(df["first_order_value"] >= median_value,
                                       "First order above median", "First order below median")
    for col, name in [("group_country", "km_by_country"), ("group_first_order", "km_by_first_order")]:
        fig, ax = plt.subplots()
        for label, g in df.groupby(col):
            KaplanMeierFitter().fit(g["duration"], event_observed=g["event"], label=f"{label} (n={len(g)})") \
                .plot_survival_function(ax=ax)
        ax.set_xlabel("Days since first purchase")
        ax.set_ylabel("Share of customers still active")
        ax.set_title(col.replace("group_", "By ").replace("_", " "))
        fig.savefig(f"{FIG_DIR}/{name}.png", dpi=150, bbox_inches="tight")
        plt.close(fig)

    # 3. Cox model: how do customer features change the risk of churning?
    model_df = pd.DataFrame({
        "duration": df["duration"],
        "event": df["event"],
        "is_uk": (df["country"] == "United Kingdom").astype(int),
        "log_first_order_value": np.log1p(df["first_order_value"].clip(lower=0)),
    })
    cph = CoxPHFitter()
    cph.fit(model_df, duration_col="duration", event_col="event")
    cph.print_summary(decimals=3)
    return kmf, cph, model_df


if __name__ == "__main__":
    data = add_duration_and_event(load_data())
    analyse(data)
    print("Figures saved in", FIG_DIR)
