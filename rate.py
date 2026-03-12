import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from fredapi import Fred

# --- 1. 初始設定與 FRED 連線 ---
st.set_page_config(page_title="專業級利率哨兵", layout="wide")

# 從 Streamlit Secrets 自動讀取 Key
try:
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
    fred = Fred(api_key=FRED_API_KEY)
except Exception as e:
    st.error("❌ 無法從 Secrets 讀取 FRED_API_KEY，請檢查格式是否為 FRED_API_KEY = \"xxx\"")
    st.stop()

@st.cache_data(ttl=3600)
def get_market_data():
    try:
        # 抓取 10 年期美債常備到期利率 (DGS10)
        series = fred.get_series('DGS10')
        latest_val = series.iloc[-1]
        return float(latest_val)
    except:
        return 3.85 # 抓取失敗時的備援預設值

current_rate = get_market_data()

# --- 2. 介面標題 ---
st.title("🏛️ 聯準會連線：利率結構型產品哨兵")
st.caption(f"數據源：FRED (Federal Reserve Economic Data) | 目前市場 10Y 參考利率：{current_rate:.2f}%")

# --- 3. 側邊欄控制面板 ---
with st.sidebar:
    st.header("💵 投資設定")
    principal = st.number_input("投資本金 (USD)", value=50000, step=1000)
    
    st.header("📜 產品條件 (DSNGL0523)")
    fixed_coupon = st.slider("前半年固定年息 (%)", 0.0, 15.0, 6.8) / 100
    float_coupon = st.slider("半年後最高年息 (%)", 0.0, 10.0, 5.0) / 100
    
    st.header("🚧 門檻設定")
    accrual_limit = st.slider("計息區間上限 (%)", 2.0, 6.0, 4.3) / 100
    call_limit = st.slider("Autocall 門檻 (%)", 2.0, 6.0, 3.2) / 100
    
    st.header("📈 模擬設定")
    # 預設值自動對準 FRED 抓到的利率
    init_rate = st.slider("起始模擬利率 (%)", 2.0, 6.0, current_rate) / 100
    vol = st.slider("預期年化波動率 (%)", 5, 50, 15) / 100
    sim_count = st.select_slider("模擬次數", options=[100, 500, 1000], value=500)

# --- 4. 蒙地卡羅模擬引擎 ---
def run_simulation():
    years = 7
    days = 252 * years
    dt = 1/252
    
    results = []
    sample_paths = []
    
    for i in range(sim_count):
        # 模擬利率路徑 (GBM 模型)
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = init_rate * np.exp(np.cumsum(vol * shocks - 0.5 * vol**2 * dt))
        
        coupons_pct = 0
        call_day = days
        status = "到期"
        
        for d in range(days):
            if d < 126: # 前半年固定領息
                coupons_pct += (fixed_coupon / 252)
            else:
                # 季觀察 Autocall (每 63 交易日)
                if (d - 126) % 63 == 0 and path[d] <= call_limit:
                    status = "提前贖回"
                    call_day = d
                    break
                # 每日區間計息觀察
                if path[d] <= accrual_limit:
                    coupons_pct += (float_coupon / 252)
        
        duration = (call_day + 1) / 252
        total_usd_gain = coupons_pct * principal
        
        results.append({
            'annual_return': (coupons_pct / duration) * 100,
            'usd_gain': total_usd_gain,
            'status': status,
            'duration': duration
        })
        if i < 15: sample_paths.append(path[:call_day])
            
    return pd.DataFrame(results), sample_paths

# 執行運算
df, paths = run_simulation()

# --- 5. 視覺化呈現 ---
# 關鍵指標看板
c1, c2, c3, c4 = st.columns(4)
c1.metric("預期平均利息", f"${df['usd_gain'].mean():,.0f}")
c2.metric("平均年化收益", f"{df['annual_return'].mean():.2f}%")
c3.metric("提前贖回機率", f"{(df['status']=='提前贖回').mean()*100:.1f}%")
c4.metric("預期持有年限", f"{df['duration'].mean():.1f} 年")

st.divider()

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("💰 總收益分佈 (USD)")
    fig_hist = go.Figure(data=[go.Histogram(x=df['usd_gain'], marker_color='#2E86C1', nbinsx=25)])
    fig_hist.update_layout(xaxis_title="總利息收益 (美金)", yaxis_title="發生頻率", bargap=0.1)
    st.plotly_chart(fig_hist, use_container_width=True)

with col_right:
    st.subheader("📈 利率走勢與門檻模擬")
    fig_path = go.Figure()
    for p in paths:
        fig_path.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.3, showlegend=False))
    
    # 門檻標示
    fig_path.add_hline(y=accrual_barrier, line_dash="dash", line_color="#E74C3C", annotation_text=f"計息上限 {accrual_barrier*100:.1f}%")
    fig_path.add_hline(y=call_barrier, line_dash="dash", line_color="#27AE60", annotation_text=f"Autocall {call_barrier*100:.1f}%")
    
    fig_path.update_layout(yaxis=dict(tickformat=".1%"), margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_path, use_container_width=True)

# 底部洞察
st.info(f"💡 哨兵分析：目前市場利率為 {current_rate:.2f}%，距離計息上限還有 {accrual_barrier*100 - current_rate:.2f} 點空間。")
