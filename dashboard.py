import yfinance as yf
import pandas as pd
import streamlit as st
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET
import random
from datetime import datetime, timezone, timedelta
from streamlit_autorefresh import st_autorefresh

# --- 1. Dashboard Setup & Theme ---
st.set_page_config(page_title="Global Trading Terminal", layout="wide")

# --- AUTO REFRESH (Every 30 Minutes / 1,800,000 ms) ---
# Hussain Bhai, yeh ab har aadhe ghante baad data refresh karega
count = st_autorefresh(interval=1800000, limit=None, key="dashboard_refresh_30")

st.markdown("""
    <style>
    .main {background-color: transparent;}
    .news-card {border-left: 6px solid #e74c3c; background-color: #1e222d; color: #d1d4dc; padding: 12px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);}
    .session-box {padding: 12px; border-radius: 8px; text-align: center; margin-bottom: 15px; transition: 0.3s;}
    .time-badge {background: rgba(255,255,255,0.1); color: #d1d4dc; padding: 4px 8px; border-radius: 4px; display: inline-block; margin-top: 5px;}
    .psych-box {background-color: #1e222d; padding: 20px; border-radius: 10px; border-left: 5px solid #f1c40f; margin-bottom: 20px;}
    .quote-text {font-style: italic; font-size: 1.2em; color: #f1c40f;}
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    ::-webkit-scrollbar {width: 6px; height: 6px;}
    ::-webkit-scrollbar-track {background: #0e1117;} 
    ::-webkit-scrollbar-thumb {background: #3498db; border-radius: 3px;}
    </style>
""", unsafe_allow_html=True)

# --- TELEGRAM ALERT FUNCTION ---
def send_telegram_alert(message):
    try:
        bot_token = st.secrets["TELEGRAM_BOT_TOKEN"]
        chat_id = st.secrets["TELEGRAM_CHAT_ID"]
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)
    except: pass 

# Initialize Memories
if "sent_alerts" not in st.session_state: st.session_state.sent_alerts = set()
if "ai_verdicts" not in st.session_state: st.session_state.ai_verdicts = {}

# =========================================================================
# --- BACKEND DATA FUNCTIONS ---
# =========================================================================
@st.cache_data(ttl=1800) # Cache also aligned to 30 mins
def load_cot_data():
    try:
        df_cot = pd.read_excel("COT.xlsm", sheet_name="Main", engine='openpyxl', usecols="A,B,G,K,P", skiprows=2, header=None)
        df_cot.columns = ['Instrument', 'Net Change', 'Direction', 'COT Index', 'OI Change']
        return df_cot.dropna(subset=['Instrument'])
    except: return pd.DataFrame()

@st.cache_data(ttl=1800)
def load_daily_oi():
    try:
        df = pd.read_excel("Daily_OI.xlsm", sheet_name="Data", engine='openpyxl')
        df.columns = df.columns.astype(str).str.replace('\n', ' ').str.replace('\r', '')
        col_map = {'USD': 'USD', 'Euro': 'EUR', 'Pound': 'GBP', 'Australian': 'AUD', 'Zealand': 'NZD', 'Canadian': 'CAD', 'Swiss': 'CHF', 'Yen': 'JPY', 'Gold': 'GOLD'}
        oi_list = []
        for keyword, symbol in col_map.items():
            matched_col = next((col for col in df.columns if keyword.lower() in col.lower()), None)
            if matched_col:
                valid_data = pd.to_numeric(df[matched_col], errors='coerce').dropna().values
                if len(valid_data) >= 2:
                    curr_oi, prev_oi = valid_data[0], valid_data[1]
                    change = curr_oi - prev_oi
                    status = "Increasing 🟢" if change > 0 else "Decreasing 🔴"
                    oi_list.append({'Instrument': symbol, 'Current OI': int(curr_oi), 'Status': status})
        return pd.DataFrame(oi_list)
    except: return pd.DataFrame()

@st.cache_data(ttl=1800)
def get_market_data(mode):
    data_list = []
    symbols = {'USD': 'DX-Y.NYB', 'GOLD': 'GC=F', 'EUR': '6E=F', 'GBP': '6B=F', 'JPY': '6J=F', 'AUD': '6A=F', 'CAD': '6C=F', 'CHF': '6S=F'}
    interval = "1h" if "Swing" in mode else "30m"
    for name, ticker in symbols.items():
        try:
            df = yf.download(ticker, period="1mo", interval=interval, progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
            close, sma = df['Close'].iloc[-1], df['Close'].rolling(20).mean().iloc[-1]
            vol, avg_vol = df['Volume'].iloc[-1], df['Volume'].rolling(20).mean().iloc[-1]
            score = 5
            if close > sma: score = 7 if close > df['High'].iloc[-5] else 6
            else: score = 3 if close < df['Low'].iloc[-5] else 4
            vol_confirm = "✅ Vol Confirmed" if vol > avg_vol else "No Volume Confirm"
            data_list.append({'Instrument': name, 'Structure': 'Uptrend' if close > sma else 'Downtrend', 'PA Signal': 'Buy Pullback' if score >= 6 else 'Sell Pullback' if score <= 4 else 'Neutral', 'Volume Confirm': vol_confirm, 'Score': score})
        except: pass
    return pd.DataFrame(data_list)

@st.cache_data(ttl=1800)
def get_currency_matrix():
    currencies = ['EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
    matrix_df = pd.DataFrame(index=currencies, columns=currencies + ['TOTAL'])
    tickers, pairs_map = [], {}
    for i in range(len(currencies)):
        for j in range(i+1, len(currencies)):
            pair = f"{currencies[i]}{currencies[j]}=X"; tickers.append(pair); pairs_map[pair] = (currencies[i], currencies[j])
    try:
        df = yf.download(tickers, period="1mo", interval="1d", progress=False)
        closes = df['Close']
        scores = {c: 0 for c in currencies}
        for ticker in tickers:
            c1, c2 = pairs_map[ticker]
            try:
                pair_data = closes[ticker].dropna()
                curr, sma = pair_data.iloc[-1], pair_data.rolling(20).mean().iloc[-1]
                diff = (curr - sma) / sma
                if diff > 0.002: 
                    matrix_df.loc[c1, c2], matrix_df.loc[c2, c1] = '⬆', '⬇'; scores[c1] += 1; scores[c2] -= 1
                elif diff < -0.002:
                    matrix_df.loc[c1, c2], matrix_df.loc[c2, c1] = '⬇', '⬆'; scores[c1] -= 1; scores[c2] += 1
                else: matrix_df.loc[c1, c2], matrix_df.loc[c2, c1] = '↔', '↔'
            except: pass
        for c in currencies:
            matrix_df.loc[c, c] = ''; matrix_df.loc[c, 'TOTAL'] = scores[c]
        return matrix_df.sort_values(by='TOTAL', ascending=False)
    except: return pd.DataFrame()

# Initialize AI
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    ai_model = genai.GenerativeModel('models/gemini-pro')
except:
    api_key = None
    ai_model = None

# --- Initialize Tabs ---
tab_terminal, tab_risk, tab_psych = st.tabs(["🦅 Trading Terminal", "💰 Risk Manager", "🧠 Mindset & Psychology"])

# =========================================================================
# --- TAB 1: TRADING TERMINAL ---
# =========================================================================
with tab_terminal:
    st.title("🦅 Master Session-Ready Terminal")
    trading_mode = st.radio("⚙️ Select Trading Engine", ["Intraday (H1 + M30)", "Swing Trading (D1 + H4)"], index=1, horizontal=True)

    pkt_timezone = timezone(timedelta(hours=5))
    now_pkt = datetime.now(pkt_timezone)
    st.info(f"🕒 **Live Clock:** {now_pkt.strftime('%I:%M:%S %p')} (PKT) | **Refresh Cycle:** Every 30 Mins")

    # [Session Status Display - Same as before]
    def get_session_status(now, open_h, close_h):
        open_time = now.replace(hour=open_h, minute=0, second=0, microsecond=0)
        close_time = now.replace(hour=close_h, minute=0, second=0, microsecond=0)
        is_weekend = now.weekday() >= 5
        if open_h > close_h:
            if now.hour >= open_h or now.hour < close_h:
                is_active = True
                if now.hour >= open_h: close_time += timedelta(days=1)
            else: is_active = False
        else: is_active = open_h <= now.hour < close_h
        if is_weekend: return False, "Market Closed", "⏸️ Weekend"
        diff = (close_time - now) if is_active else (open_time - now)
        rem = f"⏳ {'Closes' if is_active else 'Opens'} in {diff.seconds // 3600}h {(diff.seconds // 60) % 60}m"
        return is_active, f"{open_time.strftime('%I %p')} - {close_time.strftime('%I %p')}", rem

    def get_session_html(name, is_active, color, timing_str, rem_str):
        bg_color = color if is_active else "#2b3040"
        return f"""<div class='session-box' style='background-color: {bg_color}; color: white;'>
            <div style='font-size: 1.1em; font-weight: bold;'>{name}</div>
            <div style='font-size: 0.85em; opacity: 0.9;'>{timing_str}</div>
            <div style='font-size: 0.9em; font-weight: 500; margin-top:5px;'>{"🟢 ACTIVE" if is_active else "⚪ CLOSED"}</div>
            <div class='time-badge'>{rem_str}</div></div>"""

    syd_a, syd_t, syd_r = get_session_status(now_pkt, 3, 12)
    tok_a, tok_t, tok_r = get_session_status(now_pkt, 5, 14)
    lon_a, lon_t, lon_r = get_session_status(now_pkt, 12, 21)
    ny_a, ny_t, ny_r = get_session_status(now_pkt, 17, 2)

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(get_session_html("🇦🇺 Sydney", syd_a, "#3498db", syd_t, syd_r), unsafe_allow_html=True)
    with c2: st.markdown(get_session_html("🇯🇵 Tokyo", tok_a, "#9b59b6", tok_t, tok_r), unsafe_allow_html=True)
    with c3: st.markdown(get_session_html("🇬🇧 London", lon_a, "#e67e22", lon_t, lon_r), unsafe_allow_html=True)
    with c4: st.markdown(get_session_html("🇺🇸 New York", ny_a, "#e74c3c", ny_t, ny_r), unsafe_allow_html=True)

    # Load Data
    cot_df = load_cot_data()
    oi_df = load_daily_oi()
    df_fx = get_market_data(trading_mode)
    matrix_df = get_currency_matrix()
    live_news = requests.get("https://www.forexlive.com/feed", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10).content # Minimal news fetch

    st.markdown("---")
    st.subheader("🎯 AI-Verified Trade Setups (Updated Every 30 Mins)")

    strong = df_fx[df_fx['Score'] >= 6]
    weak = df_fx[df_fx['Score'] <= 4]
    found = False

    if not strong.empty and not weak.empty:
        for _, s in strong.iterrows():
            for _, w in weak.iterrows():
                c1, c2 = s['Instrument'], w['Instrument']
                cot_align = True
                if not cot_df.empty:
                    s_sent = cot_df[cot_df['Instrument'].str.contains(c1, case=False)]['Direction'].values
                    if len(s_sent) > 0 and "Bearish" in s_sent[0]: cot_align = False
                
                if cot_align and ("✅" in s['Volume Confirm']):
                    order = ['GOLD', 'EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
                    try:
                        if order.index(c1) < order.index(c2): pair, action = f"{c1}{c2}", "BUY"
                        else: pair, action = f"{c2}{c1}", "SELL"
                        
                        setup_id = f"{action}_{pair}_{now_pkt.strftime('%Y-%m-%d_%H')}" # Unique per hour
                        
                        if setup_id not in st.session_state.ai_verdicts:
                            if ai_model:
                                with st.spinner(f"🤖 AI Verifying {pair}..."):
                                    prompt = f"Expert Analyst: {action} setup on {pair}. Strength {s['Score']} vs {w['Score']}. COT/Vol Aligned. Batao yeh trade safe hai ya news risk? (Roman Urdu, 2 lines max)"
                                    response = ai_model.generate_content(prompt)
                                    st.session_state.ai_verdicts[setup_id] = response.text
                        
                        verdict = st.session_state.ai_verdicts.get(setup_id, "Monitoring...")
                        st.markdown(f"<div style='background-color: #1e222d; padding: 15px; border-radius: 10px; border-left: 5px solid #2ecc71; margin-bottom: 10px;'><h4>🔥 {action} {pair}</h4><p style='color: #f1c40f;'><b>🤖 AI:</b> {verdict}</p></div>", unsafe_allow_html=True)
                        found = True
                        
                        if setup_id not in st.session_state.sent_alerts:
                            send_telegram_alert(f"🚨 *AI Setup*\n🔥 {action} {pair}\n🤖 {verdict}")
                            st.session_state.sent_alerts.add(setup_id)
                    except: pass
    
    if not found: st.info("Filhal koi setup nahi mila. Background monitoring active hai...")

    # --- CHAT & TABLES (Same as before) ---
    st.markdown("---")
    st.subheader("💬 AI Chat & Matrix")
    # [Matrix, Price Action, COT/OI Tables codes go here - Same as before]

# --- [TAB 2 & 3: Risk Manager & Psychology remain same] ---
