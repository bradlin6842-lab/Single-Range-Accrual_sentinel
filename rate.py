import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import pytz

# --- 1. 初始設定與時區 ---
st.set_page_config(page_title="Rate Sentinel Pro: Analytics Edition", layout="wide")
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

# 📡 抓取 FRED API 即時數據
fred_rate, fred_obs_date, move_vol_live, app_sync_time = fetch_live_data(target_key)

# --- 2. 側邊欄：控制中心 ---
with st.sidebar:
    st.header("💰 Portfolio Input")
    principal = st.number_input("Principal Amount (USD)", value=50000, step=5000)
    
    st.divider()
    st.header("📜 Coupon Structure")
    # 根據要求：首半年 9.1%，續期 6.0%
    fixed_coupon_rate = st.number_input("Fixed Rate % (Initial)", value=9.1, step=0.1) / 100
    floating_coupon_rate = st.number_input("Floating Rate % (Post-Fixed)", value=6.0, step=0.1) / 100
    fixed_months = st.selectbox("Fixed Period (Months)", options=[6, 12], index=0)
    fixed_days = 126 if fixed_months == 6 else 252
    
    st.divider()
    st.header("⏳ Tenor & Features")
    total_years = st.slider("Total Tenor (Years)", 1, 15, 10)
    enable_autocall = st.toggle("Enable Autocall Feature", value=True)
    
    st.divider()
    st.header("🔌 Live Market Data")
    st.info(f"10Y Treasury: {fred_rate:.2f}%")
    st.caption(f"FRED Latest Obs: {fred_obs_date}")
    st.info(f"LIVE MOVE Index: {move_vol_live:.1f}")
    vol_multiplier = st.slider("Volatility Stress (x)", 0.5, 3.0, 1.0)
    sim_vol = (move_vol_live / 1000) * vol_multiplier
    
    st.header("🖥️ Bloomberg Input")
    # 根據要求：預設改為 4.00%
    sofr_rate = st.number_input("10Y SOFR CMS (%)", value=4.00, format="%.5f")
    
    st.divider()
    st.header("🛡️ Risk Terms")
    issuer_rating = st.select_slider("Rating", options=["AAA", "AA", "A", "BBB", "BB", "B"], value="A")
    pd_map = {"AAA": 0.0001, "AA": 0.0003, "A": 0.0007, "BBB": 0.002, "BB": 0.01, "B": 0.04}
    annual_pd = pd_map[issuer_rating]
    
    # 根據要求：門檻 4.4%
    accrual_barrier = st.slider("Accrual Barrier (%)", 3.5, 5.5, 4.40) / 100
    call_barrier = st.slider("Autocall Barrier (%)", 2.5, 4.0, 3.20) / 100 if enable_autocall else 0.0
    st.caption(f"App Sync: {app_sync_time}")

# --- 3. 模擬引擎 ---
def run_comparison_sim(rates_dict, p_val, volatility, t_years):
    days = 252 * t_years
    dt = 1/252
    all_results, all_paths = {}, {}
    for label, start_rate in rates_dict.items():
        results, paths = [], []
        for i in range(400):
            shocks = np.random.normal(0, np.sqrt(dt), days)
            path = (start_rate/100) * np.exp(np.cumsum(volatility * shocks - 0.5 * volatility**2 * dt))
            
            initial_coupons = fixed_coupon_rate * (fixed_months / 12)
            coupons = initial_coupons
            call_day = days
            for d in range(fixed_days, days):
                if enable_autocall and (d-fixed_days) % 63 == 0 and path[d] <= call_barrier:
                    call_day = d; break
                if path[d] <= accrual_barrier: 
                    coupons += (floating_coupon_rate / 252)
            
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

# --- 4. 主畫面佈局 ---
st.title("🏛️ Sentinel Pro: Analytics & Stress Test")
st.warning(f"Strategy: **6M Fixed @ {fixed_coupon_rate*100:.1f}%** | Barrier: **CMS <= {accrual_barrier*100:.2f}%**")

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

# 圖表區塊
col_l, col_r = st.columns(2)

with col_l:
    # 替換小提琴圖為「直方圖」
    st.subheader("📊 Probability Distribution (Histogram)")
    fig_hist = go.Figure()
    for name, data in sim_data.items():
        fig_hist.add_trace(go.Histogram(
            x=data['wealth'], name=name, 
            marker_color=colors[name], opacity=0.6,
            nbinsx=40
        ))
    fig_hist.update_layout(
        barmode='overlay', 
        xaxis_title="Wealth at Maturity (USD)",
        yaxis_title="Frequency",
        height=450,
        xaxis=dict(range=[principal * 0.9, principal * 1.8], tickformat="$,.0f"),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
    )
    st.plotly_chart(fig_hist, use_container_width=True)

with col_r:
    st.subheader("🎯 Real-Time CMS Monitor")
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

st.subheader("📈 Monte Carlo Paths (Barrier: 4.4%)")
fig_path = go.Figure()
for name, paths in sim_paths.items():
    for p in paths: fig_path.add_trace(go.Scatter(y=p, mode='lines', line=dict(color=colors[name], width=1), opacity=0.3, showlegend=False))
# 畫出清晰的 Barrier
fig_path.add_hline(y=accrual_barrier, line_dash="dash", line_color="#FF0000", line_width=3, annotation_text="Barrier 4.40%")
if enable_autocall:
    fig_path.add_hline(y=call_barrier, line_dash="dash", line_color="#00FFFF", line_width=3, annotation_text="Autocall")
fig_path.update_layout(yaxis=dict(tickformat=".1%", title="Rate Level"), height=500)
st.plotly_chart(fig_path, use_container_width=True)
