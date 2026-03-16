import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import pytz

# --- 1. Initial Config ---
st.set_page_config(page_title="Rate Sentinel Pro: Scenario Comparison", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

def get_final_key():
    try:
        raw_val = st.secrets["FRED_API_KEY"]
        return "".join(filter(str.isalnum, str(raw_val))).lower()
    except: return None

target_key = get_final_key()

@st.cache_data(ttl=600)
def fetch_live_data(api_key):
    now = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
    base_url = "https://api.stlouisfed.org/fred/series/observations"
    def get_val(sid):
        try:
            url = f"{base_url}?series_id={sid}&api_key={api_key}&file_type=json&sort_order=desc&limit=1"
            res = requests.get(url, timeout=10).json()
            return float(res['observations'][0]['value'])
        except: return None
    # FETCH FROM FRED API
    t_rate = get_val("DGS10")
    m_move = get_val("MOVE")
    return t_rate if t_rate else 4.28, m_move if m_move else 105.0, now

# Live Data from FRED
fred_rate, move_vol, up_time = fetch_live_data(target_key)

# --- 2. Sidebar: Multi-Scenario Controls ---
with st.sidebar:
    st.header("🔌 Live Data (FRED API)")
    st.info(f"10Y Treasury: {fred_rate:.2f}%")
    st.info(f"MOVE Index: {move_vol:.1f}")
    
    st.header("🖥️ Bloomberg Manual Input")
    sofr_rate = st.number_input("10Y SOFR CMS (%)", value=3.7811, format="%.5f")
    
    st.divider()
    st.header("🛡️ Risk & Terms")
    issuer_rating = st.select_slider("Credit Rating", options=["AAA", "AA", "A", "BBB", "BB"], value="A")
    pd_map = {"AAA": 0.02, "AA": 0.05, "A": 0.20, "BBB": 0.50, "BB": 1.50}
    annual_pd = pd_map[issuer_rating] / 100
    
    vol_adj = st.slider("Volatility Buffer", 0.5, 2.0, 1.0)
    final_vol = (move_vol / 1000) * vol_adj
    
    accrual_barrier = st.slider("Accrual Barrier (%)", 3.5, 5.5, 4.3) / 100
    call_barrier = st.slider("Autocall Barrier (%)", 2.5, 4.0, 3.2) / 100
    st.caption(f"Last Sync: {up_time}")

# --- 3. Dual-Scenario Simulation Logic ---
def run_comparison_sim(rates_dict, principal=50000):
    days, dt = 252 * 7, 1/252
    comparison_results = {}
    
    for label, start_rate in rates_dict.items():
        results = []
        for _ in range(300): # 300 iterations per scenario for performance
            shocks = np.random.normal(0, np.sqrt(dt), days)
            path = (start_rate/100) * np.exp(np.cumsum(final_vol * shocks - 0.5 * final_vol**2 * dt))
            coupons = 0.034
            call_day = days
            for d in range(126, days):
                if (d-126) % 63 == 0 and path[d] <= call_barrier:
                    call_day = d; break
                if path[d] <= accrual_barrier: coupons += (0.05 / 252)
            dur = (call_day + 1) / 252
            survival = (1 - annual_pd) ** dur
            results.append({'yield': (coupons/dur)*100, 'usd': coupons*principal*survival})
        comparison_results[label] = pd.DataFrame(results)
    return comparison_results

scenarios = {"Treasury (FRED)": fred_rate, "SOFR CMS (Bloomberg)": sofr_rate}
sim_data = run_comparison_sim(scenarios)

# --- 4. Main Dashboard: Scenario Comparison ---
st.title("🏛️ Sentinel: Scenario Comparison Dashboard")

# Comparison Metrics Table
st.subheader("📊 Scenario Comparison Metrics")
comp_col1, comp_col2 = st.columns(2)

for i, (name, data) in enumerate(sim_data.items()):
    with [comp_col1, comp_col2][i]:
        st.markdown(f"### {name}")
        st.metric("Avg. Annual Yield", f"{data['yield'].mean():.2f}%")
        st.metric("Risk-Adj. Return (USD)", f"${data['usd'].mean():,.0f}")
        dist = accrual_barrier*100 - scenarios[name]
        st.metric("Distance to Barrier", f"{dist:.2f}%", delta=f"{dist:.2f}%", delta_color="normal")

st.divider()

# Overlapping Visualization
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("💰 Return Distribution Comparison")
    fig_comp = go.Figure()
    colors = {"Treasury (FRED)": "#E74C3C", "SOFR CMS (Bloomberg)": "#2ECC71"}
    for name, data in sim_data.items():
        fig_comp.add_trace(go.Violin(x=data['usd'], name=name, line_color=colors[name], box_visible=True, meanline_visible=True))
    fig_comp.update_layout(xaxis_title="Risk-Adjusted Gain (USD)", height=450, showlegend=False)
    st.plotly_chart(fig_comp, use_container_width=True)

with col_r:
    st.subheader("🎯 Accrual Safety Gauge (Current SOFR)")
    # Focus on the more relevant SOFR for the gauge
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = sofr_rate,
        title = {'text': "Current SOFR CMS Position"},
        gauge = {
            'axis': {'range': [2.5, 5.0]},
            'steps' : [
                {'range': [0, call_barrier*100], 'color': "#D5F5E3"},
                {'range': [call_barrier*100, accrual_barrier*100], 'color': "#EBEDEF"},
                {'range': [accrual_barrier*100, 5.0], 'color': "#FADBD8"}],
            'threshold': {'line': {'color': "red", 'width': 4}, 'value': accrual_barrier*100}
        }
    ))
    fig_gauge.update_layout(height=400)
    st.plotly_chart(fig_gauge, use_container_width=True)
