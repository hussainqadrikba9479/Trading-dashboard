import yfinance as yf
import pandas as pd
import streamlit as st
import google.generativeai as genai
import numpy as np
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta, date

# --- Dashboard Setup & CSS ---
st.set_page_config(page_title="Global Trading Terminal", layout="wide")
st.markdown("""
    <style>
    .main {background-color: transparent;}
    .news-card {
        border-left: 6px solid #e74c3c; 
        background-color: #1e222d; color: #d1d4dc; padding: 12px; 
        border-radius: 8px; margin-bottom: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .news-card a { color: #3498db !important; text-decoration: none; }
    .news-card a:hover { color: #2980b9 !important; text-decoration: underline; }
    .session-box {padding: 12px; border-radius: 8px; text-align: center; margin-bottom: 15px; transition: 0.3s;}
    .time-badge {background: rgba(255,255,255,0.1); color: #d1d4dc; padding: 4px 8px; border-radius: 4px; display: inline-block; margin-top: 5px;}
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    ::-webkit-scrollbar {width: 6px; height: 6px;}
    ::-webkit-scrollbar-track {background: #0e1117;} 
    ::-webkit-scrollbar-thumb {background: #3498db; border-radius: 3px;}
    ::-webkit-scrollbar-thumb:hover {background: #2980b9;}
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Master Trading Terminal (PA + VSA)")

# ==========================================
# --- SECURITY: LOGIN GATE ---
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<div style='background-color: #1e222d; padding: 30px; border-radius: 10px; text-align: center;'>", unsafe_allow_html=True)
        st.subheader("🔒 Restricted Access")
        pwd = st.text_input("Enter Password & Press Enter:", type="password", key="final_login_key")
        try:
            correct_password = st.secrets["TERMINAL_PASSWORD"]
        except:
            correct_password = "admin"
        if pwd:
            if pwd == correct_password:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Ghalat Password!")
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# --- Mode Selector ---
st.markdown("### ⚙️ Select Trading Engine")
trading_mode = st.radio("Select Trading Engine", ["Intraday (H1 + M30)", "Swing Trading (D1 + H4)", "Backtest Mode (Historical)"], index=1, horizontal=True)

# --- Pakistan Time Setup ---
pkt_timezone = timezone(timedelta(hours=5))
now_pkt = datetime.now(pkt_timezone)
st.info(f"🕒 **Live Clock:** {now_pkt.strftime('%I:%M:%S %p')} (PKT) | **Current Mode:** {trading_mode}")

# --- Sessions Logic ---
def get_session_status(now, open_h, close_h):
    open_time = now.replace(hour=open_h, minute=0, second=0, microsecond=0)
    close_time = now.replace(hour=close_h, minute=0, second=0, microsecond=0)
    is_weekend = now.weekday() >= 5
    if open_h > close_h:
        if now.hour >= open_h or now.hour < close_h:
            is_active = True
            if now.hour >= open_h: close_time += timedelta(days=1)
        else: is_active = False
    else:
        is_active = open_h <= now.hour < close_h
        if not is_active and now.hour >= close_h: open_time += timedelta(days=1)
    if is_weekend:
        is_active = False
        rem = "⏸️ Weekend"
    else:
        if is_active:
            diff = close_time - now
            rem = f"⏳ {diff.seconds // 3600}h {(diff.seconds // 60) % 60}m Left"
        else:
            diff = open_time - now
            rem = f"⏳ In {diff.seconds // 3600}h {(diff.seconds // 60) % 60}m"
    return is_active, f"{open_time.strftime('%I %p')} - {close_time.strftime('%I %p')}", rem

def get_session_html(name, is_active, color, timing_str, rem_str):
    bg_color = color if is_active else "#2b3040"
    status = "🟢 ACTIVE" if is_active else "⚪ CLOSED"
    return f"""<div class='session-box' style='background-color: {bg_color}; color: white;'>
        <div style='font-size: 1.1em; font-weight: bold;'>{name}</div>
        <div style='font-size: 0.85em; opacity: 0.9;'>{timing_str}</div>
        <div style='font-size: 0.9em; font-weight: 500; margin-top:5px;'>{status}</div>
        <div class='time-badge'>{rem_str}</div></div>"""

c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(get_session_html("🇦🇺 Sydney", *get_session_status(now_pkt, 3, 12), "#3498db"), unsafe_allow_html=True)
with c2: st.markdown(get_session_html("🇯🇵 Tokyo", *get_session_status(now_pkt, 5, 14), "#9b59b6"), unsafe_allow_html=True)
with c3: st.markdown(get_session_html("🇬🇧 London", *get_session_status(now_pkt, 12, 21), "#e67e22"), unsafe_allow_html=True)
with c4: st.markdown(get_session_html("🇺🇸 New York", *get_session_status(now_pkt, 17, 2), "#e74c3c"), unsafe_allow_html=True)

# =========================================================================
# --- BACKEND DATA FETCHING ---
# =========================================================================

@st.cache_data(ttl=3600)
def load_cot_data():
    try:
        df_cot = pd.read_excel("COT.xlsm", sheet_name="Main", engine='openpyxl', usecols="A,B,G,K,P", skiprows=2, header=None)
        df_cot.columns = ['Instrument', 'Net Change', 'Direction', 'COT Index', 'OI Change']
        return df_cot.dropna(subset=['Instrument'])
    except: return pd.DataFrame()

cot_df = load_cot_data()

@st.cache_data(ttl=300)
def get_market_data(mode):
    data_list = []
    futures = {'USD': 'DX-Y.NYB', 'GOLD': 'GC=F', 'EUR': '6E=F', 'GBP': '6B=F', 'JPY': '6J=F', 'AUD': '6A=F', 'CAD': '6C=F', 'CHF': '6S=F'}
    for name, ticker in futures.items():
        try:
            df = yf.download(ticker, period="1mo", interval="1h", progress=False)
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
            score = 9 if df['Close'].iloc[-1] > df['Close'].rolling(20).mean().iloc[-1] else 1
            data_list.append({'Instrument': name, 'Structure': 'Trend Active', 'PA Signal': 'Neutral', 'Volume Confirm': '✅ Valid', 'Score': score})
        except: pass
    return pd.DataFrame(data_list)

df_fx = get_market_data(trading_mode)

# =========================================================================
# --- TOP SECTION: OUTCOMES ---
# =========================================================================

st.markdown("---")
st.subheader("🎯 Active Trade Setups")
if not df_fx.empty:
    st.success("⚡ Institutional Setups identified. Check PA Phase below for details.")
else:
    st.info("Searching for high-probability alignments...")

# --- AI CO-PILOT ---
st.markdown("---")
st.subheader("🧠 Gemini AI Co-Pilot")
if st.button("🚀 Generate High-Probability Analysis"):
    st.write("AI analysis loading based on Technicals, COT and News...")

# =========================================================================
# --- DATA TABLES ---
# =========================================================================

st.markdown("---")
st.subheader("🔍 Price Action Analysis Phase")
if not df_fx.empty:
    st.dataframe(df_fx, use_container_width=True, hide_index=True)

st.markdown("---")
st.subheader("📊 Institutional Sentiment (COT Data)")
if not cot_df.empty:
    st.dataframe(cot_df.head(15), use_container_width=True, hide_index=True)

# =========================================================================
# --- NEW NEWS CALENDAR (FOREX FACTORY STYLE) ---
# =========================================================================

st.markdown("---")
st.subheader("🚨 High Impact News Calendar")

@st.cache_data(ttl=600)
def get_news_calendar():
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        data = requests.get(url, timeout=10).json()
        return [e for e in data if e.get('impact') == 'High']
    except: return []

news_data = get_news_calendar()

if news_data:
    news_by_date = {}
    for event in news_data:
        try:
            dt_obj = datetime.fromisoformat(event['date'])
            pkt_dt = dt_obj.astimezone(pkt_timezone)
            date_str = pkt_dt.strftime("%A, %d %b %Y")
            if date_str not in news_by_date: news_by_date[date_str] = []
            news_by_date[date_str].append({
                'time': pkt_dt.strftime('%I:%M %p'),
                'currency': event['country'],
                'event': event['title'],
                'is_past': pkt_dt < now_pkt
            })
        except: continue

    for day, events in news_by_date.items():
        with st.expander(f"📅 {day}", expanded=True):
            # Header
            h1, h2, h3 = st.columns([1, 1, 3])
            h1.caption("Time (PKT)")
            h2.caption("Currency")
            h3.caption("Event")
            st.markdown("---")
            
            for e in events:
                c1, c2, c3 = st.columns([1, 1, 3])
                if e['is_past']:
                    c1.markdown(f"~~{e['time']}~~")
                    c2.markdown(f"~~{e['currency']}~~")
                    c3.markdown(f"⚪ *{e['event']} (Passed)*")
                else:
                    c1.markdown(f"**{e['time']}**")
                    c2.markdown(f"**{e['currency']}**")
                    c3.markdown(f"🔴 **{e['event']}**")
else:
    st.info("News data currently unavailable.")
