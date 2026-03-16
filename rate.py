import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import pytz

# --- 1. 初始設定 ---
st.set_page_config(page_title="Rate Sentinel Pro: Multi-Benchmark", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

def get_final_key():
    try:
        raw_val = st.secrets["FRED_API_KEY"]
        return "".join(filter(str.isalnum, str(raw_val))).lower()
    except: return None

target_key = get_final_key()

@st.cache_data(ttl=600)
def fetch_market_data(api_key):
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

m_rate_live, m_move, up_time = fetch_market_data(target_key)

# --- 2. 側邊欄控制：加入彭博手動輸入 ---
with st.sidebar:
    st.header("📊 Benchmark Control")
    # 勾選此項即可手動輸入彭博看到的 3.78%
    use_manual = st.checkbox("Use Bloomberg Manual Input", value=True)
    if use_manual:
        manual_rate = st.number_input("10Y SOFR CMS (%)", value=3.78113, format="%.5f")
        current_benchmark = manual_rate
    else:
        current_benchmark = m_rate_live
    
    st.divider()
    st.header("🛡️ Issuer Credit Risk")
    issuer_rating = st.select_slider("Rating", options=["AAA", "AA", "A", "BBB", "BB"], value="A")
    pd_map = {"AAA": 0.02, "AA": 0.05, "A": 0.20, "BBB": 0.50, "BB": 1.50}
    annual_pd = pd_map[issuer_rating] / 100

    st.header("📜 Product Terms")
    accrual_barrier = st.slider("Accrual Barrier (%)", 3.5, 5.5, 4.3) / 100
    call_barrier = st.slider("Autocall Barrier (%)", 2.5, 4.0, 3.2) / 100
    vol = st.slider("Volatility (MOVE based)", 5, 50, int(m_move/10)) / 100

# --- 3. 模擬邏輯 ---
def run_sim(p_rate):
    days, dt, principal = 252 * 7, 1/252, 50000
    results = []
    for _ in range(500):
        path = (p_rate/100) * np.exp(np.cumsum(vol * np.random.normal(0, np.sqrt(dt), days) - 0.5 * vol**2 * dt))
        coupons = 0.034
        call_day = days
        for d in range(126, days):
            if (d-126) % 63 == 0 and path[d] <= call_barrier:
                call_day = d; break
            if path[d] <= accrual_barrier: coupons += (0.05 / 252)
        dur = (call_day + 1) / 252
        results.append({'ret': (coupons/dur)*100, 'usd': coupons*principal * (1-annual_pd)**dur})
    return pd.DataFrame(results)

res_df = run_sim(current_benchmark)

# --- 4. 主畫面：新增儀表板圖表 ---
st.title("🏛️ Fed Rate Sentinel: Benchmark Comparison")
st.success(f"Tracking Benchmark: **{current_benchmark:.5f}%** | Barrier: **{accrual_barrier*100:.2f}%**")

c1, c2, c3 = st.columns(3)
c1.metric("Distance to Barrier", f"{(accrual_barrier*100 - current_benchmark):.2f}%", help="Higher is safer")
c2.metric("Simulated Annual Yield", f"{res_df['ret'].mean():.2f}%")
c3.metric("Risk-Adj. Principal Value", f"${res_df['usd'].mean():,.0f}")

# 視覺化：計息安全區間儀表板
fig = go.Figure(go.Indicator(
    mode = "gauge+number",
    value = current_benchmark,
    title = {'text': "Current Rate vs. Accrual Barrier"},
    gauge = {
        'axis': {'range': [2.5, 5.0]},
        'bar': {'color': "#2980B9"},
        'steps' : [
            {'range': [0, call_barrier*100], 'color': "#D5F5E3"},      # 贖回區
            {'range': [call_barrier*100, accrual_barrier*100], 'color': "#EBEDEF"}, # 計息區
            {'range': [accrual_barrier*100, 5.0], 'color': "#FADBD8"}], # 零息區
        'threshold': {'line': {'color': "red", 'width': 4}, 'thickness': 0.75, 'value': accrual_barrier*100}
    }
))
st.plotly_chart(fig, use_container_width=True)
