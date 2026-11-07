"""Contact-or-not decision rule, checked against the randomized email experiment.

Rule: contact a customer only if the extra money we expect from contacting them
is bigger than the cost of the contact.

    expected gain = predicted uplift in visits  x  revenue per extra visit
    contact if      expected gain > cost per contact

Revenue per extra visit comes from the experiment itself:
    (extra spend per emailed customer) / (extra visits per emailed customer).

Checking the rule: the email was assigned at random, so inside any group of
customers chosen from their features alone, "emailed minus not emailed" spend is
a fair estimate of what contacting that group really adds. We compare
    - contact nobody        (net = 0)
    - contact everybody
    - contact by the rule
in net revenue per 1,000 customers (extra spend minus contact costs). A bootstrap
gives a 95% interval, so a gain that is just noise shows up as such.
"""
import os

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

IN_PATH = "data/uplift_predictions.csv"
FIG_PATH = "docs/figures/decision_rule.png"
COSTS = [0.05, 0.10, 0.25, 0.50, 1.00, 2.00]  # cost per contact, same currency as spend
N_BOOT = 300


def load_data(path=IN_PATH):
    return pd.read_csv(path)


def revenue_per_extra_visit(treated, spend, visit):
    d_spend = spend[treated == 1].mean() - spend[treated == 0].mean()
    d_visit = visit[treated == 1].mean() - visit[treated == 0].mean()
    return d_spend / d_visit


def net_per_customer(mask, treated, spend, cost):
    """Net revenue per customer in the whole population if exactly the customers
    in `mask` are contacted: share contacted x (extra spend among them - cost)."""
    t = mask & (treated == 1)
    c = mask & (treated == 0)
    if t.sum() == 0 or c.sum() == 0:
        return 0.0
    extra = spend[t].mean() - spend[c].mean()
    return mask.mean() * (extra - cost)


def run_policies(treated, spend, visit, pred, cost):
    v = revenue_per_extra_visit(treated, spend, visit)
    rule = pred * v > cost
    everyone = np.ones(len(pred), dtype=bool)
    return {"share": rule.mean(),
            "rule": net_per_customer(rule, treated, spend, cost),
            "all": net_per_customer(everyone, treated, spend, cost)}


def evaluate(df, costs=COSTS, n_boot=N_BOOT, seed=0):
    treated = df["treated"].to_numpy()
    spend = df["spend"].to_numpy(dtype=float)
    visit = df["visit"].to_numpy(dtype=float)
    pred = df["predicted_uplift"].to_numpy(dtype=float)
    print(f"Revenue per extra visit: {revenue_per_extra_visit(treated, spend, visit):.2f}")

    rng = np.random.default_rng(seed)
    boots = [rng.integers(0, len(df), len(df)) for _ in range(n_boot)]
    rows = []
    for cost in costs:
        base = run_policies(treated, spend, visit, pred, cost)
        diffs = []
        for idx in boots:
            r = run_policies(treated[idx], spend[idx], visit[idx], pred[idx], cost)
            diffs.append(r["rule"] - r["all"])
        lo, hi = np.percentile(diffs, [2.5, 97.5])
        rows.append({"cost per contact": cost,
                     "share contacted by rule": f"{base['share']:.0%}",
                     "net per 1,000: contact none": 0,
                     "net per 1,000: contact all": round(base["all"] * 1000),
                     "net per 1,000: rule": round(base["rule"] * 1000),
                     "rule minus all (95% CI)": f"{(base['rule'] - base['all']) * 1000:+.0f} ({lo * 1000:+.0f} to {hi * 1000:+.0f})"})
    return pd.DataFrame(rows)


def plot(table, path=FIG_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    surface, ink, muted = "#fcfcfb", "#0b0b0b", "#52514e"
    blue, orange = "#2a78d6", "#eb6834"
    x = table["cost per contact"]
    fig, ax = plt.subplots(figsize=(7, 4.2), facecolor=surface)
    ax.set_facecolor(surface)
    ax.axhline(0, color=muted, linewidth=1)
    ax.plot(x, table["net per 1,000: contact all"], color=blue, linewidth=2, marker="o", markersize=6,
            label="Contact everyone")
    ax.plot(x, table["net per 1,000: rule"], color=orange, linewidth=2, marker="o", markersize=6,
            label="Contact by the rule")
    ax.set_xscale("log")
    ax.set_xticks(list(x))
    ax.set_xticklabels([f"{c:.2f}" for c in x])
    ax.minorticks_off()
    ax.annotate("Contact nobody = 0", (x.iloc[-1], 0), textcoords="offset points", xytext=(0, 8),
                ha="right", color=muted, fontsize=9)
    ax.set_xlabel("Cost per contact (log scale)", color=ink)
    ax.set_ylabel("Net revenue per 1,000 customers", color=ink)
    ax.set_title("When does targeting beat contacting everyone?", color=ink, loc="left")
    ax.tick_params(colors=muted)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color("#c9c8c3")
    ax.grid(axis="y", color="#e6e5e1", linewidth=0.8)
    ax.legend(frameon=False, labelcolor=ink)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=surface)
    plt.close(fig)


if __name__ == "__main__":
    table = evaluate(load_data())
    print(table.to_string(index=False))
    plot(table)
    print("Figure saved in", FIG_PATH)
