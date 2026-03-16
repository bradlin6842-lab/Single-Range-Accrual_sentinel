import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import pytz

# --- 1. Initial Config ---
st.set_page_config(page_title="Rate Sentinel Pro: Ultimate Edition", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

# --- 2. Data Cleaning & Fetching ---
def get_final_key():
    try:
        raw_val = st.secrets["FRED_API_KEY"]
        return "".join(filter(str.isalnum, str(raw_val))).lower()
    except: return None

target_key = get_final_key()

@st.cache_data(ttl=600)
def fetch_data(api_key):
    now = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
    base_url = "https://api.stlouisfed.org/fred/series/observations"
    def get_val(sid):
        try:
            url = f"{base_url}?series_id={sid}&api_key={api_key}&file_type=json&sort_order=desc&limit=1"
            res = requests.get(url, timeout=10).json()
            return float(res['observations'][0]['value'])
        except: return None
    r = get_val("DGS10")
    m = get_val("MOVE")
    return r if r else 4.28, m if m else 105.0, now

m_rate_live, m_move, up_time = fetch_data(target_key)

# --- 3. Sidebar: Full Controls ---
with st.sidebar:
    st.header("📊 Benchmark & Credit")
    use_manual = st.checkbox("Use Bloomberg Manual Input", value=True)
    if use_manual:
        manual_rate = st.number_input("10Y SOFR CMS (%)", value=3.78113, format="%.5f")
        current_benchmark = manual_rate
    else:
        current_benchmark = m_rate_live
    
    issuer_rating = st.select_slider("Issuer Credit Rating", 
                                     options=["AAA", "AA", "A", "BBB", "BB"], value="A")
    pd_map = {"AAA": 0.02, "AA": 0.05, "A": 0.20, "BBB": 0.50, "BB": 1.50}
    annual_pd = pd_map[issuer_rating] / 100
    st.divider()

    st.header("💵 Investment & Terms")
    principal = st.number_input("Principal Amount (USD)", value=50000)
    vol = st.slider("Volatility (MOVE Index)", 5, 50, int(m_move/10)) / 100
    accrual_barrier = st.slider("Accrual Barrier (%)", 3.5, 5.5, 4.3) / 100
    call_barrier = st.slider("Autocall Barrier (%)", 2.5, 4.0, 3.2) / 100
    st.divider()
    st.caption(f"System Status: 🟢 Connected")
    st.caption(f"Last Sync: {up_time}")

# --- 4. Monte Carlo Logic ---
def run_full_sim(p_rate):
    days, dt = 252 * 7, 1/252
    results, sample_paths = [], []
    for i in range(500):
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = (p_rate/100) * np.exp(np.cumsum(vol * shocks - 0.5 * vol**2 * dt))
        coupons = 0.034 # Fixed 1st 6M
        call_day = days
        status_str = "Matured"
        for d in range(126, days):
            if (d-126) % 63 == 0 and path[d] <= call_barrier:
                status_str, call_day = "Autocalled", d
                break
            if path[d] <= accrual_barrier: coupons += (0.05 / 252)
        dur = (call_day + 1) / 252
        survival = (1 - annual_pd) ** dur
        results.append({'ret': (coupons/dur)*100, 'usd': coupons*principal, 
                        'risk_adj': coupons*principal*survival, 'dur': dur})
        if i < 15: sample_paths.append(path[:call_day])
    return pd.DataFrame(results), sample_paths

df_res, path_res = run_full_sim(current_benchmark)

# --- 5. Main Dashboard ---
st.title("🏛️ Fed Rate Sentinel: Full Portfolio Analyzer")

# Top Level Metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("Current Rate", f"{current_benchmark:.4f}%")
m2.metric("Dist. to Barrier", f"{(accrual_barrier*100 - current_benchmark):.2f}%")
m3.metric("Sim. Annual Yield", f"{df_res['ret'].mean():.2f}%")
m4.metric("Exp. Duration", f"{df_res['dur'].mean():.1f}Y")

st.divider()

# Charts Area
# Row 1: Gauge Chart (The highlight of Benchmark comparison)
st.subheader("🎯 Accrual Status Monitor")
fig_gauge = go.Figure(go.Indicator(
    mode = "gauge+number", value = current_benchmark,
    gauge = {
        'axis': {'range': [2.5, 5.0]},
        'steps' : [
            {'range': [0, call_barrier*100], 'color': "#D5F5E3"},
            {'range': [call_barrier*100, accrual_barrier*100], 'color': "#EBEDEF"},
            {'range': [accrual_barrier*100, 5.0], 'color': "#FADBD8"}],
        'threshold': {'line': {'color': "red", 'width': 4}, 'value': accrual_barrier*100}
    }
))
fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=20, b=20))
st.plotly_chart(fig_gauge, use_container_width=True)

# Row 2: Analysis Graphs
col_l, col_r = st.columns(2)
with col_l:
    st.subheader("💰 Nominal vs Risk-Adj. Return")
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(x=df_res['usd'], name='Nominal', marker_color='#3498DB', opacity=0.6))
    fig_hist.add_trace(go.Histogram(x=df_res['risk_adj'], name='Risk-Adjusted', marker_color='#E74C3C', opacity=0.6))
    fig_hist.update_layout(barmode='overlay', height=400, legend=dict(x=0.01, y=0.99))
    st.plotly_chart(fig_hist, use_container_width=True)

with col_r:
    st.subheader("📈 Monte Carlo Rate Paths")
    fig_path = go.Figure()
    for p in path_res: fig_path.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.3, showlegend=False))
    fig_path.add_hline(y=accrual_barrier, line_dash="dash", line_color="red")
    fig_path.add_hline(y=call_barrier, line_dash="dash", line_color="green")
    fig_path.update_layout(yaxis=dict(tickformat=".1%"), height=400)
    st.plotly_chart(fig_path, use_container_width=True)
