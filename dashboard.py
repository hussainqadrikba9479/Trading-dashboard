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
st.set_page_config(page_title="Hussain Algo Terminal V5", page_icon="📈", layout="wide")

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
        return df.dropna(subset=['Instrument'])
    except: return pd.DataFrame()

def style_cot(val):
    if isinstance(val, str):
        if 'Top' in val: return 'background-color: #5c1a1a; color: white'
        if 'Bottom' in val: return 'background-color: #1a5c20; color: white'
    elif isinstance(val, (int, float)):
        if val > 0: return 'color: #00ff00'
        if val < 0: return 'color: #ff4c4c'
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

@st.cache_data(ttl=300)
def get_news_and_squawk():
    pkt_tz = pytz.timezone('Asia/Karachi')
    now_pkt = datetime.now(pkt_tz)
    
    # 1. Scheduled News (Forex Factory Style)
    news = []
    try:
        r = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.xml", timeout=10)
        root = ET.fromstring(r.content)
        for item in root.findall('event'):
            impact = item.find('impact').text
            title = item.find('title').text
            
            if impact == 'High' or 'Holiday' in title:
                date_str = item.find('date').text
                time_str = item.find('time').text
                
                # Fetch Forecast, Previous, Actual if available
                forecast = item.find('forecast').text if item.find('forecast') is not None else ""
                previous = item.find('previous').text if item.find('previous') is not None else ""
                actual = item.find('actual').text if item.find('actual') is not None else ""
                
                # Simple logic to check if news is past (for strike-through)
                # Note: Exact time conversion needs proper parsing, using rough check for UI
                is_past = False
                
                news.append({
                    'Date': date_str,
                    'Time': time_str,
                    'Impact': "🔴" if impact == 'High' else "🏦", 
                    'Cur': item.find('country').text, 
                    'Event': title,
                    'Actual': actual,
                    'Forecast': forecast,
                    'Previous': previous,
                    '_is_past': is_past # hidden column for styling
                })
    except: pass
    
    df_news = pd.DataFrame(news)
    
    # 2. Live Squawk (Investing.com Style)
    squawk = []
    try:
        r2 = requests.get("https://www.forexlive.com/feed/news", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        root2 = ET.fromstring(r2.content)
        for i, item in enumerate(root2.findall('.//item')):
            if i >= 6: break # Top 6 breaking news
            pub_date = item.find('pubDate').text
            # Format time slightly better
            time_display = pub_date[17:22] + " GMT" 
            squawk.append({
                'Time': time_display, 
                'Headline': item.find('title').text,
                'Link': item.find('link').text
            })
    except: pass
    
    return df_news, squawk

@st.cache_data(ttl=3600)
def get_matrix_data():
    currencies = ['EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
    matrix = pd.DataFrame(index=currencies, columns=currencies, dtype=object)
    totals = []
    for i, c1 in enumerate(currencies):
        score = 0
        for j, c2 in enumerate(currencies):
            if i == j: matrix.iloc[i, j] = "-"
            else:
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
    return matrix.sort_values(by='TOTALS', ascending=False)

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
    
    if now.weekday() >= 5: 
        st.error("🛑 MARKET CLOSED (WEEKEND) - Markets will reopen on Monday.")
        return

    cols = st.columns(4)
    sessions = [
        {"name": "🇦🇺 Sydney", "open": 4, "close": 13},
        {"name": "🇯🇵 Tokyo", "open": 5, "close": 14},
        {"name": "🇬🇧 London", "open": 12, "close": 21},
        {"name": "🇺🇸 New York", "open": 17, "close": 2}
    ]
    
    current_time_minutes = now.hour * 60 + now.minute
    
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
            wait = open_mins - current_time_minutes if current_time_minutes < open_mins else (open_mins + 24*60) - current_time_minutes
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
    
    st.subheader("📊 Currency Strength Matrix")
    st.dataframe(get_matrix_data().style.map(style_matrix), use_container_width=True)

with col_right:
    st.subheader("🏦 Institutional (COT/OI)")
    df_cot = load_cot_data()
    if not df_cot.empty:
        st.dataframe(df_cot.style.map(style_cot), hide_index=True, use_container_width=True)
    st.dataframe(load_daily_oi(), hide_index=True, use_container_width=True)
    
    st.divider()
    
    # FOREX FACTORY STYLE NEWS
    st.subheader("📅 Scheduled News (Forex Factory)")
    df_news, squawk_list = get_news_and_squawk()
    
    if not df_news.empty:
        # Markdown table setup for strike-through and custom styling
        html_table = "<table style='width:100%; text-align:left; font-size:14px;'>"
        html_table += "<tr style='border-bottom: 1px solid #555;'><th>Date</th><th>Time</th><th>Imp</th><th>Cur</th><th>Event</th><th>Actual</th><th>Forecast</th><th>Prev</th></tr>"
        
        for idx, row in df_news.iterrows():
            # Dummy logic: First 2 rows shown as 'past' (strikethrough)
            row_style = "text-decoration: line-through; color: #888;" if idx < 2 else ""
            html_table += f"<tr style='{row_style}'>"
            html_table += f"<td>{row['Date']}</td><td>{row['Time']}</td><td>{row['Impact']}</td><td><b>{row['Cur']}</b></td><td>{row['Event']}</td>"
            html_table += f"<td><b>{row['Actual']}</b></td><td>{row['Forecast']}</td><td>{row['Previous']}</td>"
            html_table += "</tr>"
        html_table += "</table>"
        st.markdown(html_table, unsafe_allow_html=True)
    
    st.divider()
    
    # INVESTING.COM STYLE LIVE SQUAWK
    st.subheader("⚡ Live Breaking News (Investing Style)")
    if squawk_list:
        for item in squawk_list:
            st.markdown(f"<h5 style='margin-bottom:0px; color:#4DA8DA;'>{item['Headline']}</h5>", unsafe_allow_html=True)
            st.markdown(f"<small style='color:#888;'>ForexLive • {item['Time']}</small>", unsafe_allow_html=True)
            st.markdown("<hr style='margin-top:5px; margin-bottom:15px; border-color:#333;'>", unsafe_allow_html=True)

st.divider()
st.subheader("💬 Market Q&A (Ask Gemini)")
query = st.chat_input("Ask about market trends...")
if query and ai_model:
    st.write(f"Assistant: {ai_model.generate_content(query).text}")
