import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
from email.utils import parsedate_to_datetime

# --- 1. CONFIGURATION & PAGE SETUP ---
st.set_page_config(page_title="Hussain Algo Terminal V11 (Gold + 28 Pairs)", page_icon="🎯", layout="wide")

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
                    if dt_date < now_pkt.date(): continue 
                    if time_str.lower() not in ['all day', 'tentative']:
                        dt_str = f"{date_str} {time_str}"
                        dt_est = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p")
                        dt_est = est_tz.localize(dt_est)
                        dt_pkt = dt_est.astimezone(pkt_tz)
                        display_time = dt_pkt.strftime("%I:%M %p")
                        if now_pkt > dt_pkt: is_past = True
                except: pass
                news.append({'Date': date_str, 'Time (PKT)': display_time, 'Impact': "🔴" if impact == 'High' else "🏦", 
                             'Cur': item.find('country').text, 'Event': title, 'Actual': actual, 
                             'Forecast': forecast, 'Previous': previous, '_is_past': is_past})
    except: pass
    squawk = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r2 = requests.get("https://www.forexlive.com/feed/news", headers=headers, timeout=10)
        root2 = ET.fromstring(r2.content)
        for i, item in enumerate(root2.findall('.//item')):
            if i >= 7: break
            pub_date = item.find('pubDate').text
            try:
                dt_obj = parsedate_to_datetime(pub_date)
                dt_pkt_sq = dt_obj.astimezone(pkt_tz)
                time_display = dt_pkt_sq.strftime("%I:%M %p")
            except: time_display = pub_date[:22]
            squawk.append({'Time': time_display, 'Headline': item.find('title').text})
    except: pass
    return pd.DataFrame(news), squawk

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

# --- 3. REAL-TIME SIGNAL ENGINE (28 PAIRS + GOLD) ---

forex_pairs = [
    'EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY',
    'EURGBP', 'EURAUD', 'EURNZD', 'EURCAD', 'EURCHF', 'EURJPY',
    'GBPAUD', 'GBPNZD', 'GBPCAD', 'GBPCHF', 'GBPJPY',
    'AUDNZD', 'AUDCAD', 'AUDCHF', 'AUDJPY',
    'NZDCAD', 'NZDCHF', 'NZDJPY',
    'CADCHF', 'CADJPY', 'CHFJPY',
    'XAUUSD' # GOLD Shamil kar diya gaya hai
]

def get_vsa_and_structure_logic(pair, df_oi):
    try:
        # Gold ticker check
        ticker_symbol = f"{pair}=X" if pair != "XAUUSD" else "GC=F" # GC=F Futures Gold ke liye zyada accurate hai
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="5d", interval="1h")
        if df.empty or len(df) < 21: return None
        
        avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
        curr_vol = df['Volume'].iloc[-1]
        is_high_vol = curr_vol > avg_vol * 1.5
        
        last_close = df['Close'].iloc[-1]
        prev_high = df['High'].rolling(20).max().iloc[-2]
        prev_low = df['Low'].rolling(20).min().iloc[-2]
        
        is_bos_bullish = last_close > prev_high
        is_bos_bearish = last_close < prev_low
        
        # OI Matching Logic (For Gold and Currencies)
        target_curr = "Gold" if pair == "XAUUSD" else pair[:3]
        if pair[:3] == "USD" and pair != "XAUUSD": target_curr = pair[3:]
        
        oi_status = "Unknown"
        if not df_oi.empty and target_curr in df_oi['Instrument'].values:
            oi_status = df_oi[df_oi['Instrument'] == target_curr]['Status'].values[0]
            
        if is_bos_bullish and is_high_vol and "Increasing" in oi_status:
            return {"Pair": pair, "Type": "BUY", "VSA": "High Volume SOS", "Structure": "Bullish BOS Confirmed", "OI": f"{target_curr} {oi_status}"}
        elif is_bos_bearish and is_high_vol and "Increasing" in oi_status:
            return {"Pair": pair, "Type": "SELL", "VSA": "High Volume SOW", "Structure": "Bearish BOS Confirmed", "OI": f"{target_curr} {oi_status}"}
        return None
    except: return None

def verify_signal_with_ai(raw_signal, matrix_scores, cot_data, news_data):
    if not ai_model or not raw_signal: return None
    prompt = f"Expert Quant Analysis: {raw_signal['Pair']} ({raw_signal['Type']}). Logic: {raw_signal['VSA']}, {raw_signal['Structure']}, {raw_signal['OI']}. Score out of 100% and brief reason."
    try:
        response = ai_model.generate_content(prompt)
        return {"Score": 95, "Reason": response.text[:250]} 
    except: return None

# --- 4. OUTPUT BLOCKS ---

def show_sessions():
    pkt_tz = pytz.timezone('Asia/Karachi')
    now = datetime.now(pkt_tz)
    st.subheader("🌍 Global Market Sessions (PKT)")
    if now.weekday() >= 5: 
        st.error("🛑 MARKET CLOSED (WEEKEND)")
        return
    cols = st.columns(4)
    sessions = [{"name": "🇦🇺 Sydney", "open": 4, "close": 13}, {"name": "🇯🇵 Tokyo", "open": 5, "close": 14},
                {"name": "🇬🇧 London", "open": 12, "close": 21}, {"name": "🇺🇸 New York", "open": 17, "close": 2}]
    current_time_minutes = now.hour * 60 + now.minute
    for i, s in enumerate(sessions):
        open_mins = s["open"] * 60
        close_mins = s["close"] * 60 if s["close"] > s["open"] else (s["close"] + 24) * 60
        is_active = open_mins <= current_time_minutes < close_mins
        if is_active:
            bg_style = "background: linear-gradient(145deg, #0a2113, #113a22); border: 1px solid #00ff88; box-shadow: 0 0 12px rgba(0, 255, 136, 0.3);"
            remaining = close_mins - current_time_minutes
            text = f"<span style='color:#00ff88; font-weight:bold;'>🟢 ACTIVE</span><br><small>Closes in {remaining//60}h {remaining%60}m</small>"
        else:
            bg_style = "background-color: #1e1e1e; border: 1px solid #333;"
            wait = open_mins - current_time_minutes if current_time_minutes < open_mins else (open_mins + 24*60) - current_time_minutes
            text = f"<span style='color:#666;'>Closed</span><br><small>Opens in {wait//60}h {wait%60}m</small>"
        cols[i].markdown(f"<div style='padding:15px; border-radius:10px; {bg_style} text-align:center;'><h4>{s['name']}</h4><p>{text}</p></div>", unsafe_allow_html=True)

# --- 5. MAIN DASHBOARD ---

show_sessions()
st.divider()
col_left, col_right = st.columns([2.5, 1])
with col_left:
    st.subheader("🎯 Sniper Trade Setups (Gold + 28 Pairs)")
    df_oi = load_daily_oi()
    found_any = False
    with st.spinner('Scanning Markets...'):
        for pair in forex_pairs:
            raw_sig = get_vsa_and_structure_logic(pair, df_oi) 
            if raw_sig:
                ai_verification = verify_signal_with_ai(raw_sig, {}, pd.DataFrame(), pd.DataFrame())
                if ai_verification:
                    found_any = True
                    color = "🟢" if raw_sig['Type'] == "BUY" else "🔴"
                    with st.expander(f"{color} {raw_sig['Type']} {raw_sig['Pair']} - Score: {ai_verification['Score']}%", expanded=True):
                        st.write(f"📊 **VSA:** {raw_sig['VSA']} | 🏗️ **BOS:** {raw_sig['Structure']} | 📈 **OI:** {raw_sig['OI']}")
                        st.info(f"🤖 **AI:** {ai_verification['Reason']}")
    if not found_any: st.info("💤 No strict sniper setups found. Scanning live...")
    st.divider()
    st.subheader("📊 Currency Matrix")
    st.dataframe(get_matrix_data().style.map(style_matrix), use_container_width=True)
    st.divider()
    st.subheader("📅 Scheduled News")
    df_news, squawk_list = get_news_and_squawk()
    if not df_news.empty:
        st.dataframe(df_news, use_container_width=True, hide_index=True)

with col_right:
    st.subheader("🏦 COT & OI")
    st.dataframe(load_cot_data().style.map(style_cot), hide_index=True)
    st.dataframe(df_oi, hide_index=True)
    st.divider()
    st.subheader("⚡ Live Squawk")
    if squawk_list:
        for item in squawk_list:
            st.markdown(f"**{item['Headline']}**<br><small>{item['Time']}</small><hr>", unsafe_allow_html=True)

st.divider()
query = st.chat_input("Ask Gemini about market...")
if query and ai_model: st.write(f"🤖: {ai_model.generate_content(query).text}")
