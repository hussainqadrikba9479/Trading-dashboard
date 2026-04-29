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
st.set_page_config(page_title="Hussain Algo Terminal V4", page_icon="📈", layout="wide")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    ai_model = genai.GenerativeModel('gemini-pro')
except:
    ai_model = None

# --- 2. DATA ENGINES ---

@st.cache_data(ttl=3600)
def load_cot_data():
    try:
        df = pd.read_excel("COT.xlsm", sheet_name="Main", engine='openpyxl', skiprows=2)
        df = df.iloc[:, [0, 1, 6, 10, 11]]
        df.columns = ['Instrument', 'Net Change', 'Direction', 'COT_Index_NComm', 'COT_Index_Comm']
        df = df.dropna(subset=['Instrument'])
        return df
    except: return pd.DataFrame()

# COT Table ko Color karne ka function
def style_cot(val):
    if isinstance(val, str):
        if 'Top' in val: return 'background-color: #5c1a1a; color: white'  # Red for Top
        if 'Bottom' in val: return 'background-color: #1a5c20; color: white' # Green for Bottom
    elif isinstance(val, (int, float)):
        if val > 0: return 'color: #00ff00' # Green text for positive
        if val < 0: return 'color: #ff4c4c' # Red text for negative
    return ''

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

@st.cache_data(ttl=600)
def get_news_and_squawk():
    pkt_tz = pytz.timezone('Asia/Karachi')
    now_pkt = datetime.now(pkt_tz)
    
    # 1. Scheduled News (Forex Factory)
    news = []
    try:
        r = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.xml", timeout=10)
        root = ET.fromstring(r.content)
        for item in root.findall('event'):
            impact = item.find('impact').text
            title = item.find('title').text
            date_str = item.find('date').text
            time_str = item.find('time').text
            
            if impact == 'High' or 'Holiday' in title:
                # Time logic (rough estimation for EST to PKT display)
                news.append({
                    'Date': date_str,
                    'Time': time_str,
                    'Type': "🔴 High" if impact == 'High' else "🏦 Holiday", 
                    'Curr': item.find('country').text, 
                    'Event': title
                })
    except: pass
    
    df_news = pd.DataFrame(news)
    
    # 2. Live Squawk (ForexLive)
    squawk = []
    try:
        r2 = requests.get("https://www.forexlive.com/feed/news", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        root2 = ET.fromstring(r2.content)
        for i, item in enumerate(root2.findall('.//item')):
            if i >= 5: break
            squawk.append({'Time': item.find('pubDate').text[17:22], 'Headline': item.find('title').text})
    except: pass
    
    return df_news, pd.DataFrame(squawk)

@st.cache_data(ttl=3600)
def get_matrix_data():
    currencies = ['EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
    matrix = pd.DataFrame(index=currencies, columns=currencies, dtype=object)
    
    # Demo logic for Matrix matching "Markets Made Clear" style
    # Asal production mein Yahoo Finance lagayenge, yahan UI structure design kiya hai
    totals = []
    for i, c1 in enumerate(currencies):
        score = 0
        for j, c2 in enumerate(currencies):
            if i == j:
                matrix.iloc[i, j] = "-"
            else:
                # Randomize trend for UI check (Change to real SMA logic later)
                val = np.random.choice([1, -1, 0])
                if val == 1: 
                    matrix.iloc[i, j] = "🟢 ⬆"
                    score += 1
                elif val == -1: 
                    matrix.iloc[i, j] = "🔴 ⬇"
                    score -= 1
                else: 
                    matrix.iloc[i, j] = "🟡 ↔"
        totals.append(score)
        
    matrix['TOTALS'] = totals
    matrix = matrix.sort_values(by='TOTALS', ascending=False)
    return matrix

# Matrix ko Total Colors dene ka function
def style_matrix(val):
    if val == "-": return 'background-color: #333333; color: #333333'
    if isinstance(val, (int, float)):
        if val > 0: return 'background-color: #1a5c20; color: white; font-weight: bold;'
        if val < 0: return 'background-color: #5c1a1a; color: white; font-weight: bold;'
    return ''

# --- 3. OUTPUT BLOCKS ---

def show_sessions():
    pkt_tz = pytz.timezone('Asia/Karachi')
    now = datetime.now(pkt_tz)
    st.subheader("🌍 Global Market Sessions (PKT)")
    
    if now.weekday() >= 5: # 5=Sat, 6=Sun
        st.error("🛑 MARKET CLOSED (WEEKEND) - Markets will reopen on Monday.")
        return

    cols = st.columns(4)
    sessions = [
        {"name": "🇦🇺 Sydney", "open": 4, "close": 13},
        {"name": "🇯🇵 Tokyo", "open": 5, "close": 14},
        {"name": "🇬🇧 London", "open": 12, "close": 21},
        {"name": "🇺🇸 New York", "open": 17, "close": 2}
    ]
    
    h = now.hour
    m = now.minute
    current_time_minutes = h * 60 + m
    
    for i, s in enumerate(sessions):
        open_mins = s["open"] * 60
        close_mins = s["close"] * 60 if s["close"] > s["open"] else (s["close"] + 24) * 60
        is_active = open_mins <= current_time_minutes < close_mins
        
        if is_active:
            color = "#1E5128"
            remaining = close_mins - current_time_minutes
            text = f"🟢 ACTIVE<br><small>Closes in {remaining//60}h {remaining%60}m</small>"
        else:
            color = "#333333"
            if current_time_minutes < open_mins:
                wait = open_mins - current_time_minutes
            else:
                wait = (open_mins + 24*60) - current_time_minutes
            text = f"Closed<br><small>Opens in {wait//60}h {wait%60}m</small>"
            
        cols[i].markdown(f"<div style='padding:15px; border-radius:10px; background-color:{color}; text-align:center;'><h4>{s['name']}</h4><p>{text}</p></div>", unsafe_allow_html=True)

# --- 4. MAIN DASHBOARD ---

show_sessions()
st.divider()

col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("🔥 Active Trade Setups & AI Scoring")
    st.success("📈 BUY EURUSD | Score: 92% (Strong Alignment)")
    st.info("🤖 AI: COT Near Bottom + Matrix Strong + No News Conflict. High Probability.")
    
    st.subheader("📊 Currency Strength Matrix (Auto-Sorted)")
    df_matrix = get_matrix_data()
    st.dataframe(df_matrix.style.map(style_matrix), use_container_width=True)

with col_right:
    st.subheader("🏦 Institutional (COT/OI)")
    df_cot = load_cot_data()
    if not df_cot.empty:
        st.dataframe(df_cot.style.map(style_cot), hide_index=True, use_container_width=True)
    st.dataframe(load_daily_oi(), hide_index=True, use_container_width=True)
    
    st.subheader("📰 Scheduled News & Live Squawk")
    df_news, df_squawk = get_news_and_squawk()
    
    if not df_news.empty:
        # Markdown hack to show Strike-Through for past news
        st.write("**Today's Major Events:**")
        for idx, row in df_news.head(6).iterrows():
            # Dummy strike-through logic for UI (first 2 items struck through as example)
            if idx < 2: 
                st.markdown(f"~~{row['Date']} {row['Time']} | {row['Curr']} | {row['Event']}~~")
            else:
                st.markdown(f"**{row['Date']} {row['Time']} | {row['Curr']} | {row['Event']}**")
    
    if not df_squawk.empty:
        st.write("**⚡ Live Audio Squawk (Unscheduled):**")
        st.dataframe(df_squawk, hide_index=True, use_container_width=True)

st.divider()
st.subheader("💬 Market Q&A (Ask Gemini)")
query = st.chat_input("Ask about market trends...")
if query and ai_model:
    st.write(f"Assistant: {ai_model.generate_content(query).text}")
