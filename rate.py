import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import pytz

# --- 1. 初始設定 ---
st.set_page_config(page_title="Rate Sentinel Pro: CDF Analytics", layout="wide")
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
            return float(res['observations'][0]['value']), res['observations'][0]['date']
        except: return None, None
    t_rate, t_date = get_fred_info("DGS10")
    m_move, _ = get_fred_info("MOVE")
    return t_rate if t_rate else 4.25, t_date, m_move if m_move else 105.0, sync_time

fred_rate, fred_obs_date, move_vol_live, app_sync_time = fetch_live_data(target_key)

# --- 2. Sidebar ---
with st.sidebar:
    st.header("💰 Portfolio Input")
    principal = st.number_input("Principal Amount (USD)", value=50000, step=5000)
    
    st.divider()
    st.header("📜 Coupon Structure")
    fixed_coupon_rate = st.number_input("Fixed Rate % (Initial)", value=9.1, step=0.1) / 100
    floating_coupon_rate = st.number_input("Floating Rate % (Post-Fixed)", value=6.0, step=0.1) / 100
    fixed_months = st.selectbox("Fixed Period (Months)", options=[6, 12], index=0)
    fixed_days = 126 if fixed_months == 6 else 252
    
    st.divider()
    st.header("⏳ Tenor & Features")
    total_years = st.slider("Total Tenor (Years)", 1, 15, 10)
    enable_autocall = st.toggle("Enable Autocall", value=True)
    
    st.divider()
    st.header("🔌 Market Data")
    st.info(f"10Y Treasury: {fred_rate:.2f}%")
    vol_multiplier = st.slider("Volatility Stress (x)", 0.5, 3.0, 1.0)
    sim_vol = (move_vol_live / 1000) * vol_multiplier
    
    st.header("🖥️ Bloomberg Input")
    sofr_rate = st.number_input("10Y SOFR CMS (%)", value=4.00, format="%.5f")
    
    st.divider()
    issuer_rating = st.select_slider("Rating", options=["AAA", "AA", "A", "BBB", "BB", "B"], value="A")
    pd_map = {"AAA": 0.0001, "AA": 0.0003, "A": 0.0007, "BBB": 0.002, "BB": 0.01, "B": 0.04}
    annual_pd = pd_map[issuer_rating]
    accrual_barrier = st.slider("Accrual Barrier (%)", 3.5, 5.5, 4.40) / 100
    call_barrier = st.slider("Autocall Barrier (%)", 2.5, 4.0, 3.20) / 100 if enable_autocall else 0.0

# --- 3. 模擬引擎 ---
def run_sim(rates_dict, p_val, volatility, t_years):
    days = 252 * t_years
    dt = 1/252
    all_results, all_paths = {}, {}
    for label, start_rate in rates_dict.items():
        results, paths = [], []
        for i in range(500): # 增加樣本數使 CDF 更平滑
            shocks = np.random.normal(0, np.sqrt(dt), days)
            path = (start_rate/100) * np.exp(np.cumsum(volatility * shocks - 0.5 * volatility**2 * dt))
            coupons = fixed_coupon_rate * (fixed_months / 12)
            call_day = days
            for d in range(fixed_days, days):
                if enable_autocall and (d-fixed_days) % 63 == 0 and path[d] <= call_barrier:
                    call_day = d; break
                if path[d] <= accrual_barrier: coupons += (floating_coupon_rate / 252)
            dur = (call_day + 1) / 252
            survival = (1 - annual_pd) ** dur
            results.append({'wealth': (p_val + (coupons * p_val)) * survival, 'yield': (coupons/dur)*100})
            if i < 10: paths.append(path[:call_day])
        all_results[label] = pd.DataFrame(results)
        all_paths[label] = paths
    return all_results, all_paths

scenarios = {"Treasury (FRED)": fred_rate, "SOFR CMS (Bloomberg)": sofr_rate}
sim_data, sim_paths = run_sim(scenarios, principal, sim_vol, total_years)

# --- 4. 主畫面佈局 ---
st.title("🏛️ Sentinel Pro: Strategic Wealth Analyzer")

# Top Metrics
col_m1, col_m2 = st.columns(2)
colors = {"Treasury (FRED)": "#E74C3C", "SOFR CMS (Bloomberg)": "#2ECC71"}
for i, (name, data) in enumerate(sim_data.items()):
    with [col_m1, col_m2][i]:
        st.markdown(f"### <span style='color:{colors[name]}'>{name}</span>", unsafe_allow_html=True)
        st.metric("Expected Final Wealth", f"${data['wealth'].mean():,.0f}")
        st.metric("Distance to Barrier", f"{(accrual_barrier*100 - scenarios[name]):.2f}%")

st.divider()

col_l, col_r = st.columns(2)

with col_l:
    st.subheader("📈 Win-Rate Curve (CDF Analysis)")
    fig_cdf = go.Figure()
    
    for name, data in sim_data.items():
        # 計算累積分佈
        df_sorted = data['wealth'].sort_values()
        y_vals = np.arange(1, len(df_sorted) + 1) / len(df_sorted)
        
        fig_cdf.add_trace(go.Scatter(
            x=df_sorted, y=y_vals,
            name=name, mode='lines',
            line=dict(color=colors[name], width=3),
            hovertemplate=f"Scenario: {name}<br>Wealth >= %{{x:$,.0f}}<br>Probability: %{{y:.1%}}"
        ))
    
    fig_cdf.update_layout(
        xaxis_title="Final Wealth at Maturity (USD)",
        yaxis_title="Cumulative Probability",
        yaxis=dict(tickformat=".0%"),
        xaxis=dict(range=[principal * 0.95, principal * 1.7], tickformat="$,.0f"),
        height=450,
        legend=dict(yanchor="bottom", y=0.01, xanchor="right", x=0.99),
        hovermode="x unified"
    )
    st.plotly_chart(fig_cdf, use_container_width=True)
    st.caption("此圖顯示累積機率。曲線越往右方移動且越陡峭，代表在該財富水準下的獲勝勝率越高。")

with col_r:
    st.subheader("🎯 Real-Time Accrual Monitor")
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

# 關鍵百分位數分析表
st.subheader("📋 Risk & Probability Analysis Table")
stats_data = []
for name, data in sim_data.items():
    stats_data.append({
        "Scenario": name,
        "Min (Worst Case)": f"${data['wealth'].min():,.0f}",
        "25th Percentile": f"${data['wealth'].quantile(0.25):,.0f}",
        "Median (50th)": f"${data['wealth'].quantile(0.50):,.0f}",
        "75th Percentile": f"${data['wealth'].quantile(0.75):,.0f}",
        "Max (Best Case)": f"${data['wealth'].max():,.0f}",
        "Prob. Above Principal": f"{(data['wealth'] > principal).mean():.1%}"
    })
st.table(pd.DataFrame(stats_data))
