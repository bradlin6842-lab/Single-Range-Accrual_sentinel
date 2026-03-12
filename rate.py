import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# 頁面基本設定
st.set_page_config(page_title="DSNGL0523 哨兵系統", layout="wide")

st.title("💰Single Range Accrual現金流預測")
st.caption("產品代碼：DSNGL0523 | SG 法國興業銀行發行")

# --- 側邊欄：加入投資金額 ---
with st.sidebar:
    st.header("⚙️ 模擬參數")
    principal = st.number_input("投資金額 (USD)", value=50000, step=1000)
    st.divider()
    init_rate = st.slider("目前 CMS 10Y 利率 (%)", 2.0, 6.0, 3.85) / 100
    vol = st.slider("市場波動率 (%)", 5, 40, 15) / 100
    sim_count = st.select_slider("模擬路徑數", options=[100, 500, 1000], value=500)

# --- 核心運算引擎 ---
def run_simulation():
    days = 252 * 7
    dt = 1/252
    accrual_limit = 4.3 / 100
    call_limit = 3.2 / 100
    
    results = []
    sample_paths = []
    
    for i in range(sim_count):
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = init_rate * np.exp(np.cumsum(vol * shocks - 0.5 * vol**2 * dt))
        
        coupons_pct = 0
        call_day = days
        status = "到期"
        
        for d in range(days):
            if d < 126: # 前半年固定 6.8%
                coupons_pct += (0.068 / 252)
            else:
                if (d - 126) % 63 == 0 and path[d] <= call_limit:
                    status = "提前贖回"
                    call_day = d
                    break
                if path[d] <= accrual_limit:
                    coupons_pct += (0.05 / 252)
        
        duration = (call_day + 1) / 252
        total_usd = coupons_pct * principal # 計算實際美金收益
        
        results.append({
            'return': (coupons_pct / duration) * 100,
            'usd_gain': total_usd,
            'status': status,
            'duration': duration
        })
        if i < 15: sample_paths.append(path[:call_day])
    return pd.DataFrame(results), sample_paths

# --- 執行與顯示結果 ---
df, paths = run_simulation()

# 第一排：核心指標
c1, c2, c3, c4 = st.columns(4)
c1.metric("預期總利息 (USD)", f"${df['usd_gain'].mean():,.0f}")
c2.metric("平均年化回報", f"{df['return'].mean():.2f}%")
c3.metric("提前贖回機率", f"{(df['status']=='提前贖回').mean()*100:.1f}%")
c4.metric("平均持有年限", f"{df['duration'].mean():.1f} 年")

# 第二排：圖表
st.subheader("📊 投資體感分析")
col_left, col_right = st.columns(2)

with col_left:
    st.write("**總利息收益分佈 (USD)**")
    st.bar_chart(df['usd_gain'])
    st.caption("這張圖顯示了在不同情境下，你最終拿到的總美金利息。")

with col_right:
    st.write("**利率走勢預測**")
    fig = go.Figure()
    for p in paths:
        fig.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.3, showlegend=False))
    fig.add_hline(y=4.3/100, line_dash="dash", line_color="red")
    fig.add_hline(y=3.2/100, line_dash="dash", line_color="green")
    st.plotly_chart(fig, use_container_width=True)

# 底部提醒
st.info(f"💡 根據模擬，你投入 ${principal:,.0f} 元，大約有 { (df['usd_gain'] > (principal*0.068*0.5)).mean()*100 :.0f}% 的機率領到超過半年的利息。")
