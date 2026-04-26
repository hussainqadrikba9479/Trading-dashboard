import yfinance as yf
import pandas as pd
import streamlit as st
import google.generativeai as genai
import numpy as np
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta, date

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
    .news-card a { color: #3498db !important; text-decoration: none; }
    .news-card a:hover { color: #2980b9 !important; text-decoration: underline; }
    .session-box {padding: 12px; border-radius: 8px; text-align: center; margin-bottom: 15px; transition: 0.3s;}
    .time-badge {background: rgba(255,255,255,0.1); color: #d1d4dc; padding: 4px 8px; border-radius: 4px; display: inline-block; margin-top: 5px;}
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    ::-webkit-scrollbar {width: 6px; height: 6px;}
    ::-webkit-scrollbar-track {background: #0e1117;} 
    ::-webkit-scrollbar-thumb {background: #3498db; border-radius: 3px;}
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Master Trading Terminal (PA + VSA)")

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

# --- 2. Trading Engine Selector ---
st.markdown("### ⚙️ Select Trading Engine")
trading_mode = st.radio("Select Trading Engine", ["Intraday (H1 + M30)", "Swing Trading (D1 + H4)", "Backtest Mode (Historical)"], index=1, horizontal=True)

selected_date = None
if trading_mode == "Backtest Mode (Historical)":
    st.warning("⚠️ Yahoo Finance Intraday (H1) data is only available for the last 60 days. Please select a recent date.")
    min_date = date.today() - timedelta(days=59)
    max_date = date.today()
    selected_date = st.date_input("📅 Select Date for Backtest:", value=max_date, min_value=min_date, max_value=max_date)

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

def calculate_angle(price_diff, periods): return price_diff / periods if periods != 0 else 0
def analyze_market_structure(df):
    df['Local_High'] = df['High'][(df['High'].shift(1) < df['High']) & (df['High'].shift(-1) < df['High'])]
    df['Local_Low'] = df['Low'][(df['Low'].shift(1) > df['Low']) & (df['Low'].shift(-1) > df['Low'])]
    recent_highs = df['Local_High'].dropna().tail(3).values
    recent_lows = df['Local_Low'].dropna().tail(3).values
    if len(recent_highs) < 3 or len(recent_lows) < 3: return "Insufficient Data", 0, "Neutral"

    h1, h2, h3 = recent_highs[-3], recent_highs[-2], recent_highs[-1]
    l1, l2, l3 = recent_lows[-3], recent_lows[-2], recent_lows[-1]
    tolerance = h1 * 0.001 
    current_price = df['Close'].iloc[-1]
    structure, signal, angle = "➖ Range", "Neutral", 0
    
    if (abs(h1-h2) < tolerance and abs(h2-h3) < tolerance) and (abs(l1-l2) < tolerance and abs(l2-l3) < tolerance):
        structure = "➖ Range (Valid - 3+ Touches)"
        if current_price >= h3 * 0.999: signal = "🚨 Sell at Range Top (Wait for Upthrust)"
        elif current_price <= l3 * 1.001: signal = "🟢 Buy at Range Bottom (Wait for Spring)"
    elif h3 > h2 and h2 > h1 and l3 > l2 and l2 > l1:
        structure = "📈 Uptrend Confirmed"
        angle = calculate_angle(h3 - h2, 5)
        if angle > (h1*0.0005):
            if current_price < h3 and current_price > l3: signal = "✅ Buy Pullback (Trend Continuation)"
        else: signal = "⚠️ Uptrend (Weak Angle - Caution)"
    elif h3 < h2 and h2 < h1 and l3 < l2 and l2 < l1:
        structure = "📉 Downtrend Confirmed"
        angle = calculate_angle(l2 - l3, 5)
        if angle > (l1*0.0005):
            if current_price > l3 and current_price < h3: signal = "❌ Sell Pullback (Trend Continuation)"
        else: signal = "⚠️ Downtrend (Weak Angle - Caution)"
    elif (h2 <= h1 + tolerance) and (h3 > h1):
        structure = "🚀 Upward Breakout Phase"
        if abs(current_price - h1) / h1 < 0.002: signal = "🟢 Safe Buy (Breakout Pullback)"
    elif (l2 >= l1 - tolerance) and (l3 < l1):
        structure = "🩸 Downward Breakdown Phase"
        if abs(current_price - l1) / l1 < 0.002: signal = "🚨 Safe Sell (Breakdown Pullback)"

    return structure, angle, signal

futures_symbols = {'USD': 'DX-Y.NYB', 'GOLD': 'GC=F', 'EUR': '6E=F', 'GBP': '6B=F', 'JPY': '6J=F', 'AUD': '6A=F', 'CAD': '6C=F', 'CHF': '6S=F'}

@st.cache_data(ttl=300)
def get_market_data(symbols_dict, mode, backtest_date=None):
    data_list = []
    for name, ticker in symbols_dict.items():
        try:
            if mode == "Backtest Mode (Historical)" and backtest_date:
                end_str = (backtest_date + timedelta(days=1)).strftime('%Y-%m-%d')
                start_str = (backtest_date - timedelta(days=50)).strftime('%Y-%m-%d')
                df_htf = yf.download(ticker, start=start_str, end=end_str, interval="1d", progress=False)
                df_ltf = yf.download(ticker, start=start_str, end=end_str, interval="1h", progress=False)
                ltf_label = "H1 (Historical)"
            elif mode == "Intraday (H1 + M30)":
                df_htf = yf.download(ticker, period="1mo", interval="1h", progress=False)
                df_ltf = yf.download(ticker, period="1mo", interval="30m", progress=False)
                ltf_label = "M30"
            else:
                df_htf = yf.download(ticker, period="6mo", interval="1d", progress=False)
                df_ltf = yf.download(ticker, period="1mo", interval="1h", progress=False)
                ltf_label = "H4"
                
            if df_htf.empty or df_ltf.empty: continue
            if isinstance(df_htf.columns, pd.MultiIndex): df_htf.columns = df_htf.columns.droplevel(1)
            if isinstance(df_ltf.columns, pd.MultiIndex): df_ltf.columns = df_ltf.columns.droplevel(1)

            close_htf = df_htf['Close'].iloc[-1]
            sma20_htf = df_htf['Close'].rolling(20).mean().iloc[-1]
            htf_trend = "UP" if close_htf > sma20_htf else "DOWN"

            close_ltf = df_ltf['Close'].iloc[-1]
            sma20_ltf = df_ltf['Close'].rolling(20).mean().iloc[-1]
            ltf_trend = "UP" if close_ltf > sma20_ltf else "DOWN"
            
            pa_structure, _, pa_signal = analyze_market_structure(df_ltf.copy())

            score = 5
            if htf_trend == "UP" and ltf_trend == "UP": score = 9
            elif htf_trend == "DOWN" and ltf_trend == "DOWN": score = 1
            elif htf_trend == "UP" and ltf_trend == "DOWN": score = 6
            elif htf_trend == "DOWN" and ltf_trend == "UP": score = 4

            vol, prev_vol, avg_vol = df_ltf['Volume'].iloc[-1], df_ltf['Volume'].iloc[-2], df_ltf['Volume'].rolling(20).mean().iloc[-1]
            vol_confirm = "No Volume Confirm"
            if "Breakout" in pa_structure or "Pullback" in pa_signal:
                if vol < prev_vol: vol_confirm = "✅ Vol Confirmed"
            elif "Range" in pa_signal and vol > avg_vol: vol_confirm = "🚨 Trap Vol"

            data_list.append({
                'Instrument': name, f'{ltf_label} Structure': pa_structure, 
                'PA Signal': pa_signal, 'Volume Confirm': vol_confirm, 'Score': score
            })
        except: pass
    return pd.DataFrame(data_list)

df_fx = get_market_data(futures_symbols, trading_mode, selected_date)

@st.cache_data(ttl=120)
def get_live_squawk():
    try:
        r = requests.get("https://www.forexlive.com/feed", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        root = ET.fromstring(r.content)
        return [{'title': i.find('title').text, 'link': i.find('link').text, 'time': i.find('pubDate').text} for i in root.findall('.//item')[:5]]
    except: return []

live_news = get_live_squawk()

# =========================================================================
# --- TOP SECTION: OUTCOMES (ACTIVE SETUPS WITH ORIGINAL LOGIC) ---
# =========================================================================

st.markdown("---")
st.subheader("🎯 Active Trade Setups")

if not df_fx.empty:
    strong = df_fx[df_fx['Score'] >= 8]
    weak = df_fx[df_fx['Score'] <= 3]
    found = False
    
    for _, s in strong.iterrows():
        for _, w in weak.iterrows():
            c1, c2 = s['Instrument'], w['Instrument']
            s_sig, s_vol = str(s['PA Signal']), str(s['Volume Confirm'])
            w_sig, w_vol = str(w['PA Signal']), str(w['Volume Confirm'])
            
            setup_valid = False
            desc = ""
            if ("Buy" in s_sig or "Spring" in s_sig) and "✅" in s_vol:
                setup_valid, desc = True, f"{c1} Valid Buy Structure."
            elif ("Sell" in w_sig or "Upthrust" in w_sig) and "✅" in w_vol:
                setup_valid, desc = True, f"{c2} Valid Sell Structure."
                
            if "Sell" in s_sig or "Buy" in w_sig: continue

            if setup_valid:
                order = ['GOLD', 'EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
                try:
                    if order.index(c1) < order.index(c2): pair, action = f"{c1}{c2}", "BUY"
                    else: pair, action = f"{c2}{c1}", "SELL"
                    
                    st.success(f"⚡ **{action} {pair}** | Institutional Setup 🚀")
                    st.write(f"**Confirmation:** {desc}")
                    found = True
                except: pass
                
    if not found: st.warning("Filhal criteria par koi trade setup nahi mila.")

# --- LIVE NEWS SQUAWK ---
st.markdown("---")
st.subheader("📰 Live Breaking News (Forex Squawk)")
if live_news:
    for n in live_news:
        st.markdown(f"<div class='news-card'><b>⚡ {n['title']}</b><br><small>{n['time']}</small></div>", unsafe_allow_html=True)
else:
    st.info("Live squawk feed is fetching...")

# --- AI CO-PILOT (WITH FULL CHAT LOGIC) ---
st.markdown("---")
st.subheader("🧠 Gemini AI Co-Pilot (Live Market Analysis & Chat)")

if "chat_session" not in st.session_state: st.session_state.chat_session = None
if "chat_messages" not in st.session_state: st.session_state.chat_messages = []

try: api_key = st.secrets["GEMINI_API_KEY"]
except KeyError:
    api_key = None
    st.error("⚠️ API Key not found! Please Streamlit App ki Settings > Secrets mein 'GEMINI_API_KEY' add karein.")

if api_key:
    genai.configure(api_key=api_key)

    if st.button("🚀 Generate High-Probability Market Analysis"):
        with st.spinner("Gemini is aligning VSA, Strength, COT Data, and News... Please wait."):
            try:
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                if not available_models:
                    st.error("⚠️ Aap ki API key par koi text model available nahi hai.")
                else:
                    target_model = available_models[0] 
                    model = genai.GenerativeModel(target_model)
                    
                    st.session_state.chat_session = model.start_chat(history=[])
                    st.session_state.chat_messages = [] 

                    market_summary = df_fx.to_string() if not df_fx.empty else "Technical table data missing."
                    cot_summary = cot_df.to_string() if not cot_df.empty else "COT data not available."
                    news_summary = "\n".join([n['title'] for n in live_news]) if live_news else "No major news."

                    prompt = f"""
                    Aap ek expert quantitative forex trader aur risk manager hain. Niche diye gaye live market data (Currency Strength, VSA), Institutional COT data, aur taaza khabron ka jaiza lein aur inko aapas mein align karein:
                    
                    1. TECHNICAL & VSA DATA (Currency Strength & Volume): 
                    {market_summary}
                    
                    2. INSTITUTIONAL COT DATA (Smart Money Positioning):
                    {cot_summary}
                    
                    3. LATEST BREAKING NEWS: 
                    {news_summary}
                    
                    Bataiye:
                    1. Market ka overall mood aur Smart Money (Commercials/Non-Commercials) ka rujhan kya hai?
                    2. HIGH-PROBABILITY SETUPS: Kin pairs par sab se behtareen setup ban raha hai jahan VSA, Currency Strength, aur COT teeno ek hi direction mein align ho rahe hain?
                    3. RISKS & WARNINGS: Kya kisi setup mein 'Divergence' ya trap hai? (Maslan technical/VSA buy de raha ho lekin COT sell mein ho, ya news khilaf ho).
                    
                    Jawab strictly aur asaan Roman Urdu mein dein.
                    """
                    response = st.session_state.chat_session.send_message(prompt)
                    st.session_state.chat_messages.append({"role": "assistant", "content": response.text})
                    st.rerun()
            except Exception as e:
                st.error(f"⚠️ AI Analysis Error: {e}")

    # Display Chat History
    if st.session_state.chat_messages:
        st.success("✅ Analysis Active! Ab aap neechay mazeed sawalaat pooch sakte hain.")
        for msg in st.session_state.chat_messages:
            if msg["role"] == "assistant":
                st.markdown(f"<div style='background-color: #2b3040; color: #fafafa; padding: 20px; border-radius: 10px; border-left: 5px solid #3498db; margin-bottom: 10px;'><b>🤖 AI Co-Pilot:</b><br>{msg['content']}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='background-color: #1e222d; color: #fafafa; padding: 15px; border-radius: 10px; border-left: 5px solid #e74c3c; margin-bottom: 10px; text-align: right;'><b>👤 Aap:</b><br>{msg['content']}</div>", unsafe_allow_html=True)

    # Chat Input Box
    if st.session_state.chat_session:
        user_question = st.chat_input("AI se mazeed sawal puchein (Jaise: COT data ke mutabiq USD ka next trend kya hai?)...")
        if user_question:
            st.session_state.chat_messages.append({"role": "user", "content": user_question})
            with st.spinner("AI Soch raha hai..."):
                try:
                    follow_up_prompt = f"Forex expert ki hasiyat se Roman Urdu mein is sawal ka jawab dein: {user_question}"
                    response = st.session_state.chat_session.send_message(follow_up_prompt)
                    st.session_state.chat_messages.append({"role": "assistant", "content": response.text})
                    st.rerun()
                except Exception as e: st.error(f"⚠️ Error: {e}")

# =========================================================================
# --- BOTTOM SECTION: RAW DATA TABLES & FOREX FACTORY NEWS ---
# =========================================================================

st.markdown("---")
st.subheader(f"🔍 Price Action Analysis Phase")
def style_score(val):
    if val >= 8: return 'background-color: #2ecc71; color: black; font-weight: bold'
    if val <= 3: return 'background-color: #e74c3c; color: white; font-weight: bold'
    return ''
def style_structure(val):
    if 'Uptrend' in str(val) or 'Buy' in str(val) or '✅' in str(val): return 'color: #2ecc71; font-weight: bold'
    if 'Downtrend' in str(val) or 'Sell' in str(val) or '🚨' in str(val) or '❌' in str(val): return 'color: #e74c3c; font-weight: bold'
    return ''

if not df_fx.empty:
    st.dataframe(df_fx.style.map(style_score, subset=['Score'])
                 .map(style_structure, subset=[c for c in df_fx.columns if 'Structure' in c][0])
                 .map(style_structure, subset=['PA Signal', 'Volume Confirm']), 
                 use_container_width=True, hide_index=True)

st.markdown("---")
st.subheader("📊 Institutional Sentiment (COT Data)")
if not cot_df.empty:
    st.dataframe(cot_df.head(15), use_container_width=True, hide_index=True)

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
except: st.write("Calendar data loading...")
