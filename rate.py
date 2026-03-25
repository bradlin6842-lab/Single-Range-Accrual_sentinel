import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import pytz

# --- 1. Initial Configuration ---
st.set_page_config(page_title="Rate Sentinel Pro: Universal Analyzer", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

def get_final_key():
    try:
        raw_val = st.secrets["FRED_API_KEY"]
        return "".join(filter(str.isalnum, str(raw_val))).lower()
    except: return None

target_key = get_final_key()

@st.cache_data(ttl=600)
def fetch_live_data(api_key):
    sync_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
    base_url = "https://api.stlouisfed.org/fred/series/observations"
    def get_fred_info(sid):
        try:
            url = f"{base_url}?series_id={sid}&api_key={api_key}&file_type=json&sort_order=desc&limit=1"
            res = requests.get(url, timeout=10).json()
            val = float(res['observations'][0]['value'])
            obs_date = res['observations'][0]['date']
            return val, obs_date
        except: return None, None
    t_rate, t_date = get_fred_info("DGS10")
    m_move, _ = get_fred_info("MOVE")
    return t_rate if t_rate else 4.28, t_date, m_move if m_move else 105.0, sync_time

# 📡 Data from Fed API
fred_rate, fred_obs_date, move_vol_live, app_sync_time = fetch_live_data(target_key)

# --- 2. Sidebar: Universal Controls ---
with st.sidebar:
    st.header("⏳ Investment Term & Structure")
    # 1. 可調年期 (1-15年)
    total_years = st.slider("Total Tenor (Years)", 1, 15, 7, help="Adjust the total maturity of the bond.")
    # 2. 提前贖回開關
    enable_autocall = st.toggle("Enable Autocall Feature", value=True, help="Toggle whether the bank can redeem the bond early.")
    
    st.divider()
    st.header("💰 Portfolio & Coupons")
    principal = st.number_input("Principal Amount (USD)", value=50000, step=5000)
    fixed_coupon_rate = st.number_input("Fixed Rate %", value=6.8, step=0.1) / 100
    floating_coupon_rate = st.number_input("Floating Rate %", value=5.0, step=0.1) / 100
    fixed_months = st.selectbox("Fixed Period (Months)", options=[6, 12], index=0)
    fixed_days = 126 if fixed_months == 6 else 252
    
    st.divider()
    st.header("🔌 Market Data")
    st.info(f"10Y Treasury: {fred_rate:.2f}% (Obs: {fred_obs_date})")
    vol_multiplier = st.slider("Volatility Stress (x)", 0.5, 3.0, 1.0)
    sim_vol = (move_vol_live / 1000) * vol_multiplier
    
    st.header("🖥️ Bloomberg Input")
    sofr_rate = st.number_input("10Y SOFR CMS (%)", value=3.9013, format="%.5f")
    
    st.divider()
    st.header("🛡️ Credit Risk")
    # 更精細的評分系統
    issuer_rating = st.select_slider("Rating", options=["AAA", "AA", "A", "BBB", "BB", "B"], value="A")
    pd_map = {"AAA": 0.0001, "AA": 0.0003, "A": 0.0007, "BBB": 0.002, "BB": 0.01, "B": 0.04}
    annual_pd = pd_map[issuer_rating]
    
    accrual_barrier = st.slider("Accrual Barrier (%)", 3.5, 5.5, 4.3) / 100
    call_barrier = st.slider("Autocall Barrier (%)", 2.5, 4.0, 3.2) / 100 if enable_autocall else 0.0

# --- 3. Advanced Simulation Engine ---
def run_comparison_sim(rates_dict, p_val, volatility, t_years):
    days = 252 * t_years
    dt = 1/252
    all_results, all_paths = {}, {}
    for label, start_rate in rates_dict.items():
        results, paths = [], []
        for i in range(400):
            shocks = np.random.normal(0, np.sqrt(dt), days)
            path = (start_rate/100) * np.exp(np.cumsum(volatility * shocks - 0.5 * volatility**2 * dt))
            
            coupons = fixed_coupon_rate * (fixed_months / 12)
            call_day = days
            for d in range(fixed_days, days):
                # 只有開關開啟時才判斷 Autocall
                if enable_autocall and (d-fixed_days) % 63 == 0 and path[d] <= call_barrier:
                    call_day = d; break
                if path[d] <= accrual_barrier: coupons += (floating_coupon_rate / 252)
            
            dur = (call_day + 1) / 252
            survival = (1 - annual_pd) ** dur
            results.append({'wealth': (p_val + (coupons * p_val)) * survival, 
                            'yield': (coupons/dur)*100, 'dur': dur})
            if i < 10: paths.append(path[:call_day])
        all_results[label] = pd.DataFrame(results)
        all_paths[label] = paths
    return all_results, all_paths

scenarios = {"Treasury (FRED)": fred_rate, "SOFR CMS (Bloomberg)": sofr_rate}
sim_data, sim_paths = run_comparison_sim(scenarios, principal, sim_vol, total_years)

# --- 4. Main Dashboard ---
st.title("🏛️ Sentinel: Multi-Asset Structure Analyzer")
status_txt = f"[{total_years}Y] Fixed {fixed_months}M @ {fixed_coupon_rate*100:.1f}% | Autocall: {'ON' if enable_autocall else 'OFF'}"
st.warning(status_txt)

col1, col2 = st.columns(2)
colors = {"Treasury (FRED)": "#E74C3C", "SOFR CMS (Bloomberg)": "#2ECC71"}
for i, (name, data) in enumerate(sim_data.items()):
    with [col1, col2][i]:
        st.markdown(f"### <span style='color:{colors[name]}'>{name}</span>", unsafe_allow_html=True)
        m_r1, m_r2 = st.columns(2)
        m_r1.metric("Exp. Wealth", f"${data['wealth'].mean():,.0f}")
        m_r2.metric("Annual Yield", f"{data['yield'].mean():.2f}%")
        m_r3, m_r4 = st.columns(2)
        m_r3.metric("Avg. Hold Time", f"{data['dur'].mean():.1f}Y")
        m_r4.metric("Barrier Dist.", f"{(accrual_barrier*100 - scenarios[name]):.2f}%")

st.divider()

col_l, col_r = st.columns(2)
with col_l:
    st.subheader("💰 Asset Projection (Maturity)")
    fig_comp = go.Figure()
    for name, data in sim_data.items():
        fig_comp.add_trace(go.Violin(x=data['wealth'], name=name, line_color=colors[name], box_visible=True, meanline_visible=True))
    fig_comp.update_layout(xaxis_title="USD", height=450, xaxis=dict(range=[principal * 0.85, principal * 1.6]))
    st.plotly_chart(fig_comp, use_container_width=True)

with col_r:
    st.subheader("🎯 Accrual Safety Gauge")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = sofr_rate,
        gauge = {
            'axis': {'range': [2.5, 5.0]},
            'steps' : [{'range': [0, call_barrier*100 if enable_autocall else 2.5], 'color': "#D5F5E3"}, 
                       {'range': [call_barrier*100 if enable_autocall else 2.5, accrual_barrier*100], 'color': "#EBEDEF"}, 
                       {'range': [accrual_barrier*100, 5.0], 'color': "#FADBD8"}],
            'threshold': {'line': {'color': "red", 'width': 4}, 'value': accrual_barrier*100}
        }
    ))
    fig_gauge.update_layout(height=400)
    st.plotly_chart(fig_gauge, use_container_width=True)

st.subheader("📈 Interest Rate Simulation Paths")
fig_path = go.Figure()
for name, paths in sim_paths.items():
    for p in paths: fig_path.add_trace(go.Scatter(y=p, mode='lines', line=dict(color=colors[name], width=1), opacity=0.3, showlegend=False))
fig_path.add_hline(y=accrual_barrier, line_dash="dash", line_color="#FF0000", line_width=3, annotation_text="Barrier")
if enable_autocall:
    fig_path.add_hline(y=call_barrier, line_dash="dash", line_color="#00FFFF", line_width=3, annotation_text="Autocall")
fig_path.update_layout(yaxis=dict(tickformat=".1%", title="Rate Level"), height=500)
st.plotly_chart(fig_path, use_container_width=True)
