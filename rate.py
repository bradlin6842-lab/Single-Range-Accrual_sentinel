import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from fredapi import Fred

# --- 1. 初始設定與 FRED 連線 ---
st.set_page_config(page_title="自動化利率哨兵 Pro", layout="wide")

try:
    # 確保你的 Streamlit Secrets 已設定 FRED_API_KEY
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
    fred = Fred(api_key=FRED_API_KEY)
except Exception as e:
    st.error("❌ 無法讀取 Secrets。請確保格式為：FRED_API_KEY = \"你的代碼\"")
    st.stop()

@st.cache_data(ttl=3600) # 每小時更新一次數據
def get_market_data():
    try:
        # 抓取 10Y 利率 (DGS10) 與 債市波動率 (MOVE)
        rate_series = fred.get_series('DGS10')
        move_series = fred.get_series('MOVE')
        
        latest_rate = float(rate_series.iloc[-1])
        latest_move = float(move_series.iloc[-1])
        
        # 核心邏輯：將 MOVE Index 轉換為模擬用的年化波動率建議值
        # 經驗公式：MOVE 100 約對應 10% 的波動 Vibe
        suggested_vol = latest_move / 10 
        
        return latest_rate, suggested_vol, latest_move
    except Exception as e:
        # 抓取失敗時的備援值
        return 3.85, 15.0, 100.0

# 取得即時市場數據
market_rate, market_vol, move_index = get_market_data()

# --- 2. 介面標題 ---
st.title("Range Accural哨兵 (Fed DGS10 + MOVE)")
st.info(f"📡 連線成功！目前市場 10Y 利率：{market_rate:.2f}% | MOVE 波動指數：{move_index:.1f} (建議波動率：{market_vol:.1f}%)")

# --- 3. 側邊欄控制面板 ---
with st.sidebar:
    st.header("💵 投資金額")
    principal = st.number_input("本金 (USD)", value=50000, step=1000)
    
    st.header("📈 市場動態 (自動載入)")
    # 起始利率預設對齊市場
    init_rate = st.slider("起始模擬利率 (%)", 2.0, 6.0, market_rate) / 100
    # 波動率預設對齊 MOVE Index 轉換值
    vol = st.slider("預期年化波動率 (%)", 5, 50, int(market_vol)) / 100
    
    st.header("📜 產品條件")
    fixed_coupon = st.slider("前半年固定年息 (%)", 0.0, 15.0, 6.8) / 100
    float_coupon = st.slider("半年後最高年息 (%)", 0.0, 10.0, 5.0) / 100
    
    st.header("🚧 門檻設定 (Barrier)")
    accrual_barrier = st.slider("計息區間上限 (%)", 2.0, 6.0, 4.3) / 100
    call_barrier = st.slider("Autocall 門檻 (%)", 2.0, 6.0, 3.2) / 100
    
    sim_count = st.select_slider("模擬次數", options=[100, 500, 1000], value=500)

# --- 4. 蒙地卡羅模擬引擎 ---
def run_simulation():
    years = 7
    days = 252 * years
    dt = 1/252
    
    results = []
    sample_paths = []
    
    for i in range(sim_count):
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = init_rate * np.exp(np.cumsum(vol * shocks - 0.5 * vol**2 * dt))
        
        coupons_pct = 0
        call_day = days
        status = "到期"
        
        for d in range(days):
            if d < 126: # 前半年固定
                coupons_pct += (fixed_coupon / 252)
            else:
                if (d - 126) % 63 == 0 and path[d] <= call_barrier: # 季觀察 Autocall
                    status = "提前贖回"
                    call_day = d
                    break
                if path[d] <= accrual_barrier: # 每日計息
                    coupons_pct += (float_coupon / 252)
        
        duration = (call_day + 1) / 252
        usd_gain = coupons_pct * principal
        
        results.append({
            'annual_return': (coupons_pct / duration) * 100,
            'usd_gain': usd_gain,
            'status': status,
            'duration': duration
        })
        if i < 15: sample_paths.append(path[:call_day])
            
    return pd.DataFrame(results), sample_paths

df, paths = run_simulation()

# --- 5. 視覺化呈現 ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("預期平均利息", f"${df['usd_gain'].mean():,.0f}")
c2.metric("平均年化收益", f"{df['annual_return'].mean():.2f}%")
c3.metric("提前贖回機率", f"{(df['status']=='提前贖回').mean()*100:.1f}%")
c4.metric("平均持有年限", f"{df['duration'].mean():.1f} 年")

st.divider()

col_l, col_r = st.columns(2)

with col_l:
    st.subheader("💰 收益分佈預測")
    fig_hist = go.Figure(data=[go.Histogram(x=df['usd_gain'], marker_color='#2980B9', nbinsx=20)])
    fig_hist.update_layout(xaxis_title="利息美金金額", yaxis_title="發生次數", bargap=0.1)
    st.plotly_chart(fig_hist, use_container_width=True)

with col_r:
    st.subheader("📈 利率路徑與區間監控")
    fig_path = go.Figure()
    for p in paths:
        fig_path.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.3, showlegend=False))
    
    fig_path.add_hline(y=accrual_barrier, line_dash="dash", line_color="red", 
                       annotation_text=f"計息上限 {accrual_barrier*100:.1f}%")
    fig_path.add_hline(y=call_barrier, line_dash="dash", line_color="green", 
                       annotation_text=f"Autocall {call_barrier*100:.1f}%")
    
    fig_path.update_layout(yaxis=dict(tickformat=".1%"), margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_path, use_container_width=True)

st.success(f"💡 哨兵洞察：目前市場波動率（MOVE 指數）處於 {move_index:.1f} 水準，這代表市場對未來利率的看法{'較為動盪' if move_index > 110 else '相對平穩'}。")
