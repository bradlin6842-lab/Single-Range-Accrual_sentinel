import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from fredapi import Fred
from datetime import datetime
import pytz

# --- 1. 初始設定與連線 ---
st.set_page_config(page_title="利率哨兵：數據透明版", layout="wide")

# 設定台北時區方便查看更新時間
tw_tz = pytz.timezone('Asia/Taipei')

try:
raw_key = st.secrets["FRED_API_KEY"]
FRED_API_KEY = raw_key.strip()  # 加入清洗，刪除隱形換行
fred = Fred(api_key=FRED_API_KEY)

except Exception as e:
    st.error("❌ Secrets 讀取失敗，請檢查 FRED_API_KEY 設定。")
    st.stop()

@st.cache_data(ttl=600) # 縮短緩存時間至 10 分鐘，方便測試更新
def get_market_data():
    now = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
    try:
        # 抓取數據
        rate_series = fred.get_series('DGS10')
        move_series = fred.get_series('MOVE')
        
        latest_rate = float(rate_series.iloc[-1])
        latest_move = float(move_series.iloc[-1])
        
        # 檢查是否拿到有效值（非空值）
        if np.isnan(latest_rate) or np.isnan(latest_move):
            raise ValueError("FRED 回傳空數據")
            
        return latest_rate, latest_move / 10, latest_move, now, "🟢 即時連線"
    except Exception as e:
        # 抓取失敗時回傳備援值，並標註狀態
        return 3.85, 15.0, 100.0, now, f"🔴 備援模式 (錯誤: {str(e)[:20]}...)"

# 取得數據與狀態
m_rate, m_vol, m_move, update_time, status_tag = get_market_data()

# --- 2. 介面呈現 ---
st.title("🏛️ 聯準會全自動哨兵 (透明診斷版)")

# 顯示數據狀態與更新時間
st.markdown(f"### 狀態：{status_tag}")
st.caption(f"📅 最後檢查時間 (台北)：{update_time}")

if "🔴" in status_tag:
    st.warning("⚠️ 目前正處於備援模式，顯示的是預設數據 (3.85%)。請確認 FRED API Key 是否正確或 FRED 網站是否維護中。")

# --- 3. 指標與模擬器 (其餘邏輯相同) ---
st.divider()
st.info(f"📡 目前 10Y 參考利率：{m_rate:.2f}% | MOVE 波動指數：{m_move:.1f}")

with st.sidebar:
    st.header("💵 投資金額")
    principal = st.number_input("本金 (USD)", value=50000, step=1000)
    
    st.header("📈 市場參數")
    init_rate = st.slider("起始模擬利率 (%)", 2.0, 6.0, m_rate) / 100
    vol = st.slider("預期年化波動率 (%)", 5, 50, int(m_vol)) / 100
    
    st.header("📜 產品條件")
    fixed_coupon = st.slider("前半年固定年息 (%)", 0.0, 15.0, 6.8) / 100
    float_coupon = st.slider("半年後最高年息 (%)", 0.0, 10.0, 5.0) / 100
    accrual_barrier = st.slider("計息區間上限 (%)", 2.0, 6.0, 4.3) / 100
    call_barrier = st.slider("Autocall 門檻 (%)", 2.0, 6.0, 3.2) / 100
    sim_count = st.select_slider("模擬次數", options=[100, 500, 1000], value=500)

# (以下模擬運算與圖表部分維持原樣...)
def run_simulation():
    years, days, dt = 7, 252 * 7, 1/252
    results, sample_paths = [], []
    for _ in range(sim_count):
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = init_rate * np.exp(np.cumsum(vol * shocks - 0.5 * vol**2 * dt))
        coupons_pct, call_day, status = 0, days, "到期"
        for d in range(days):
            if d < 126: coupons_pct += (fixed_coupon / 252)
            else:
                if (d - 126) % 63 == 0 and path[d] <= call_barrier:
                    status, call_day = "提前贖回", d
                    break
                if path[d] <= accrual_barrier: coupons_pct += (float_coupon / 252)
        duration = (call_day + 1) / 252
        results.append({'return': (coupons_pct / duration) * 100, 'usd_gain': coupons_pct * principal, 'status': status, 'duration': duration})
        if len(sample_paths) < 15: sample_paths.append(path[:call_day])
    return pd.DataFrame(results), sample_paths

df, paths = run_simulation()

c1, c2, c3, c4 = st.columns(4)
c1.metric("預期平均利息", f"${df['usd_gain'].mean():,.0f}")
c2.metric("平均年化收益", f"{df['return'].mean():.2f}%")
c3.metric("提前贖回機率", f"{(df['status']=='提前贖回').mean()*100:.1f}%")
c4.metric("平均持有年限", f"{df['duration'].mean():.1f} 年")

st.divider()
col_l, col_r = st.columns(2)
with col_l:
    st.subheader("💰 收益分佈預測")
    fig_hist = go.Figure(data=[go.Histogram(x=df['usd_gain'], marker_color='#2980B9', nbinsx=20)])
    st.plotly_chart(fig_hist, use_container_width=True)
with col_r:
    st.subheader("📈 利率監控圖")
    fig_path = go.Figure()
    for p in paths: fig_path.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.3, showlegend=False))
    fig_path.add_hline(y=accrual_barrier, line_dash="dash", line_color="red", annotation_text="上限")
    fig_path.add_hline(y=call_barrier, line_dash="dash", line_color="green", annotation_text="Autocall")
    fig_path.update_layout(yaxis=dict(tickformat=".1%"), margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_path, use_container_width=True)
