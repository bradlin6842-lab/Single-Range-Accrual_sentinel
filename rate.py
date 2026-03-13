import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import pytz

# --- 1. 初始設定 ---
st.set_page_config(page_title="利率哨兵 Pro：完整版", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

# --- 2. 數據清洗與抓取邏輯 (剛才成功的版本) ---
def get_final_key():
    try:
        raw_val = st.secrets["FRED_API_KEY"]
        # 強力粉碎雜質：只留字母數字並轉小寫
        return "".join(filter(str.isalnum, str(raw_val))).lower()
    except:
        return None

target_key = get_final_key()

@st.cache_data(ttl=600)
def fetch_market_data(api_key):
    now = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
    try:
        # 抓取 10Y 利率 (DGS10)
        r_url = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={api_key}&file_type=json&sort_order=desc&limit=1"
        r_res = requests.get(r_url, timeout=10).json()
        latest_r = float(r_res['observations'][0]['value'])
        
        # 抓取 MOVE 指數
        m_url = f"https://api.stlouisfed.org/fred/series/observations?series_id=MOVE&api_key={api_key}&file_type=json&sort_order=desc&limit=1"
        m_res = requests.get(m_url, timeout=10).json()
        latest_m = float(m_res['observations'][0]['value'])
        
        return latest_r, latest_m / 10, latest_m, now, "🟢 連線成功"
    except Exception as e:
        # 失敗時回傳預設值
        return 3.85, 15.0, 100.0, now, f"🔴 連線失敗 ({str(e)[:10]})"

m_rate, m_vol, m_move, up_time, status = fetch_market_data(target_key)

# --- 3. 側邊欄診斷與控制 ---
with st.sidebar:
    st.subheader("🔍 系統診斷")
    st.caption(f"數據狀態：{status}")
    st.caption(f"最後更新：{up_time}")
    st.divider()
    
    st.header("💵 投資設定")
    principal = st.number_input("本金 (USD)", value=50000, step=1000)
    
    st.header("📈 市場模擬參數")
    init_rate = st.slider("起始利率 (%)", 2.0, 6.0, m_rate) / 100
    vol = st.slider("年化波動率 (%)", 5, 50, int(m_vol)) / 100
    
    st.header("📜 產品條件 (7Y)")
    fixed_coupon = 0.068  # 前半年固定 6.8%
    float_coupon = 0.050  # 後續最高 5.0%
    accrual_barrier = st.slider("計息上限 (%)", 3.5, 5.5, 4.3) / 100
    call_barrier = st.slider("Autocall 門檻 (%)", 2.5, 4.0, 3.2) / 100
    st.divider()
    sim_count = st.select_slider("模擬精確度", options=[100, 500, 1000], value=500)

# --- 4. 主畫面標題 ---
st.title("🏛️ 聯準會利率哨兵系統 (完整模擬版)")
st.info(f"📡 已同步最新市場數據：10Y 利率 **{m_rate:.2f}%** | MOVE 指數 **{m_move:.1f}**")

# --- 5. 蒙地卡羅模擬核心 ---
def run_simulation():
    years = 7
    days = 252 * years
    dt = 1/252
    results = []
    sample_paths = []
    
    for i in range(sim_count):
        # 產生利率隨機路徑
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = init_rate * np.exp(np.cumsum(vol * shocks - 0.5 * vol**2 * dt))
        
        coupons_earned = 0
        call_day = days
        status_str = "到期"
        
        for d in range(days):
            # 前半年 (126天) 固定計息
            if d < 126:
                coupons_earned += (fixed_coupon / 252)
            else:
                # 每一季 (63天) 觀察一次 Autocall
                if (d - 126) % 63 == 0 and path[d] <= call_barrier:
                    status_str, call_day = "提前贖回", d
                    break
                # 在計息區間內才領息 (5%)
                if path[d] <= accrual_barrier:
                    coupons_earned += (float_coupon / 252)
        
        duration = (call_day + 1) / 252
        results.append({
            'return': (coupons_earned / duration) * 100,
            'usd_gain': coupons_earned * principal,
            'status': status_str,
            'duration': duration
        })
        if i < 15: sample_paths.append(path[:call_day])
        
    return pd.DataFrame(results), sample_paths

df, paths = run_simulation()

# --- 6. 數據指標展示 ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("預期平均利息", f"${df['usd_gain'].mean():,.0f}")
c2.metric("平均年化收益", f"{df['return'].mean():.2f}%")
c3.metric("提前贖回機率", f"{(df['status']=='提前贖回').mean()*100:.1f}%")
c4.metric("預期持有年限", f"{df['duration'].mean():.1f} 年")

st.divider()

# --- 7. 圖表視覺化 ---
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("💰 預期收益分佈")
    fig_hist = go.Figure(data=[go.Histogram(x=df['usd_gain'], marker_color='#2980B9', nbinsx=20)])
    fig_hist.update_layout(xaxis_title="總利息收入 (USD)", yaxis_title="出現次數", height=400)
    st.plotly_chart(fig_hist, use_container_width=True)

with col_r:
    st.subheader("📈 利率模擬路徑")
    fig_path = go.Figure()
    for p in paths:
        fig_path.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.3, showlegend=False))
    
    fig_path.add_hline(y=accrual_barrier, line_dash="dash", line_color="red", annotation_text="計息上限 (4.3%)")
    fig_path.add_hline(y=call_barrier, line_dash="dash", line_color="green", annotation_text="Autocall (3.2%)")
    fig_path.update_layout(yaxis=dict(tickformat=".1%"), height=400, margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_path, use_container_width=True)

st.caption("註：本模擬基於幾何布朗運動 (GBM) 模型。過去績效不代表未來報酬之保證。")
