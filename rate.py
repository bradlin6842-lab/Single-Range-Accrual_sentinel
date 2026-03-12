import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# 頁面基本設定
st.set_page_config(page_title="結構型產品哨兵", layout="wide")

st.title("🏦 結構型產品 (Range Accrual) 全功能模擬器")
st.caption("自定義產品條件與現金流分析")

# --- 側邊欄：設定區 ---
with st.sidebar:
    st.header("💵 投資金額")
    principal = st.number_input("本金 (USD)", value=50000, step=1000)
    
    st.header("📜 產品配息條件")
    fixed_rate = st.slider("前半年固定年息 (%)", 0.0, 15.0, 6.8) / 100
    float_rate = st.slider("半年後最高年息 (%)", 0.0, 10.0, 5.0) / 100
    
    st.header("🚧 門檻設定 (Barrier)")
    accrual_barrier = st.slider("計息區間上限 (%)", 2.0, 6.0, 4.3) / 100
    call_barrier = st.slider("Autocall 門檻 (%)", 2.0, 6.0, 3.2) / 100
    
    st.header("📈 市場預期")
    init_rate = st.slider("目前 CMS 10Y 利率 (%)", 2.0, 6.0, 3.85) / 100
    vol = st.slider("預測年化波動率 (%)", 5, 50, 15) / 100
    sim_count = st.select_slider("模擬精確度", options=[100, 500, 1000], value=500)

# --- 核心運算引擎 ---
def run_simulation():
    days = 252 * 7  # 7年期
    dt = 1/252
    
    results = []
    sample_paths = []
    
    for i in range(sim_count):
        # 幾何布朗運動
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = init_rate * np.exp(np.cumsum(vol * shocks - 0.5 * vol**2 * dt))
        
        coupons_pct = 0
        call_day = days
        status = "到期"
        
        for d in range(days):
            if d < 126: # 前半年固定
                coupons_pct += (fixed_rate / 252)
            else:
                # 季觀察 Autocall
                if (d - 126) % 63 == 0 and path[d] <= call_barrier:
                    status = "提前贖回"
                    call_day = d
                    break
                # 每日區間計息
                if path[d] <= accrual_barrier:
                    coupons_pct += (float_rate / 252)
        
        duration = (call_day + 1) / 252
        total_usd = coupons_pct * principal
        
        results.append({
            'return': (coupons_pct / duration) * 100,
            'usd_gain': total_usd,
            'status': status,
            'duration': duration
        })
        if i < 15: sample_paths.append(path[:call_day])
    return pd.DataFrame(results), sample_paths

# --- 執行與呈現 ---
df, paths = run_simulation()

# 第一排：關鍵看板
c1, c2, c3, c4 = st.columns(4)
c1.metric("預期總配息 (USD)", f"${df['usd_gain'].mean():,.0f}")
c2.metric("平均年化收益率", f"{df['return'].mean():.2f}%")
c3.metric("提前贖回機率", f"{(df['status']=='提前贖回').mean()*100:.1f}%")
c4.metric("平均持有時間", f"{df['duration'].mean():.1f} 年")

# 第二排：圖表
st.divider()
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("💰 總利息收益分佈")
    # 自定義分佈圖
    hist_data = df['usd_gain']
    fig_hist = go.Figure(data=[go.Histogram(x=hist_data, marker_color='skyblue', nbinsx=20)])
    fig_hist.update_layout(xaxis_title="美金利息", yaxis_title="發生次數", bargap=0.1)
    st.plotly_chart(fig_hist, use_container_width=True)

with col_right:
    st.subheader("📈 利率走勢模擬")
    fig_path = go.Figure()
    for p in paths:
        fig_path.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.3, showlegend=False))
    
    # 加入界線 (依據使用者設定)
    fig_path.add_hline(y=accrual_barrier, line_dash="dash", line_color="red", annotation_text=f"上限 {accrual_barrier*100:.1f}%")
    fig_path.add_hline(y=call_barrier, line_dash="dash", line_color="green", annotation_text=f"Autocall {call_barrier*100:.1f}%")
    
    # 座標軸百分比格式
    fig_path.update_layout(yaxis=dict(tickformat=".1%"), margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig_path, use_container_width=True)

st.info(f"💡 哨兵提示：在目前設定下，您投入 ${principal:,.0f} 元，預期利息約落在 ${df['usd_gain'].min():,.0f} ~ ${df['usd_gain'].max():,.0f} 之間。")
