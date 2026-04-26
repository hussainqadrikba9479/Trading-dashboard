import yfinance as yf
import pandas as pd
import streamlit as st
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

# --- 1. Dashboard Setup & Theme ---
st.set_page_config(page_title="Global Trading Terminal", layout="wide")
st.markdown("""
    <style>
    .main {background-color: transparent;}
    .news-card {
        border-left: 6px solid #e74c3c; 
        background-color: #1e222d; color: #d1d4dc; padding: 12px; 
        border-radius: 8px; margin-bottom: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .session-box {padding: 12px; border-radius: 8px; text-align: center; margin-bottom: 15px; transition: 0.3s;}
    .time-badge {background: rgba(255,255,255,0.1); color: #d1d4dc; padding: 4px 8px; border-radius: 4px; display: inline-block; margin-top: 5px;}
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    ::-webkit-scrollbar {width: 6px; height: 6px;}
    ::-webkit-scrollbar-track {background: #0e1117;} 
    ::-webkit-scrollbar-thumb {background: #3498db; border-radius: 3px;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# --- SECURITY: LOGIN GATE ---
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br><div style='background-color: #1e222d; padding: 30px; border-radius: 10px; text-align: center;'>", unsafe_allow_html=True)
        st.subheader("🔒 Restricted Access")
        pwd = st.text_input("Enter Password & Press Enter:", type="password", key="final_login_key")
        try: correct_password = st.secrets["TERMINAL_PASSWORD"]
        except: correct_password = "admin"
        if pwd:
            if pwd == correct_password:
                st.session_state.authenticated = True
                st.rerun()
            else: st.error("❌ Ghalat Password!")
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

st.title("🦅 Master Trading Terminal (PA + VSA + COT)")

# --- 2. Trading Engine Selector ---
trading_mode = st.radio("⚙️ Select Trading Engine", ["Intraday (H1 + M30)", "Swing Trading (D1 + H4)"], index=1, horizontal=True)

# --- 3. Live Sessions & Clock ---
pkt_timezone = timezone(timedelta(hours=5))
now_pkt = datetime.now(pkt_timezone)
st.info(f"🕒 **Live Clock:** {now_pkt.strftime('%I:%M:%S %p')} (PKT) | **Current Mode:** {trading_mode}")

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
    
    if is_weekend: return False, "Market Closed", "⏸️ Weekend"
    
    if is_active:
        diff = close_time - now
        rem = f"⏳ Closes in {diff.seconds // 3600}h {(diff.seconds // 60) % 60}m"
    else:
        diff = open_time - now
        rem = f"⏳ Opens in {diff.seconds // 3600}h {(diff.seconds // 60) % 60}m"
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
# --- BACKEND DATA ENGINE ---
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
            data_list.append({
                'Instrument': name, 
                'Structure': 'Uptrend' if close > sma else 'Downtrend',
                'PA Signal': 'Buy Pullback' if score >= 6 else 'Sell Pullback' if score <= 4 else 'Neutral',
                'Volume Confirm': vol_confirm, 'Score': score
            })
        except: pass
    return pd.DataFrame(data_list)

df_fx = get_market_data(trading_mode)

@st.cache_data(ttl=120)
def get_live_squawk():
    try:
        r = requests.get("https://www.forexlive.com/feed", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        root = ET.fromstring(r.content)
        return [{'title': i.find('title').text, 'link': i.find('link').text, 'time': i.find('pubDate').text} for i in root.findall('.//item')[:5]]
    except: return []

live_news = get_live_squawk()

# =========================================================================
# --- TOP SECTION: OUTCOMES (ACTIONABLE ITEMS FIRST) ---
# =========================================================================

st.markdown("---")
st.subheader("🎯 Active Trade Setups (PA + VSA + COT Locked)")

strong = df_fx[df_fx['Score'] >= 6]
weak = df_fx[df_fx['Score'] <= 4]
found = False

if not strong.empty and not weak.empty:
    for _, s in strong.iterrows():
        for _, w in weak.iterrows():
            cot_align = True
            if not cot_df.empty:
                s_sentiment = cot_df[cot_df['Instrument'].str.contains(s['Instrument'], case=False)]['Direction'].values
                if len(s_sentiment) > 0 and "Bearish" in s_sentiment[0]: cot_align = False
            
            if cot_align and ("✅" in s['Volume Confirm'] or "✅" in w['Volume Confirm']):
                st.success(f"🔥 **BUY {s['Instrument']}{w['Instrument']}** | Score: {s['Score']} vs {w['Score']} | Smart Money Aligned 🚀")
                found = True

if not found:
    st.info("Filhal criteria par koi trade setup nahi mila. Searching for institutional alignments...")

# --- AI CO-PILOT ---
st.markdown("---")
st.subheader("🧠 Gemini AI Co-Pilot (Live Chat & Analysis)")

if "chat_session" not in st.session_state: st.session_state.chat_session = None
if "chat_messages" not in st.session_state: st.session_state.chat_messages = []

try: api_key = st.secrets["GEMINI_API_KEY"]
except: api_key = None; st.error("⚠️ API Key missing in Secrets!")

if api_key:
    genai.configure(api_key=api_key)
    if st.button("🚀 Generate Institutional Report"):
        with st.spinner("Gemini is processing your PA, Volume, and COT data..."):
            try:
                # ✅ FIX: Auto-Detect Model (Yeh error 404 ko hamesha ke liye khatam kar dega)
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                target_model = available_models[0] if available_models else 'models/gemini-pro'
                model = genai.GenerativeModel(target_model)
                
                st.session_state.chat_session = model.start_chat(history=[])
                st.session_state.chat_messages = [] 
                
                pa_data = df_fx.to_string() if not df_fx.empty else "No PA data."
                cot_data = cot_df.to_string() if not cot_df.empty else "No COT data."
                
                prompt = f"""
                Aap ek expert quantitative forex analyst hain. Niche diye gaye data ka jaiza lein:
                1. PRICE ACTION & VOLUME: {pa_data}
                2. INSTITUTIONAL POSITIONING (COT): {cot_data}
                
                Bataiye:
                1. Market ka overall mood kya hai?
                2. Kin pairs par PA, Volume aur COT teeno align ho rahe hain (High Probability)?
                3. Risks aur trap warnings dein.
                
                Jawab Roman Urdu mein point-by-point dein.
                """
                response = st.session_state.chat_session.send_message(prompt)
                st.session_state.chat_messages.append({"role": "assistant", "content": response.text})
                st.rerun()
            except Exception as e:
                st.error(f"AI Error: {e}")
                
    # Display Chat History
    if st.session_state.chat_messages:
        for msg in st.session_state.chat_messages:
            if msg["role"] == "assistant":
                st.markdown(f"<div style='background-color: #1e222d; padding: 20px; border-radius: 10px; border-left: 5px solid #3498db; margin-bottom: 10px;'><b>🤖 AI Co-Pilot:</b><br>{msg['content']}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='background-color: #2b3040; padding: 15px; border-radius: 10px; border-left: 5px solid #e74c3c; margin-bottom: 10px; text-align: right;'><b>👤 Aap:</b><br>{msg['content']}</div>", unsafe_allow_html=True)
        
    # Follow-up Chat Input
    if st.session_state.chat_session:
        user_q = st.chat_input("AI se mazeed sawal puchein...")
        if user_q:
            st.session_state.chat_messages.append({"role": "user", "content": user_q})
            with st.spinner("AI Soch raha hai..."):
                try:
                    res = st.session_state.chat_session.send_message(f"Forex expert ki hasiyat se Roman Urdu mein is sawal ka jawab dein: {user_q}")
                    st.session_state.chat_messages.append({"role": "assistant", "content": res.text})
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

# =========================================================================
# --- BOTTOM SECTION: DATA TABLES & NEWS FEED ---
# =========================================================================

st.markdown("---")
col_l, col_r = st.columns(2)
with col_l:
    st.subheader("🔍 Price Action Analysis")
    st.dataframe(df_fx, use_container_width=True, hide_index=True)
with col_r:
    st.subheader("📊 Institutional Positioning (COT)")
    st.dataframe(cot_df.head(15), use_container_width=True, hide_index=True)

# --- LIVE NEWS SQUAWK (Moved to Bottom) ---
st.markdown("---")
st.subheader("📰 Live Breaking News (Forex Squawk)")
if live_news:
    for n in live_news:
        st.markdown(f"<div class='news-card'><b>⚡ {n['title']}</b><br><small>{n['time']}</small></div>", unsafe_allow_html=True)
else:
    st.warning("Squawk feed currently unavailable.")

# --- FOREX FACTORY STYLE CALENDAR ---
st.markdown("---")
st.subheader("📅 High Impact News Calendar")
try:
    cal_data = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json").json()
    news_by_date = {}
    for e in cal_data:
        if e.get('impact') == 'High':
            dt = datetime.fromisoformat(e['date']).astimezone(pkt_timezone)
            d_str = dt.strftime("%A, %d %b %Y")
            if d_str not in news_by_date: news_by_date[d_str] = []
            news_by_date[d_str].append({'time': dt.strftime('%I:%M %p'), 'curr': e['country'], 'title': e['title'], 'past': dt < now_pkt})

    for day, events in news_by_date.items():
        with st.expander(f"📅 {day}", expanded=True):
            for ev in events:
                c1, c2, c3 = st.columns([1, 1, 3])
                if ev['past']:
                    c1.markdown(f"~~{ev['time']}~~")
                    c2.markdown(f"~~{ev['curr']}~~")
                    c3.markdown(f"⚪ *{ev['title']} (Passed)*")
                else:
                    c1.markdown(f"**{ev['time']}**")
                    c2.markdown(f"**{ev['curr']}**")
                    c3.markdown(f"🔴 **{ev['title']}**")
except: st.write("Calendar loading...")
