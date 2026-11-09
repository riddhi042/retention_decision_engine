"""Retention Decision Engine - interactive dashboard.

Reads the small summary files in dashboard/summary/ (made by
export_dashboard_data.py), so it runs without the database or raw data.
"""
import json
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Retention Decision Engine", layout="wide")

HERE = os.path.dirname(os.path.abspath(__file__))
SUMMARY = os.path.join(HERE, "summary")
BLUE, ORANGE, GREY, INK, MUTED = "#6c5ce7", "#f0614f", "#9b94b3", "#2b2540", "#6b6483"
SERIES = [BLUE, ORANGE]

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');
      html, body, [class*="st-"], .stMarkdown, button {font-family: 'Nunito', sans-serif !important;}
      .block-container {padding-top: 3.4rem; max-width: 1180px;}
      .hero {background: linear-gradient(120deg, #efe9ff 0%, #ffe9e3 55%, #fff3d6 100%); border-radius: 26px;
             padding: 2rem 2.2rem 1.7rem 2.2rem; margin-bottom: 1.3rem; box-shadow: 0 6px 24px rgba(108,92,231,0.10);}
      .hero h1 {font-size: 2.5rem; font-weight: 800; letter-spacing: -0.02em; margin: 0 0 0.35rem 0; padding: 0; color: #2b2540;}
      .hero p {color: #5b5474; font-size: 1.08rem; margin: 0 0 1rem 0; max-width: 46rem; line-height: 1.55;}
      .chip {display: inline-block; background: rgba(255,255,255,0.8); color: #4b3bb8; border-radius: 999px;
             padding: 0.22rem 0.8rem; font-size: 0.82rem; font-weight: 700; margin: 0 0.4rem 0.3rem 0;}
      [data-testid="stMetric"] {border-radius: 20px; padding: 16px 20px; box-shadow: 0 3px 14px rgba(108,92,231,0.08);}
      [data-testid="stColumn"]:nth-child(1) [data-testid="stMetric"] {background: #efe9ff;}
      [data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] {background: #ffe9e3;}
      [data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] {background: #fff3d6;}
      [data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] {background: #e3f6ee;}
      [data-testid="stMetricLabel"] p {color: #5b5474; font-size: 0.86rem; font-weight: 600;}
      [data-testid="stMetricValue"] {font-weight: 800;}
      div[data-testid="stPlotlyChart"] {background: #ffffff; border-radius: 22px; padding: 10px 12px;
             box-shadow: 0 4px 18px rgba(108,92,231,0.09);}
      button[role="tab"] {font-weight: 700; font-size: 1rem;}
      .takeaway {background: #f3eeff; border-radius: 18px; padding: 0.85rem 1.1rem; margin: 0.8rem 0 1.2rem 0;
                 color: #2b2540; line-height: 1.5;}
      [data-testid="stAlert"] {border-radius: 16px;}
      [data-testid="stExpander"] {border-radius: 16px;}
      .footer {text-align: center; color: #9b94b3; font-size: 0.85rem; margin-top: 2rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load(name):
    path = os.path.join(SUMMARY, name)
    if name.endswith(".json"):
        with open(path) as f:
            return json.load(f)
    return pd.read_csv(path)


def style(fig, height=380, legend=True):
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=84, b=10), title_y=0.98, title_yanchor="top", paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)", font=dict(color=INK, size=13, family="Nunito, sans-serif"), showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0),
        hoverlabel=dict(bgcolor="white", font_size=13),
    )
    fig.update_xaxes(showline=True, linecolor="#d9d1ea", gridcolor="#f0ebf8", zeroline=False, tickfont=dict(color=MUTED))
    fig.update_yaxes(showline=False, gridcolor="#f0ebf8", zeroline=False, tickfont=dict(color=MUTED))
    return fig


def takeaway(text):
    st.markdown(f'<div class="takeaway">&#10024; {text}</div>', unsafe_allow_html=True)


S = load("summary.json")

st.markdown(
    """
    <div class="hero">
      <h1>Retention Decision Engine</h1>
      <p>Which customers are worth trying to keep, and is contacting them worth the cost?
      Built on real retail purchases (UCI Online Retail II) and a randomized email experiment (Hillstrom).</p>
      <span class="chip">survival analysis</span><span class="chip">customer value</span>
      <span class="chip">uplift modelling</span><span class="chip">contact-or-not rule</span>
    </div>
    """,
    unsafe_allow_html=True,
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Customers analysed", f"{S['customers']:,}")
k2.metric("Churned (no purchase in 180 days)", f"{S['churn_rate']:.0%}")
k3.metric("Revenue from the top 10% of customers", f"{S['top_decile_revenue_share']:.0%}")
k4.metric("Lift in site visits from an email", f"+{S['visit_effect'] * 100:.1f} pts")

tab1, tab2, tab3, tab4 = st.tabs(["🛍️ Customers", "⏳ When customers leave", "💎 Customer value", "💌 Email and the decision rule"])

# ------------------------------------------------------------------ tab 1
with tab1:
    takeaway("Revenue is concentrated in a small group of customers, and many customers go quiet and come back later.")
    c1, c2 = st.columns(2)
    monthly = load("monthly.csv")
    fig = go.Figure(go.Scatter(x=monthly["month"], y=monthly["revenue"], mode="lines", line=dict(color=BLUE, width=2.5),
                               fill="tozeroy", fillcolor="rgba(108,92,231,0.14)", name="Revenue",
                               hovertemplate="%{x|%b %Y}<br>Revenue %{y:,.0f}<extra></extra>"))
    fig.update_layout(title=dict(text="Monthly revenue (seasonal, with a Christmas peak)", x=0, font=dict(size=15)))
    c1.plotly_chart(style(fig, legend=False), use_container_width=True)

    dec = load("deciles.csv")
    fig = go.Figure(go.Bar(x=dec["decile"], y=dec["pct_of_revenue"], marker_color=[ORANGE] + [BLUE] * 9,
                           customdata=dec[["customers", "avg_revenue"]],
                           hovertemplate="Decile %{x}<br>%{y}% of revenue<br>Average per customer %{customdata[1]:,.0f}<extra></extra>"))
    fig.update_layout(title=dict(text="Share of revenue by customer decile (1 = top 10%)", x=0, font=dict(size=15)),
                      xaxis=dict(dtick=1, title="Customer decile"), yaxis=dict(title="% of revenue"))
    c2.plotly_chart(style(fig, legend=False), use_container_width=True)

    cohort = load("cohort.csv")
    pivot = cohort.pivot(index="cohort_month", columns="month_number", values="retention_pct")
    fig = go.Figure(go.Heatmap(z=pivot.values, x=pivot.columns, y=pivot.index.astype(str), zmin=0, zmax=60,
                               colorscale=[[0, "#f6f2ff"], [1, "#4b3bb8"]], colorbar=dict(title="% active"),
                               hovertemplate="Cohort %{y}<br>%{x} months later<br>%{z}% bought<extra></extra>"))
    fig.update_layout(title=dict(text="Cohort retention: share of each first-purchase month who buy again", x=0, font=dict(size=15)),
                      xaxis=dict(title="Months since first purchase"), yaxis=dict(autorange="reversed"))
    st.plotly_chart(style(fig, height=470, legend=False), use_container_width=True)

# ------------------------------------------------------------------ tab 2
with tab2:
    takeaway(
        f"About {S['survival_365']:.0%} of customers are still active a year after their first purchase. "
        "Customers with bigger first orders stay longer; UK and non-UK customers look the same."
    )
    km = load("km_curves.csv")
    split = st.radio("Compare customers by", ["All customers", "First order size", "Country"], horizontal=True)
    sub = km[km["split"] == split]
    fig = go.Figure()
    for i, (label, g) in enumerate(sub.groupby("group")):
        color = SERIES[i % 2]
        rgb = tuple(int(color[j:j + 2], 16) for j in (1, 3, 5))
        fig.add_trace(go.Scatter(x=list(g["day"]) + list(g["day"][::-1]), y=list(g["upper"]) + list(g["lower"][::-1]),
                                 fill="toself", fillcolor=f"rgba({rgb[0]},{rgb[1]},{rgb[2]},0.15)", line=dict(width=0),
                                 hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=g["day"], y=g["survival"], mode="lines", line=dict(color=color, width=2.5),
                                 name=f"{label} (n={int(g['customers'].iloc[0]):,})",
                                 hovertemplate="Day %{x}<br>%{y:.1%} still active<extra></extra>"))
    fig.update_layout(title=dict(text="Share of customers still active, by days since first purchase", x=0, font=dict(size=15)),
                      xaxis=dict(title="Days since first purchase"), yaxis=dict(title="Still active", tickformat=".0%", range=[0.3, 1.02]))
    st.plotly_chart(style(fig, height=420), use_container_width=True)
    st.caption("The curve goes flat after about 550 days partly because of how churn is defined (it needs 180 quiet days "
               "before the end of the data), so it does not mean long-standing customers never leave.")

    a, b, c = st.columns(3)
    a.metric("Still active at 90 days", f"{S['survival_90']:.0%}")
    b.metric("Still active at 180 days", f"{S['survival_180']:.0%}")
    c.metric("Still active at 1 year", f"{S['survival_365']:.0%}")

    cox = load("cox.csv")
    names = {"is_uk": "UK customer", "log_first_order_value": "Larger first order (log scale)"}
    fig = go.Figure()
    fig.add_vline(x=1, line_color=GREY, line_dash="dash")
    fig.add_trace(go.Scatter(x=cox["hazard_ratio"], y=[names.get(c, c) for c in cox["covariate"]], mode="markers",
                             marker=dict(color=BLUE, size=11),
                             error_x=dict(type="data", symmetric=False, array=cox["upper"] - cox["hazard_ratio"],
                                          arrayminus=cox["hazard_ratio"] - cox["lower"], color=BLUE),
                             customdata=cox["p"], hovertemplate="%{y}<br>Hazard ratio %{x:.2f}<br>p = %{customdata:.4f}<extra></extra>"))
    fig.update_layout(title=dict(text="What changes the risk of leaving? (hazard ratio, left of 1 = leaves more slowly)", x=0, font=dict(size=15)),
                      xaxis=dict(title="Hazard ratio (95% interval)"))
    st.plotly_chart(style(fig, height=240, legend=False), use_container_width=True)

# ------------------------------------------------------------------ tab 3
with tab3:
    takeaway(
        f"The model predicts who buys again well (AUC {S['clv_auc']:.2f}) and ranks customers a little better than past revenue alone, "
        "but it does not find the very top spenders better than a simple baseline."
    )
    a, b, c = st.columns(3)
    a.metric("Repeat-purchase AUC (0.5 = coin flip)", f"{S['clv_auc']:.2f}")
    b.metric("Rank correlation: model vs past revenue", f"{S['clv_rho_model']:.2f} vs {S['clv_rho_hist']:.2f}")
    c.metric("Real future revenue in top 10%: model vs past revenue", f"{S['clv_top10_model']:.0%} vs {S['clv_top10_hist']:.0%}")
    cal = load("clv_calibration.csv")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=cal["decile"], y=cal["predicted"], name="Predicted 180-day value", marker_color=BLUE))
    fig.add_trace(go.Bar(x=cal["decile"], y=cal["actual"], name="Actual 180-day revenue", marker_color=ORANGE))
    fig.update_layout(barmode="group", bargap=0.25, title=dict(text="Predicted vs actual 180-day value by predicted decile (1 = highest)", x=0, font=dict(size=15)),
                      xaxis=dict(dtick=1, title="Predicted-value decile"), yaxis=dict(title="Average per customer"))
    st.plotly_chart(style(fig, height=400), use_container_width=True)
    st.caption("Every customer is scored by models that never saw their own outcome (5-fold cross-fitting), using only purchases before 9 June 2011.")

# ------------------------------------------------------------------ tab 4
with tab4:
    lo_, hi_ = S["visit_effect_lower"], S["visit_effect_upper"]
    takeaway(
        f"The email works: site visits rose from {S['visit_control']:.1%} to {S['visit_emailed']:.1%} "
        f"(+{S['visit_effect'] * 100:.1f} points, interval {lo_ * 100:.1f} to {hi_ * 100:.1f}). "
        "The model could not reliably pick out who responds most, so the best rule is close to a simple break-even check."
    )
    ud = load("uplift_deciles.csv")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=ud["decile"], y=ud["actual"], name="Actual lift (95% interval)", marker_color=BLUE,
                         error_y=dict(type="data", symmetric=False, array=ud["upper"] - ud["actual"],
                                      arrayminus=ud["actual"] - ud["lower"], color=MUTED)))
    fig.add_trace(go.Scatter(x=ud["decile"], y=ud["predicted"], name="Model's predicted lift", mode="lines+markers",
                             line=dict(color=ORANGE, width=2.5), marker=dict(size=8)))
    fig.update_layout(title=dict(text="Does the model find who responds most? (deciles of predicted lift in visits)", x=0, font=dict(size=15)),
                      xaxis=dict(dtick=1, title="Decile of predicted lift (1 = highest)"), yaxis=dict(title="Extra visit probability", tickformat=".0%"))
    st.plotly_chart(style(fig, height=380), use_container_width=True)

    st.subheader("Try the decision rule")
    st.write("Contact a customer only if the extra revenue we expect from them is more than the cost of contacting them. "
             "Move the slider to change what one contact costs.")
    curve = load("decision_curve.csv")
    cost = st.slider("Cost per contact", float(curve["cost"].min()), float(curve["cost"].max()), 0.5, 0.05)
    row = curve.iloc[(curve["cost"] - cost).abs().argmin()]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Customers the rule contacts", f"{row['share_contacted']:.0%}")
    m2.metric("Net per 1,000: contact everyone", f"{row['net_all']:,.0f}")
    m3.metric("Net per 1,000: contact by the rule", f"{row['net_rule']:,.0f}")
    m4.metric("Net per 1,000: contact nobody", "0")

    if row["diff_lower"] > 0:
        verdict = "The rule beats contacting everyone here, and the gain is outside the noise."
    elif row["diff_upper"] < 0:
        verdict = "The rule does worse than contacting everyone here."
    else:
        verdict = "No reliable difference between the rule and contacting everyone at this cost."
    st.info(f"At {row['cost']:.2f} per contact: {verdict} "
            f"(rule minus contact-everyone: {row['diff']:+,.0f} per 1,000, interval {row['diff_lower']:+,.0f} to {row['diff_upper']:+,.0f}).")

    fig = go.Figure()
    fig.add_hline(y=0, line_color=GREY)
    fig.add_trace(go.Scatter(x=curve["cost"], y=curve["net_all"], mode="lines", name="Contact everyone", line=dict(color=BLUE, width=2.5)))
    fig.add_trace(go.Scatter(x=curve["cost"], y=curve["net_rule"], mode="lines", name="Contact by the rule", line=dict(color=ORANGE, width=2.5)))
    fig.add_vline(x=row["cost"], line_color=INK, line_dash="dot")
    fig.update_layout(title=dict(text="Net revenue per 1,000 customers as contact cost rises", x=0, font=dict(size=15)),
                      xaxis=dict(title="Cost per contact"), yaxis=dict(title="Net revenue per 1,000 customers"))
    st.plotly_chart(style(fig, height=380), use_container_width=True)
    breakeven = S["spend_emailed"] - S["spend_control"]
    st.caption(f"Each email adds about {breakeven:.2f} of spend per customer, so contacting everyone pays off until a contact costs roughly that much. "
               "Above it, the rule's value is mostly in knowing when not to contact.")

with st.expander("Limits and assumptions"):
    st.markdown(
        "- Churn means no purchase for more than 180 days, counted from the last date in the data (9 December 2011). It is a judgement call.\n"
        "- Revenue figures are revenue, not profit. \"Net\" means extra spend minus contact costs.\n"
        "- The retail customers and the email-experiment customers are different people. The decision rule is demonstrated on the email experiment.\n"
        "- Only about 1% of emailed customers bought, so purchases were too rare to model directly; the model predicts site visits and revenue per visit is estimated from the average effect.\n"
        "- The model's predicted lift is larger than the real lift at the top, so trust its ordering more than its size."
    )

st.markdown('<div class="footer">Python · PostgreSQL · lifelines · scikit-learn · Streamlit · Plotly</div>', unsafe_allow_html=True)
