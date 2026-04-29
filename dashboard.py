import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz

# --- 1. CONFIGURATION & PAGE SETUP ---
st.set_page_config(page_title="Hussain Algo Terminal V3", page_icon="📈", layout="wide")

# AI Configuration
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    ai_model = genai.GenerativeModel('gemini-pro')
except:
    ai_model = None

# --- 2. DATA ENGINES (INPUT BLOCKS) ---

@st.cache_data(ttl=3600)
def load_cot_data():
    try:
        df = pd.read_excel("COT.xlsm", sheet_name="Main", engine='openpyxl', skiprows=2)
        df = df.iloc[:, [0, 1, 6, 10, 11]]
        df.columns = ['Instrument', 'Net Change', 'Direction', 'COT_Index_NComm', 'COT_Index_Comm']
        return df.dropna(subset=['Instrument'])
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_daily_oi():
    currencies = ['EUR', 'GBP', 'AUD', 'NZD', 'CAD', 'CHF', 'JPY', 'Gold']
    oi_list = []
    try:
        xls = pd.ExcelFile("Daily_OI.xlsm", engine='openpyxl')
        for symbol in currencies:
            if symbol in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=symbol)
                if not df.empty:
                    latest = df.iloc[0]
                    status = "Increasing 🟢" if latest['Change in Futures Open Interest'] > 0 else "Decreasing 🔴"
                    oi_list.append({'Instrument': symbol, 'OI': int(latest['Futures Open Interest']), 'Status': status})
        return pd.DataFrame(oi_list)
    except: return pd.DataFrame()

@st.cache_data(ttl=300)
def get_news():
    try:
        r = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.xml", timeout=10)
        root = ET.fromstring(r.content)
        news = []
        for item in root.findall('event'):
            impact = item.find('impact').text
            title = item.find('title').text
            if impact == 'High' or 'Holiday' in title:
                news.append({'Type': "🔴 High" if impact == 'High' else "🏦 Holiday", 
                             'Curr': item.find('country').text, 'Event': title, 'Time': item.find('time').text})
        return pd.DataFrame(news).head(10)
    except: return pd.DataFrame()

def get_matrix_data():
    currencies = ['EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
    pairs = [f"{c}USD=X" if c != 'USD' else "DX-Y.NYB" for c in currencies]
    data = yf.download(pairs, period="1mo", interval="1d", progress=False)['Close']
    scores = {}
    for c in currencies:
        ticker = f"{c}USD=X" if c != 'USD' else "DX-Y.NYB"
        if ticker in data.columns:
            close = data[ticker].iloc[-1]
            sma20 = data[ticker].rolling(20).mean().iloc[-1]
            scores[c] = 1 if close > sma20 else -1
    return scores

# --- 3. OUTPUT BLOCKS (UI DESIGN) ---

def show_sessions():
    pkt_tz = pytz.timezone('Asia/Karachi')
    now = datetime.now(pkt_tz)
    st.subheader("🌍 Global Market Sessions (PKT)")
    
    if now.weekday() >= 5:
        st.error("🛑 MARKET CLOSED (WEEKEND)")
        return

    cols = st.columns(4)
    sessions = [
        {"name": "🇦🇺 Sydney", "open": 4, "close": 13},
        {"name": "🇯🇵 Tokyo", "open": 5, "close": 14},
        {"name": "🇬🇧 London", "open": 12, "close": 21},
        {"name": "🇺🇸 New York", "open": 17, "close": 2}
    ]
    
    for i, s in enumerate(sessions):
        is_active = False
        current_hour = now.hour
        if s["open"] < s["close"]:
            is_active = s["open"] <= current_hour < s["close"]
        else: # Over midnight
            is_active = current_hour >= s["open"] or current_hour < s["close"]
            
        color = "#1E5128" if is_active else "#333333"
        text = "🟢 ACTIVE" if is_active else "Closed"
        cols[i].markdown(f"<div style='padding:15px; border-radius:10px; background-color:{color}; text-align:center;'><h4>{s['name']}</h4><p>{text}</p></div>", unsafe_allow_html=True)

# --- 4. MAIN DASHBOARD LAYOUT ---

show_sessions()
st.divider()

col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("🔥 Active Trade Setups & AI Scoring")
    # Logic: Matrix Strength + VSA + Structure alignment
    matrix_scores = get_matrix_data()
    # Dummy logic for display - in real it will use Block 1 & 2
    st.success("📈 BUY EURUSD | Score: 92% (Strong Alignment)")
    st.info("🤖 AI: COT Near Bottom + Matrix Strong + No News Conflict. High Probability.")
    
    st.subheader("📊 Currency Strength Matrix")
    st.write(pd.DataFrame([matrix_scores], index=["Strength"]))

with col_right:
    st.subheader("🏦 Institutional (COT/OI)")
    st.dataframe(load_cot_data(), hide_index=True)
    st.dataframe(load_daily_oi(), hide_index=True)
    
    st.subheader("📰 Major News & Squawk")
    st.table(get_news())

st.divider()
st.subheader("💬 Market Q&A (Ask Gemini)")
query = st.chat_input("Ask about market trends...")
if query and ai_model:
    st.write(f"Assistant: {ai_model.generate_content(query).text}")
