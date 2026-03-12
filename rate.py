import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from fredapi import Fred

# --- 1. 初始設定與 FRED 連線 (從 Secrets 讀取) ---
st.set_page_config(page_title="專業級利率哨兵", layout="wide")

try:
    # 確保你的 Secrets 裡有 FRED_API_KEY
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
    fred = Fred(api_key=FRED_API_KEY)
except Exception as e:
    st.error("❌ 無法讀取 Secrets 中的 FRED_API_KEY。請檢查格式是否為 FRED_API_KEY = \"xxx\"")
    st.stop()

@st.cache_data(ttl=3600)
def get_market_data():
    try:
        # 抓取 FRED 10 年期美債利率 (DGS10)
        series = fred.get_series('DGS10')
        return float(series.iloc[-1])
    except:
        return 3.85 # 備援預設值

current_market_rate = get_market_data()

# --- 2. 介面標題 ---
st.title("🏛️ 聯準會數據連線：利率哨兵系統")
st.caption(f"數據源：FRED | 目前 10Y 參考利率：{current_market_rate:.2f}%")

# --- 3. 側邊欄控制面板 (定義變數名稱) ---
with st.sidebar:
    st.header("💵 投資金額")
    principal = st.number_input("本金 (USD)", value=50000, step=1000)
    
    st.header("📜 產品條件")
    fixed_coupon = st.slider("前半年固定年息 (%)", 0.0, 15.0, 6.8) / 100
    float_coupon = st.slider("半年後最高年息 (%)", 0.0, 10.0, 5.0) / 100
    
    st.header("🚧 門檻設定 (Barrier)")
    # 這裡統一使用 _barrier 結尾，避免後續畫圖出錯
    accrual_barrier = st.slider("計息區間上限 (%)", 2.0, 6.0, 4.3) / 100
    call_barrier = st.slider("Autocall 門檻 (%)", 2.0, 6.0, 3.2) / 100
    
    st.header("📈 模擬參數")
    init_rate = st.slider("起始模擬利率 (%)", 2.0, 6.0, current_market_rate) / 100
    vol = st.slider("預測年化波動率 (%)", 5, 50, 15) / 100
    sim_count = st.select_slider("模擬次數", options=[100, 500, 1000], value=500)

# --- 4. 蒙地卡羅模擬引擎 ---
def run_simulation():
    years = 7
    days = 252 * years
    dt = 1/252
    
    results = []
    sample_paths = []
    
    for i in range(sim_count):
        # 模擬利率路徑
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = init_rate * np.exp(np.cumsum(vol * shocks - 0.5 * vol**2 * dt))
        
        coupons_pct = 0
        call_day = days
        status = "到期"
        
        for d in range(days):
            if d < 126: # 前半年固定
                coupons_pct += (fixed_coupon / 252)
            else:
                # 季觀察 Autocall
                if (d - 126) % 63 == 0 and path[d] <= call_barrier:
                    status = "提前贖回"
                    call_day = d
                    break
                # 每日計息觀察
                if path[d] <= accrual_barrier:
                    coupons_pct += (float_coupon / 252)
        
        duration = (call_day + 1) / 252
        usd_gain = coupons_pct * principal
        
        results.append({
            'return': (coupons_pct / duration) * 100,
            'usd_gain': usd_gain,
            'status': status,
            'duration': duration
        })
        if i < 15: sample_paths.append(path[:call_day])
            
    return pd.DataFrame(results), sample_paths

# 執行運算
df, paths = run_simulation()

# --- 5. 視覺化呈現 ---
# 頂部指標
c1, c2, c3, c4 = st.columns(4)
c1.metric("預期平均利息", f"${df['usd_gain'].mean():,.0f}")
c2.metric("平均年化收益率", f"{df['return'].mean():.2f}%")
c3.metric("提前贖回機率", f"{(df['status']=='提前贖回').mean()*100:.1f}%")
c4.metric("平均持有年限", f"{df['duration'].mean():.1f} 年")

st.divider()

col_l, col_r = st.columns(2)

with col_l:
    st.subheader("💰 總收益分佈 (USD)")
    fig_hist = go.Figure(data=[go.Histogram(x=df['usd_gain'], marker_color='#3498DB', nbinsx=20)])
    fig_hist.update_layout(xaxis_title="利息美金金額", yaxis_title="出現次數", bargap=0.1)
    st.plotly_chart(fig_hist, use_container_width=True)

with col_r:
    st.subheader("📈 利率走勢與門檻模擬")
    fig_path = go.Figure()
    for p in paths:
        fig_path.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.3, showlegend=False))
    
    # 加入門檻界線 (已修正變數名稱)
    fig_path.add_hline(y=accrual_barrier, line_dash="dash", line_color="red", 
                       annotation_text=f"計息上限 {accrual_barrier*100:.1f}%")
    fig_path.add_hline(y=call_barrier, line_dash="dash", line_color="green", 
                       annotation_text=f"Autocall {call_barrier*100:.1f}%")
    
    fig_path.update_layout(yaxis=dict(tickformat=".1%"), margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_path, use_container_width=True)

st.info(f"💡 哨兵提示：當前 10Y 利率為 {current_market_rate:.2f}%，只要不衝破紅虛線，您每天都在賺錢。")
