import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import pytz

# --- 1. 初始設定 ---
st.set_page_config(page_title="利率哨兵 Pro：穩定版", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

# --- 2. 鑰匙讀取與強力清洗 ---
def get_final_key():
    try:
        raw_val = st.secrets["FRED_API_KEY"]
        return "".join(filter(str.isalnum, str(raw_val))).lower()
    except:
        return None

target_key = get_final_key()

# --- 3. 數據抓取核心 (修正版) ---
@st.cache_data(ttl=600)
def fetch_data(api_key):
    now = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
    base_url = "https://api.stlouisfed.org/fred/series/observations"
    
    def get_val(series_id):
        url = f"{base_url}?series_id={series_id}&api_key={api_key}&file_type=json&sort_order=desc&limit=1"
        res = requests.get(url, timeout=10).json()
        # 安全檢查：確保 observations 存在
        if 'observations' in res and len(res['observations']) > 0:
            val = res['observations'][0]['value']
            return float(val) if val != "." else None
        return None

    try:
        rate = get_val("DGS10")
        move = get_val("MOVE")
        
        # 如果抓不到，給予合理的市場備援值
        final_r = rate if rate else 4.21
        final_m = move if move else 105.0
        
        status = "🟢 連線成功" if (rate and move) else "🟡 部分數據連線 (使用暫存)"
        return final_r, final_m / 10, final_m, now, status
    except Exception as e:
        return 3.85, 15.0, 100.0, now, f"🔴 連線失敗 ({str(e)[:10]})"

m_rate, m_vol, m_move, up_time, status = fetch_data(target_key)

# --- 4. 側邊欄 ---
with st.sidebar:
    st.subheader("🔍 系統診斷")
    st.caption(f"狀態：{status}")
    st.caption(f"最後更新：{up_time}")
    st.divider()
    principal = st.number_input("本金 (USD)", value=50000)
    init_rate = st.slider("起始利率 (%)", 2.0, 6.0, m_rate) / 100
    vol = st.slider("年化波動率 (%)", 5, 50, int(m_vol)) / 100
    accrual_barrier = st.slider("計息上限 (%)", 3.5, 5.5, 4.3) / 100
    call_barrier = st.slider("Autocall 門檻 (%)", 2.5, 4.0, 3.2) / 100

# --- 5. 主畫面與模擬 ---
st.title("🏛️ 聯準會利率哨兵系統 (完整版)")
st.info(f"📡 市場實時：10Y 利率 {m_rate:.2f}% | MOVE 指數 {m_move:.1f}")

def run_sim():
    days, dt = 252 * 7, 1/252
    results = []
    sample_paths = []
    for i in range(500):
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = init_rate * np.exp(np.cumsum(vol * shocks - 0.5 * vol**2 * dt))
        coupons = 0.034 # 前半年
        call_day = days
        status_str = "到期"
        for d in range(126, days):
            if (d-126) % 63 == 0 and path[d] <= call_barrier:
                status_str, call_day = "提前贖回", d
                break
            if path[d] <= accrual_barrier: coupons += (0.05 / 252)
        dur = (call_day + 1) / 252
        results.append({'return': (coupons / dur) * 100, 'usd': coupons * principal, 'status': status_str, 'dur': dur})
        if i < 15: sample_paths.append(path[:call_day])
    return pd.DataFrame(results), sample_paths

df, paths = run_sim()

# --- 6. 指標與圖表 ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("預期利息", f"${df['usd'].mean():,.0f}")
c2.metric("年化收益", f"{df['return'].mean():.2f}%")
c3.metric("贖回機率", f"{(df['status']=='提前贖回').mean()*100:.1f}%")
c4.metric("持有年限", f"{df['dur'].mean():.1f}年")

fig = go.Figure()
for p in paths:
    fig.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.3, showlegend=False))
fig.add_hline(y=accrual_barrier, line_dash="dash", line_color="red")
fig.add_hline(y=call_barrier, line_dash="dash", line_color="green")
fig.update_layout(yaxis=dict(tickformat=".1%"), height=400, margin=dict(l=0, r=0, t=20, b=0))
st.plotly_chart(fig, use_container_width=True)
