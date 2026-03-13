import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import pytz

# --- 1. 初始設定 ---
st.set_page_config(page_title="利率哨兵 Pro：信用風險強化版", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

# --- 2. 數據清洗與抓取 ---
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
            if 'observations' in res and len(res['observations']) > 0:
                v = res['observations'][0]['value']
                return float(v) if v != "." else None
        except: return None
        return None

    r = get_val("DGS10")
    m = get_val("MOVE")
    final_r = r if r else 4.21
    final_m = m if m else 105.0
    status = "🟢 連線成功" if (r and m) else "🟡 部分數據連線 (使用暫存)"
    return final_r, final_m / 10, final_m, now, status

m_rate, m_vol, m_move, up_time, status = fetch_data(target_key)

# --- 3. 側邊欄：加入信用風險設定 ---
with st.sidebar:
    st.subheader("🔍 系統診斷")
    st.caption(f"狀態：{status} | 更新：{up_time}")
    st.divider()
    
    st.header("💵 投資設定")
    principal = st.number_input("本金 (USD)", value=50000)
    init_rate = st.slider("起始利率 (%)", 2.0, 6.0, m_rate) / 100
    vol = st.slider("年化波動率 (%)", 5, 50, int(m_vol)) / 100
    
    st.header("🛡️ 發行商信用風險 (Credit Risk)")
    issuer_rating = st.select_slider(
        "發行商信用評等",
        options=["AAA (極優)", "AA (優質)", "A (良好)", "BBB (警示)", "BB (投機)"],
        value="A (良好)"
    )
    # 預期年化違約率 (PD) 映射
    pd_map = {"AAA (極優)": 0.02, "AA (優質)": 0.05, "A (良好)": 0.20, "BBB (警示)": 0.50, "BB (投機)": 1.50}
    annual_pd = pd_map[issuer_rating] / 100

    st.header("📜 產品條件 (7Y)")
    accrual_barrier = st.slider("計息上限 (%)", 3.5, 5.5, 4.3) / 100
    call_barrier = st.slider("Autocall 門檻 (%)", 2.5, 4.0, 3.2) / 100

# --- 4. 蒙地卡羅模擬核心 ---
def run_sim():
    days, dt = 252 * 7, 1/252
    results = []
    sample_paths = []
    for i in range(500):
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = init_rate * np.exp(np.cumsum(vol * shocks - 0.5 * vol**2 * dt))
        coupons = 0.034 # 前半年固定
        call_day = days
        status_str = "到期"
        for d in range(126, days):
            if (d-126) % 63 == 0 and path[d] <= call_barrier:
                status_str, call_day = "提前贖回", d
                break
            if path[d] <= accrual_barrier: coupons += (0.05 / 252)
        
        dur = (call_day + 1) / 252
        # 計算此路徑下的存活機率 (Survival Probability)
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

# --- 5. 主畫面展示 ---
st.title("🏛️ 聯準會利率哨兵：風險全能版")
st.info(f"📡 市場實時：10Y 利率 {m_rate:.2f}% | MOVE 指數 {m_move:.1f} | 評等 {issuer_rating}")

# 關鍵指標
c1, c2, c3, c4 = st.columns(4)
c1.metric("預期總利息", f"${df['usd'].mean():,.0f}")
c2.metric("風險調整後收益", f"${df['risk_adj_usd'].mean():,.0f}", 
          delta=f"-${df['usd'].mean()-df['risk_adj_usd'].mean():,.0f} 風險成本", delta_color="inverse")
c3.metric("年化收益率", f"{df['return'].mean():.2f}%")
c4.metric("倒閉風險威脅", f"{annual_pd*100:.2f}% / 年")

st.divider()

# 圖表視覺化
col_l, col_r = st.columns(2)
with col_l:
    st.subheader("💰 收益與信用風險對比")
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(x=df['usd'], name='名目收益', marker_color='#3498DB', opacity=0.6))
    fig_hist.add_trace(go.Histogram(x=df['risk_adj_usd'], name='風險調整後', marker_color='#E74C3C', opacity=0.6))
    fig_hist.update_layout(barmode='overlay', xaxis_title="USD", yaxis_title="頻率", height=400)
    st.plotly_chart(fig_hist, use_container_width=True)

with col_r:
    st.subheader("📈 利率路徑與計息邊界")
    fig_path = go.Figure()
    for p in paths: fig_path.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.3, showlegend=False))
    fig_path.add_hline(y=accrual_barrier, line_dash="dash", line_color="red", annotation_text="計息上限")
    fig_path.add_hline(y=call_barrier, line_dash="dash", line_color="green", annotation_text="贖回門檻")
    fig_path.update_layout(yaxis=dict(tickformat=".1%"), height=400, margin=dict(l=0, r=0, t=20, b=0))
    st.plotly_chart(fig_path, use_container_width=True)

if annual_pd > 0.005:
    st.warning(f"🚨 目前發行商信用風險較高。考慮到違約機率，你的預期收益已縮水約 ${df['usd'].mean()-df['risk_adj_usd'].mean():,.0f}。")
