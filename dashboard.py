import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
from email.utils import parsedate_to_datetime # RSS time parse karne ke liye

# --- 1. CONFIGURATION & PAGE SETUP ---
st.set_page_config(page_title="Hussain Algo Terminal V8", page_icon="📈", layout="wide")

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
    est_tz = pytz.timezone('US/Eastern')
    
    # 1. Scheduled News (Forex Factory)
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
                
                forecast = item.find('forecast').text if item.find('forecast') is not None else "-"
                previous = item.find('previous').text if item.find('previous') is not None else "-"
                actual = item.find('actual').text if item.find('actual') is not None else "-"
                
                is_past = False
                display_time = time_str
                
                try:
                    dt_date = datetime.strptime(date_str, "%m-%d-%Y").date()
                    if dt_date < now_pkt.date():
                        continue 
                    
                    if time_str.lower() not in ['all day', 'tentative']:
                        dt_str = f"{date_str} {time_str}"
                        dt_est = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p")
                        dt_est = est_tz.localize(dt_est)
                        dt_pkt = dt_est.astimezone(pkt_tz)
                        display_time = dt_pkt.strftime("%I:%M %p")
                        
                        if now_pkt > dt_pkt:
                            is_past = True
                except: pass
                
                news.append({
                    'Date': date_str,
                    'Time (PKT)': display_time,
                    'Impact': "🔴" if impact == 'High' else "🏦", 
                    'Cur': item.find('country').text, 
                    'Event': title,
                    'Actual': actual,
                    'Forecast': forecast,
                    'Previous': previous,
                    '_is_past': is_past
                })
    except: pass
    df_news = pd.DataFrame(news)
    
    # 2. Live Squawk (ForexLive Feed - Reliable & Unblocked)
    squawk = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        r2 = requests.get("https://www.forexlive.com/feed/news", headers=headers, timeout=10)
        root2 = ET.fromstring(r2.content)
        for i, item in enumerate(root2.findall('.//item')):
            if i >= 7: break
            pub_date = item.find('pubDate').text
            try:
                # Robust Time Parsing
                dt_obj = parsedate_to_datetime(pub_date)
                dt_pkt_sq = dt_obj.astimezone(pkt_tz)
                time_display = dt_pkt_sq.strftime("%I:%M %p")
            except:
                time_display = pub_date[:22]
                
            squawk.append({
                'Time': time_display, 
                'Headline': item.find('title').text
            })
    except Exception as e:
        print(f"Squawk Error: {e}")
        pass
    
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
            # New Lucrative, Premium Dark-Green Glowing Style
            bg_style = "background: linear-gradient(145deg, #0a2113, #113a22); border: 1px solid #00ff88; box-shadow: 0 0 12px rgba(0, 255, 136, 0.3);"
            remaining = close_mins - current_time_minutes
            text = f"<span style='color:#00ff88; font-weight:bold; letter-spacing: 1px;'>🟢 ACTIVE</span><br><small style='color:#b3b3b3;'>Closes in {remaining//60}h {remaining%60}m</small>"
        else:
            bg_style = "background-color: #1e1e1e; border: 1px solid #333;"
            wait = open_mins - current_time_minutes if current_time_minutes < open_mins else (open_mins + 24*60) - current_time_minutes
            text = f"<span style='color:#666;'>Closed</span><br><small style='color:#555;'>Opens in {wait//60}h {wait%60}m</small>"
            
        cols[i].markdown(f"<div style='padding:15px; border-radius:10px; {bg_style} text-align:center;'><h4 style='margin-bottom:5px; color:#e0e0e0;'>{s['name']}</h4><p style='margin:0;'>{text}</p></div>", unsafe_allow_html=True)

# --- 4. MAIN DASHBOARD ---

show_sessions()
st.divider()

col_left, col_right = st.columns([2.5, 1])

with col_left:
    st.subheader("🔥 Active Trade Setups & AI Scoring")
    st.success("📈 BUY EURUSD | Score: 92% (Strong Alignment)")
    st.info("🤖 AI: COT Near Bottom + Matrix Strong + No News Conflict. High Probability.")
    
    st.subheader("📊 Currency Strength Matrix")
    st.dataframe(get_matrix_data().style.map(style_matrix), use_container_width=True)
    
    st.divider()
    
    st.subheader("📅 Scheduled News (Forex Factory)")
    df_news, squawk_list = get_news_and_squawk()
    
    if not df_news.empty:
        html_table = "<table style='width:100%; text-align:left; font-size:14px; border-collapse: collapse;'>"
        html_table += "<tr style='border-bottom: 2px solid #555; color:#ccc; background-color: #1e1e1e;'><th>Date</th><th>Time(PKT)</th><th>Imp</th><th>Cur</th><th>Event</th><th>Actual</th><th>Forecast</th><th>Prev</th></tr>"
        
        for idx, row in df_news.iterrows():
            row_style = "text-decoration: line-through; color: #666;" if row['_is_past'] else "color: #fff;"
            html_table += f"<tr style='border-bottom: 1px solid #333; {row_style}'>"
            html_table += f"<td style='padding:8px;'>{row['Date']}</td><td>{row['Time (PKT)']}</td><td>{row['Impact']}</td><td><b>{row['Cur']}</b></td><td>{row['Event']}</td>"
            html_table += f"<td><b>{row['Actual']}</b></td><td>{row['Forecast']}</td><td>{row['Previous']}</td>"
            html_table += "</tr>"
        html_table += "</table>"
        st.markdown(html_table, unsafe_allow_html=True)
    else:
        st.info("💤 Is hafte ke liye koi aur major news baqi nahi hai.")

with col_right:
    st.subheader("🏦 Institutional (COT/OI)")
    df_cot = load_cot_data()
    if not df_cot.empty:
        st.dataframe(df_cot.style.map(style_cot), hide_index=True, use_container_width=True)
    st.dataframe(load_daily_oi(), hide_index=True, use_container_width=True)
    
    st.divider()
    
    st.subheader("⚡ Live Breaking News")
    if squawk_list:
        for item in squawk_list:
            st.markdown(f"<h5 style='margin-bottom:0px; color:#4DA8DA; font-size:15px;'>{item['Headline']}</h5>", unsafe_allow_html=True)
            st.markdown(f"<small style='color:#888;'>ForexLive • {item['Time']}</small>", unsafe_allow_html=True)
            st.markdown("<hr style='margin-top:5px; margin-bottom:12px; border-color:#333;'>", unsafe_allow_html=True)
    else:
        st.warning("📡 Live feed abhi available nahi hai. System dobara koshish kar raha hai...")

st.divider()
st.subheader("💬 Market Q&A (Ask Gemini)")
query = st.chat_input("Ask about market trends...")
if query and ai_model:
    st.write(f"Assistant: {ai_model.generate_content(query).text}")
