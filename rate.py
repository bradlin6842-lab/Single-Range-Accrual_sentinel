import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import pytz

# --- 1. Initial Config ---
st.set_page_config(page_title="Rate Sentinel: Total Wealth Edition", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

def get_final_key():
    try:
        raw_val = st.secrets["FRED_API_KEY"]
        return "".join(filter(str.isalnum, str(raw_val))).lower()
    except: return None

target_key = get_final_key()

@st.cache_data(ttl=600)
def fetch_live_data(api_key):
    now = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
    base_url = "https://api.stlouisfed.org/fred/series/observations"
    def get_val(sid):
        try:
            url = f"{base_url}?series_id={sid}&api_key={api_key}&file_type=json&sort_order=desc&limit=1"
            res = requests.get(url, timeout=10).json()
            return float(res['observations'][0]['value'])
        except: return None
    t_rate = get_val("DGS10")
    m_move = get_val("MOVE")
    return t_rate if t_rate else 4.28, m_move if m_move else 105.0, now

fred_rate, move_vol, up_time = fetch_live_data(target_key)

# --- 2. Sidebar: The Command Center ---
with st.sidebar:
    st.header("💰 Portfolio Input")
    # This is the primary control for your Principal
    principal = st.number_input("Principal Amount (USD)", 
                                value=50000, 
                                step=5000, 
                                format="%d",
                                help="Adjust your initial investment amount here.")
    
    st.divider()
    st.header("📊 Benchmark & Credit")
    use_manual = st.checkbox("Use Bloomberg Manual Input", value=True)
    sofr_rate = st.number_input("10Y SOFR CMS (%)", value=3.78113, format="%.5f")
    current_benchmark = sofr_rate if use_manual else fred_rate
    
    issuer_rating = st.select_slider("Issuer Credit Rating", 
                                     options=["AAA", "AA", "A", "BBB", "BB"], value="A")
    pd_map = {"AAA": 0.02, "AA": 0.05, "A": 0.20, "BBB": 0.50, "BB": 1.50}
    annual_pd = pd_map[issuer_rating] / 100
    
    st.divider()
    st.header("📜 Term Adjustments")
    accrual_barrier = st.slider("Accrual Barrier (%)", 3.5, 5.5, 4.3) / 100
    call_barrier = st.slider("Autocall Barrier (%)", 2.5, 4.0, 3.2) / 100
    
    vol_factor = st.slider("Volatility Stress (%)", 50, 200, 100) / 100
    sim_vol = (move_vol / 1000) * vol_factor

# --- 3. Total Wealth Simulation Logic ---
def run_wealth_sim(p_rate, principal_val):
    days, dt = 252 * 7, 1/252
    results, sample_paths = [], []
    for i in range(400):
        shocks = np.random.normal(0, np.sqrt(dt), days)
        path = (p_rate/100) * np.exp(np.cumsum(sim_vol * shocks - 0.5 * sim_vol**2 * dt))
        coupons = 0.034 # 1st 6M fixed
        call_day = days
        for d in range(126, days):
            if (d-126) % 63 == 0 and path[d] <= call_barrier:
                call_day = d; break
            if path[d] <= accrual_barrier: coupons += (0.05 / 252)
        
        dur = (call_day + 1) / 252
        survival_rate = (1 - annual_pd) ** dur
        interest_earned = coupons * principal_val
        # Total Wealth = Principal + Interest (Adjusted for Credit Risk)
        total_payout = (principal_val + interest_earned) * survival_rate
        
        results.append({
            'yield': (coupons/dur)*100, 
            'total_payout': total_payout,
            'interest_only': interest_earned * survival_rate,
            'dur': dur
        })
        if i < 15: sample_paths.append(path[:call_day])
    return pd.DataFrame(results), sample_paths

df_res, path_res = run_wealth_sim(current_benchmark, principal)

# --- 4. Main Dashboard ---
st.title("🏛️ Sentinel Pro: Total Asset Projection")

# Top Level Metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("Current SOFR", f"{current_benchmark:.4f}%")
m2.metric("Principal Investment", f"${principal:,.0f}")
m3.metric("Exp. Total Payout", f"${df_res['total_payout'].mean():,.0f}")
m4.metric("Risk Cost (PD)", f"${(principal + df_res['interest_only'].mean()) * (1 - (1-annual_pd)**df_res['dur'].mean()):,.0f}", delta_color="inverse")

st.divider()

# Charts Area
col_l, col_r = st.columns(2)

with col_l:
    st.subheader("💰 Total Wealth Distribution (Principal + Interest)")
    fig_comp = go.Figure()
    # Now showing the full wealth distribution starting from your principal
    fig_comp.add_trace(go.Violin(x=df_res['total_payout'], 
                                 name='Total Payout at Maturity', 
                                 line_color="#2ECC71", 
                                 box_visible=True, 
                                 meanline_visible=True))
    fig_comp.update_layout(xaxis_title="Total Projected Wealth (USD)", 
                           height=450, 
                           xaxis=dict(range=[principal * 0.9, principal * 1.5])) # Zoom in near principal
    st.plotly_chart(fig_comp, use_container_width=True)
    st.caption(f"Graph shows projected wealth. Your principal base is ${principal:,.0f}.")

with col_r:
    st.subheader("🎯 Real-Time Accrual Monitor")
    fig_gauge = go.Figure(go.Indicator(
        mode = "gauge+number", value = current_benchmark,
        gauge = {
            'axis': {'range': [2.5, 5.0]},
            'steps' : [
                {'range': [0, call_barrier*100], 'color': "#D5F5E3"},
                {'range': [call_barrier*100, accrual_barrier*100], 'color': "#EBEDEF"},
                {'range': [accrual_barrier*100, 5.0], 'color': "#FADBD8"}],
            'threshold': {'line': {'color': "red", 'width': 4}, 'value': accrual_barrier*100}
        }
    ))
    fig_gauge.update_layout(height=400)
    st.plotly_chart(fig_gauge, use_container_width=True)

st.subheader("📈 Interest Rate Simulation Paths")
fig_path = go.Figure()
for p in path_res: fig_path.add_trace(go.Scatter(y=p, mode='lines', line=dict(width=1), opacity=0.3, showlegend=False))
fig_path.add_hline(y=accrual_barrier, line_dash="dash", line_color="red", annotation_text="Barrier")
fig_path.update_layout(yaxis=dict(tickformat=".1%"), height=400)
st.plotly_chart(fig_path, use_container_width=True)
