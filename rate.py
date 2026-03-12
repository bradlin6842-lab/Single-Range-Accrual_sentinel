import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# 設定頁面資訊
st.set_page_config(page_title="利率哨兵 DSNGL0523", layout="wide")

st.title("📊 利率結構型產品模擬器")
st.caption("DSNGL0523: Single Range Accrual SN 哨兵系統")

# --- 側邊欄參數 ---
with st.sidebar:
    st.header("⚙️ 參數設定")
    init_rate = st.slider("目前 CMS 10Y 利率 (%)", 2.0, 6.0, 3.85) / 100
    vol = st.slider("預期波動率 (%)", 5, 40, 15) / 100
    st.divider()
    accrual_limit = 4.3 / 100
    call_limit = 3.2 / 100
    sim_count = st.select_slider("模擬次數", options=[100, 500, 1000], value=500)

# --- 模擬計算 ---
def run_simulation():
    days = 252 * 7
    dt = 1/252
    results = []
    sample_paths = []
    
    for i in range(sim_count):
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = init_rate * np.exp(np.cumsum(vol * shocks - 0.5 * vol**2 * dt))
        
        coupons = 0
        call_day = days
        status = "到期"
        
        for d in range(days):
            if d < 126: # 前半年固定 6.8%
                coupons += (0.068 / 252)
            else:
                if (d - 126) % 63 == 0 and path[d] <= call_limit: # 季觀察
                    status = "提前贖回"
                    call_day = d
                    break
                if path[d] <= accrual_limit: # 區間計息 5%
                    coupons += (0.05 / 252)
        
        duration = (call_day + 1) / 252
        results.append({'return': (coupons / duration) * 100, 'status': status, 'duration': duration})
        if i < 15: sample_paths.append(path[:call_day])
    return pd.DataFrame(results), sample_paths

# --- 顯示結果 ---
df, paths = run_simulation()

c1, c2, c3 = st.columns(3)
c1.metric("平均年化回報", f"{df['return'].mean():.2f}%")
c2.metric("提前贖回機率", f"{(df['status']=='提前贖回').mean()*100:.1f}%")
c3.metric("平均持有年限", f"{df['duration'].mean():.1f} 年")

st.subheader("📈 利率路徑與區間模擬")
fig = go.Figure()
for p in paths:
    fig.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.4, showlegend=False))
fig.add_hline(y=accrual_limit, line_dash="dash", line_color="red", annotation_text="計息上限 4.3%")
fig.add_hline(y=call_limit, line_dash="dash", line_color="green", annotation_text="Autocall 3.2%")
st.plotly_chart(fig, use_container_width=True)
