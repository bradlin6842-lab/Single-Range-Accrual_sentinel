import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import pytz

# --- 1. Initial Configuration ---
st.set_page_config(page_title="Rate Sentinel Pro: Dual Scenario Comparison", layout="wide")
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
    # FETCH FROM FRED API (This uses your API key!)
    t_rate = get_val("DGS10")
    m_move = get_val("MOVE")
    return t_rate if t_rate else 4.28, m_move if m_move else 105.0, now

# 📡 Real-time Data from Fed API
fred_rate, move_vol, up_time = fetch_live_data(target_key)

# --- 2. Sidebar: Dual-Scenario & Principal Control ---
with st.sidebar:
    st.header("💰 Portfolio Input")
    principal = st.number_input("Principal Amount (USD)", value=50000, step=5000)
    
    st.divider()
    st.header("🔌 Live Data (FRED API)")
    st.info(f"10Y Treasury (DGS10): {fred_rate:.2f}%")
    st.info(f"MOVE Index: {move_vol:.1f}")
    
    st.header("🖥️ Bloomberg Input")
    sofr_rate = st.number_input("10Y SOFR CMS (%)", value=3.78113, format="%.5f")
    
    st.divider()
    st.header("🛡️ Risk & Terms")
    issuer_rating = st.select_slider("Credit Rating", options=["AAA", "AA", "A", "BBB", "BB"], value="A")
    pd_map = {"AAA": 0.02, "AA": 0.05, "A": 0.20, "BBB": 0.50, "BB": 1.50}
    annual_pd = pd_map[issuer_rating] / 100
    
    accrual_barrier = st.slider("Accrual Barrier (%)", 3.5, 5.5, 4.3) / 100
    call_barrier = st.slider("Autocall Barrier (%)", 2.5, 4.0, 3.2) / 100
    
    # Use MOVE Index to drive simulation volatility
    sim_vol = (move_vol / 1000)
    st.caption(f"Last Sync: {up_time}")

# --- 3. Dual-Scenario Simulation Logic ---
def run_comparison_sim(rates_dict, p_val):
    days, dt = 252 * 7, 1/252
    all_results = {}
    
    for label, start_rate in rates_dict.items():
        results = []
        for _ in range(400):
            shocks = np.random.normal(0, np.sqrt(dt), days)
            path = (start_rate/100) * np.exp(np.cumsum(sim_vol * shocks - 0.5 * sim_vol**2 * dt))
            coupons = 0.034 # Fixed 1st 6M
            call_day = days
            for d in range(126, days):
                if (d-126) % 63 == 0 and path[d] <= call_barrier:
                    call_day = d; break
                if path[d] <= accrual_barrier: coupons += (0.05 / 252)
            dur = (call_day + 1) / 252
            survival = (1 - annual_pd) ** dur
            total_wealth = (p_val + (coupons * p_val)) * survival
            results.append({'wealth': total_wealth, 'yield': (coupons/dur)*100})
        all_results[label] = pd.DataFrame(results)
    return all_results

scenarios = {"Treasury (FRED)": fred_rate, "SOFR CMS (Bloomberg)": sofr_rate}
sim_data = run_comparison_sim(scenarios, principal)

# --- 4. Main Dashboard ---
st.title("🏛️ Sentinel: Dual-Scenario Wealth Analyzer")

# Metrics Comparison Table
st.subheader("📊 Scenario Comparison Metrics")
col1, col2 = st.columns(2)

colors = {"Treasury (FRED)": "#E74C3C", "SOFR CMS (Bloomberg)": "#2ECC71"}

for i, (name, data) in enumerate(sim_data.items()):
    with [col1, col2][i]:
        st.markdown(f"### <span style='color:{colors[name]}'>{name}</span>", unsafe_allow_html=True)
        st.metric("Avg. Total Wealth", f"${data['wealth'].mean():,.0f}")
        st.metric("Exp. Annual Yield", f"{data['yield'].mean():.2f}%")
        dist = accrual_barrier*100 - scenarios[name]
        st.metric("Dist. to Barrier", f"{dist:.2f}%")

st.divider()

# Visualization: The "Scenario Comparison" Part
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("💰 Total Wealth Distribution Comparison")
    fig_comp = go.Figure()
    for name, data in sim_data.items():
        fig_comp.add_trace(go.Violin(x=data['wealth'], name=name, line_color=colors[name], box_visible=True, meanline_visible=True))
    
    fig_comp.update_layout(xaxis_title="Projected Wealth at Maturity (USD)", 
                           height=500, showlegend=True,
                           xaxis=dict(range=[principal * 0.9, principal * 1.5]))
    st.plotly_chart(fig_comp, use_container_width=True)
    st.caption(f"Red = FED API Scenario | Green = Bloomberg Scenario. Base Principal: ${principal:,.0f}")

with col_r:
    st.subheader("🎯 Real-Time SOFR CMS Position")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = sofr_rate,
        gauge = {
            'axis': {'range': [2.5, 5.0]},
            'steps' : [
                {'range': [0, call_barrier*100], 'color': "#D5F5E3"},
                {'range': [call_barrier*100, accrual_barrier*100], 'color': "#EBEDEF"},
                {'range': [accrual_barrier*100, 5.0], 'color': "#FADBD8"}],
            'threshold': {'line': {'color': "red", 'width': 4}, 'value': accrual_barrier*100}
        }
    ))
    fig_gauge.update_layout(height=450)
    st.plotly_chart(fig_gauge, use_container_width=True)
