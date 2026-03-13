import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
from datetime import datetime
import pytz

# --- 1. 初始設定 ---
st.set_page_config(page_title="利率哨兵 Pro", layout="wide")
tw_tz = pytz.timezone('Asia/Taipei')

# --- 2. 鑰匙讀取與強力去漬 (粉碎隱形字元) ---
def get_final_key():
    try:
        raw_val = st.secrets["FRED_API_KEY"]
        # 強力粉碎：只留下小寫英文字母與數字，刪除所有引號、空格、換行與隱形字元
        clean_key = "".join(filter(str.isalnum, str(raw_val))).lower()
        return clean_key
    except:
        return None

target_key = get_final_key()

# --- 3. 診斷與狀態顯示 ---
with st.sidebar:
    st.subheader("🔍 系統診斷")
    if target_key:
        st.code(f"長度: {len(target_key)} (應為 32)")
        st.code(f"頭尾: {target_key[:3]}...{target_key[-3:]}")
    else:
        st.error("找不到鑰匙")

# --- 4. 數據抓取 (直接向 FRED 請求) ---
@st.cache_data(ttl=600)
def fetch_fred_data(api_key):
    now = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")
    try:
        # 使用 DGS10 作為測試
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id=DGS10&api_key={api_key}&file_type=json&sort_order=desc&limit=1"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        if response.status_code != 200:
            error_msg = data.get("error_message", "未知錯誤")
            return 3.85, 15.0, 100.0, now, f"🔴 錯誤: {error_msg[:20]}"
            
        rate = float(data['observations'][0]['value'])
        
        # 抓取 MOVE (這裡簡化，直接給個預設或再次請求)
        return rate, 15.0, 105.0, now, "🟢 連線成功"
    except Exception as e:
        return 3.85, 15.0, 100.0, now, f"🔴 系統異常: {str(e)[:15]}"

m_rate, m_vol, m_move, up_time, status = fetch_fred_data(target_key)

st.title("🏛️ 聯準會利率哨兵系統")
st.markdown(f"**數據狀態：{status}** | 最後更新：`{up_time}`")

if "🟢" in status:
    st.success(f"📡 已同步最新數據：10Y 利率 {m_rate:.2f}%")
else:
    st.warning("目前正使用備援數據。請檢查 FRED 帳號狀態或 Key 是否過期。")

# (其餘模擬器 UI 代碼...)
st.divider()
c1, c2, c3 = st.columns(3)
c1.metric("目前市場利率", f"{m_rate:.2f}%")
c2.metric("預期年化波動", f"{m_vol:.1f}%")
c3.metric("MOVE 指數", f"{m_move:.1f}")
