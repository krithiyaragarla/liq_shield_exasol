"""LiqShield Streamlit dashboard.  Run:  streamlit run app/dashboard.py   (API must be running)"""
import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API = os.getenv("LIQSHIELD_API", "http://127.0.0.1:8000")
st.set_page_config(page_title="LiqShield", layout="wide", page_icon="🛡")


@st.cache_data(ttl=3)
def get(path: str, **params):
    r = requests.get(f"{API}{path}", params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def usd(x: float) -> str:
    return f"${x:,.0f}"


try:
    health = get("/")
except Exception as e:  # noqa: BLE001
    st.error(f"Cannot reach the API at {API}. Start it with `uvicorn app.api:app` ({e})")
    st.stop()

st.title("🛡 LiqShield")
st.caption("Can we meet our time-sensitive obligations with the cash and collateral we can actually mobilise?  "
           f"Analytics engine: **{health['backend'].upper()}**")

presets = get("/api/presets")
with st.sidebar:
    st.header("Stress sandbox")
    choice = st.radio("Scenario preset", list(presets) + ["Custom"], index=0)
    base = presets.get(choice, presets["Base case"])
    disabled = choice != "Custom"
    haircut = st.slider("Haircut shock (+pp on every asset)", 0.0, 0.30, float(base["haircut_shock"]), 0.01,
                        disabled=disabled)
    delay = st.slider("Incoming settlement delay (days)", 0, 4, int(base["delay_days"]), disabled=disabled)
    margin = st.slider("Margin-call multiplier", 1.0, 2.0, float(base["margin_mult"]), 0.05, disabled=disabled)
    st.divider()
    st.caption("Every slider re-runs parameterised SQL on the database.")

sc = dict(haircut_shock=haircut, delay_days=delay, margin_mult=margin)
ladder = pd.DataFrame(get("/api/liquidity-ladder", **sc))
m = get("/api/metrics", **sc)
fund = get("/api/funding", **sc)

# ---- status banner ---------------------------------------------------------------
if m["first_shortfall_day"] is None:
    st.success(f"✅ NO SHORTFALL — lowest projected buffer {usd(m['min_buffer'])}")
else:
    st.error(f"🚨 SHORTFALL — first breach on T+{m['first_shortfall_day']}, peak gap {usd(m['peak_shortfall'])}, "
             f"{m['shortfall_days']} day(s) below zero")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Lowest buffer", usd(m["min_buffer"]))
c2.metric("Peak shortfall (severity)", usd(m["peak_shortfall"]))
c3.metric("Time to shortfall", "none" if m["first_shortfall_day"] is None else f"T+{m['first_shortfall_day']}")
c4.metric("Cheapest cover cost", usd(fund["total_cost"]))

# ---- ladder chart ----------------------------------------------------------------
x = [f"T+{int(d)}" for d in ladder["day_offset"]]
fig = go.Figure()
fig.add_bar(x=x, y=ladder["net_cashflow"], name="Daily net cashflow", marker_color="#94a3b8")
fig.add_scatter(x=x, y=ladder["mobilisable"], name="Mobilisable collateral+cash", mode="lines",
                line=dict(color="#2563eb", dash="dot"))
bad = ladder["liquidity_buffer"] < 0
fig.add_scatter(x=x, y=ladder["liquidity_buffer"], name="Liquidity buffer", mode="lines+markers",
                line=dict(color="#dc2626" if bad.any() else "#16a34a", width=3),
                marker=dict(color=["#dc2626" if b else "#16a34a" for b in bad], size=9))
fig.add_hline(y=0, line_dash="dash", line_color="#dc2626", annotation_text="Shortfall threshold")
fig.update_layout(title="Liquidity ladder", hovermode="x unified", yaxis_title="USD", height=430,
                  legend=dict(orientation="h", y=-0.2))
st.plotly_chart(fig, use_container_width=True)

tab1, tab2, tab3, tab4 = st.tabs(["Funding actions", "Eligible collateral", "Counterparty calls", "Monte Carlo (in-DB UDF)"])

with tab1:
    if not fund["waterfall"]:
        st.info("No shortfall in this scenario, so no intervention is needed.")
    else:
        st.markdown("**Cheapest-first funding waterfall** (only facilities drawable by the first breach day)")
        wf = pd.DataFrame(fund["waterfall"])
        wf["in_time"] = wf["in_time"].map({1: "yes", 0: "TOO LATE"})
        st.dataframe(wf[["facility_name", "limit_amount", "available_from_day", "cost_bps", "in_time",
                         "draw_amount", "intervention_cost"]].rename(columns=str.title), hide_index=True,
                     use_container_width=True)
        if fund["residual_gap"] > 0:
            st.error(f"Residual uncovered gap: {usd(fund['residual_gap'])} — facilities are insufficient.")
        else:
            st.success(f"Shortfall fully covered. Total intervention cost {usd(fund['total_cost'])}.")
        st.markdown("**Single-action comparison**")
        sa = pd.DataFrame(fund["single"])
        sa["in_time"] = sa["in_time"].map({1: "yes", 0: "TOO LATE"})
        sa["covers_alone"] = sa["covers_alone"].map({1: "yes", 0: "no"})
        st.dataframe(sa[["facility_name", "available_from_day", "in_time", "covers_alone", "covered_amount", "cost"]]
                     .rename(columns=str.title), hide_index=True, use_container_width=True)

with tab2:
    col = pd.DataFrame(get("/api/collateral", haircut_shock=haircut))
    st.dataframe(col[["asset_id", "asset_type", "custodian", "market_value", "encumbered_flag",
                      "settlement_lag_days", "haircut_pct", "eligible_value"]], hide_index=True,
                 use_container_width=True)
    st.metric("Total eligible after haircuts & encumbrances", usd(col["eligible_value"].sum()))

with tab3:
    st.dataframe(pd.DataFrame(get("/api/exposure")), hide_index=True, use_container_width=True)

with tab4:
    vol = st.slider("Haircut shock volatility (σ)", 0.01, 0.20, 0.05, 0.01)
    mc = get("/api/monte-carlo", vol=vol, n_paths=2000, seed=42)
    st.caption(f"Executed in: **{mc['executed_in']}**")
    a, b, c = st.columns(3)
    a.metric("Base eligible collateral", usd(mc["base_eligible"]))
    b.metric("5th-percentile eligible collateral", usd(mc["p5_eligible"]))
    c.metric("Tail loss in eligible value", usd(mc["tail_loss"]))
    st.dataframe(pd.DataFrame(mc["assets"]), hide_index=True, use_container_width=True)

with st.expander("Raw ladder (database output)"):
    st.dataframe(ladder, hide_index=True, use_container_width=True)
