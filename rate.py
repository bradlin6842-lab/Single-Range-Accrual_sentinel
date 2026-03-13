import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import pytz

# --- 1. Initial Configuration ---
st.set_page_config(page_title="Rate Sentinel Pro: Risk-Adjusted Edition", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

# --- 2. Data Cleaning & API Fetching ---
def get_final_key():
    try:
        raw_val = st.secrets["FRED_API_KEY"]
        # Scrubbing: Keep only alphanumeric and force lowercase
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
            if 'observations' in res and len(res['observations']) > 0:
                v = res['observations'][0]['value']
                return float(v) if v != "." else None
        except: return None
        return None

    r = get_val("DGS10")
    m = get_val("MOVE")
    final_r = r if r else 4.21
    final_m = m if m else 105.0
    status = "🟢 Connected" if (r and m) else "🟡 Partial Connection (Cached)"
    return final_r, final_m / 10, final_m, now, status

m_rate, m_vol, m_move, up_time, status = fetch_data(target_key)

# --- 3. Sidebar: International Settings ---
with st.sidebar:
    st.subheader("🔍 System Diagnostics")
    st.caption(f"Status: {status}")
    st.caption(f"Last Update: {up_time}")
    st.divider()
    
    st.header("💵 Investment Settings")
    principal = st.number_input("Principal Amount (USD)", value=50000)
    init_rate = st.slider("Initial Rate (%)", 2.0, 6.0, m_rate) / 100
    vol = st.slider("Annual Volatility (%)", 5, 50, int(m_vol)) / 100
    
    st.header("🛡️ Issuer Credit Risk")
    issuer_rating = st.select_slider(
        "Issuer Credit Rating",
        options=["AAA (Prime)", "AA (High Quality)", "A (Upper Medium)", "BBB (Warning)", "BB (Speculative)"],
        value="A (Upper Medium)"
    )
    # Annualized Probability of Default (PD) mapping
    pd_map = {"AAA (Prime)": 0.02, "AA (High Quality)": 0.05, "A (Upper Medium)": 0.20, "BBB (Warning)": 0.50, "BB (Speculative)": 1.50}
    annual_pd = pd_map[issuer_rating] / 100

    st.header("📜 Product Terms (7Y)")
    accrual_barrier = st.slider("Accrual Barrier (%)", 3.5, 5.5, 4.3) / 100
    call_barrier = st.slider("Autocall Barrier (%)", 2.5, 4.0, 3.2) / 100

# --- 4. Monte Carlo Simulation Core ---
def run_sim():
    days, dt = 252 * 7, 1/252
    results = []
    sample_paths = []
    for i in range(500):
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = init_rate * np.exp(np.cumsum(vol * shocks - 0.5 * vol**2 * dt))
        coupons = 0.034 # Fixed for first 6 months
        call_day = days
        status_str = "Matured"
        for d in range(126, days):
            if (d-126) % 63 == 0 and path[d] <= call_barrier:
                status_str, call_day = "Autocalled", d
                break
            if path[d] <= accrual_barrier: coupons += (0.05 / 252)
        
        dur = (call_day + 1) / 252
        # Survival Probability Calculation
        survival_prob = (1 - annual_pd) ** dur
        
        results.append({
            'return': (coupons / dur) * 100,
            'usd': coupons * principal,
            'status': status_str,
            'dur': dur,
            'risk_adj_usd': coupons * principal * survival_prob
        })
        if i < 15: sample_paths.append(path[:call_day])
    return pd.DataFrame(results), sample_paths

df, paths = run_sim()

# --- 5. Main Dashboard ---
st.title("🏛️ Fed Rate Sentinel: Risk-Adjusted Portfolio")
st.info(f"📡 Market Live: 10Y Yield {m_rate:.2f}% | MOVE Index {m_move:.1f} | Rating: {issuer_rating}")

# Key Metrics
c1, c2, c3, c4 = st.columns(4)
c1.metric("Exp. Total Coupon", f"${df['usd'].mean():,.0f}")
c2.metric("Risk-Adjusted Gain", f"${df['risk_adj_usd'].mean():,.0f}", 
          delta=f"-${df['usd'].mean()-df['risk_adj_usd'].mean():,.0f} Risk Cost", delta_color="inverse")
c3.metric("Annualized Yield", f"{df['return'].mean():.2f}%")
c4.metric("Annual Default Risk", f"{annual_pd*100:.2f}%")

st.divider()

# Visualization
col_l, col_r = st.columns(2)
with col_l:
    st.subheader("💰 Nominal vs. Risk-Adjusted Coupon")
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(x=df['usd'], name='Nominal Coupon', marker_color='#3498DB', opacity=0.6))
    fig_hist.add_trace(go.Histogram(x=df['risk_adj_usd'], name='Risk-Adjusted', marker_color='#E74C3C', opacity=0.6))
    fig_hist.update_layout(barmode='overlay', xaxis_title="USD", yaxis_title="Frequency", height=400, legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01))
    st.plotly_chart(fig_hist, use_container_width=True)

with col_r:
    st.subheader("📈 Interest Rate Simulation Paths")
    fig_path = go.Figure()
    for p in paths: fig_path.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.3, showlegend=False))
    fig_path.add_hline(y=accrual_barrier, line_dash="dash", line_color="red", annotation_text="Accrual Barrier")
    fig_path.add_hline(y=call_barrier, line_dash="dash", line_color="green", annotation_text="Autocall Barrier")
    fig_path.update_layout(yaxis=dict(tickformat=".1%"), height=400, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_path, use_container_width=True)

if annual_pd > 0.005:
    st.warning(f"🚨 ALERT: High Issuer Credit Risk. Based on current rating, your expected gain has shrunk by approximately ${df['usd'].mean()-df['risk_adj_usd'].mean():,.0f} due to potential default costs.")
