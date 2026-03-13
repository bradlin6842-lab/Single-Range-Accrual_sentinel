import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from fredapi import Fred
from datetime import datetime
import pytz

# --- 1. 初始設定與連線 ---
st.set_page_config(page_title="利率哨兵 Pro", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

def get_clean_key():
    try:
        # 強力清洗：刪除所有引號與空格
        raw_key = str(st.secrets["FRED_API_KEY"])
        return raw_key.replace('"', '').replace("'", "").strip()
    except:
        return None

target_key = get_clean_key()

if not target_key:
    st.error("❌ 找不到 FRED_API_KEY，請檢查 Streamlit Secrets 設定。")
    st.stop()

@st.cache_data(ttl=600)
def fetch_data():
    update_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
    try:
        fred = Fred(api_key=target_key)
        # 抓取 10Y 利率與 MOVE 指數
        r_series = fred.get_series('DGS10')
        m_series = fred.get_series('MOVE')
        
        latest_r = float(r_series.iloc[-1])
        latest_m = float(m_series.iloc[-1])
        
        if np.isnan(latest_r) or np.isnan(latest_m):
            raise ValueError("數據為空")
            
        return latest_r, latest_m / 10, latest_m, update_time, "🟢 連線成功"
    except Exception as e:
        return 3.85, 15.0, 100.0, update_time, f"🔴 連線失敗 ({str(e)[:15]})"

# 執行抓取
m_rate, m_vol, m_move, up_time, status = fetch_data()

# --- 2. 介面呈現 ---
st.title("🏛️ 聯準會利率哨兵系統")
st.markdown(f"**數據狀態：{status}** | 最後更新：`{up_time}`")

if "🔴" in status:
    st.warning("⚠️ 目前正使用備援數據。請確認 FRED API 是否正常或 Key 是否正確。")
else:
    st.success(f"📡 已同步最新數據：10Y 利率 {m_rate:.2f}% | MOVE 指數 {m_move:.1f}")

# --- 3. 側邊欄控制 ---
with st.sidebar:
    st.header("💵 投資設定")
    principal = st.number_input("本金 (USD)", value=50000, step=1000)
    init_rate = st.slider("起始模擬利率 (%)", 2.0, 6.0, m_rate) / 100
    vol = st.slider("預期年化波動率 (%)", 5, 50, int(m_vol)) / 100
    st.divider()
    st.header("📜 產品條件")
    accrual_barrier = st.slider("計息區間上限 (%)", 2.0, 6.0, 4.3) / 100
    call_barrier = st.slider("Autocall 門檻 (%)", 2.0, 6.0, 3.2) / 100

# --- 4. 蒙地卡羅模擬 ---
def run_sim():
    days = 252 * 7
    dt = 1/252
    results = []
    sample_paths = []
    for i in range(500):
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = init_rate * np.exp(np.cumsum(vol * shocks - 0.5 * vol**2 * dt))
        # 簡化版邏輯：前半年固定領，後半年區間領，季觀察 Autocall
        coupons = 0.034 # 前半年固定 6.8%/2
        call_day = days
        status_str = "到期"
        for d in range(126, days):
            if (d-126) % 63 == 0 and path[d] <= call_barrier:
                status_str, call_day = "提前贖回", d
                break
            if path[d] <= accrual_barrier:
                coupons += (0.05 / 252)
        duration = (call_day + 1) / 252
        results.append({'return': (coupons / duration) * 100, 'usd': coupons * principal, 'status': status_str, 'dur': duration})
        if i < 15: sample_paths.append(path[:call_day])
    return pd.DataFrame(results), sample_paths

df, paths = run_sim()

# --- 5. 視覺化指標 ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("預期利息", f"${df['usd'].mean():,.0f}")
c2.metric("年化收益率", f"{df['return'].mean():.2f}%")
c3.metric("提前贖回率", f"{(df['status']=='提前贖回').mean()*100:.1f}%")
c4.metric("持有年限", f"{df['dur'].mean():.1f} 年")

# 繪製路徑圖
fig = go.Figure()
for p in paths:
    fig.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.3, showlegend=False))
fig.add_hline(y=accrual_barrier, line_dash="dash", line_color="red", annotation_text="計息上限")
fig.add_hline(y=call_barrier, line_dash="dash", line_color="green", annotation_text="贖回門檻")
fig.update_layout(yaxis=dict(tickformat=".1%"), height=400, margin=dict(l=0, r=0, t=20, b=0))
st.plotly_chart(fig, use_container_width=True)
