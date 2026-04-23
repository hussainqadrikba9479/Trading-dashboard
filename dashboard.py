import yfinance as yf
import pandas as pd
import streamlit as st
import google.generativeai as genai
import numpy as np
import requests
from datetime import datetime, timezone, timedelta, date

# --- Dashboard Setup ---
st.set_page_config(page_title="Global Trading Terminal", layout="wide")
st.markdown("""
    <style>
    .main {background-color: #f4f6f9;}
    .sentiment-card {padding: 10px; border-radius: 8px; margin-bottom: 5px; color: white; font-weight: bold; text-align: center; font-size: 0.8rem;}
    .news-card {border-left: 6px solid #e74c3c; background-color: #ffffff; padding: 12px; border-radius: 8px; box-shadow: 0px 4px 6px rgba(0,0,0,0.1); margin-bottom: 10px;}
    .session-box {padding: 12px; border-radius: 8px; text-align: center; margin-bottom: 15px; transition: 0.3s;}
    .time-badge {background: rgba(0,0,0,0.15); padding: 4px 8px; border-radius: 4px; display: inline-block; font-size: 0.8em; margin-top: 5px;}
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Master Trading Terminal (PA + VSA + Backtester)")

# --- Mode Selector ---
st.markdown("### ⚙️ Select Trading Engine")
trading_mode = st.radio("", ["Intraday (H1 + M30)", "Swing Trading (D1 + H4)", "Backtest Mode (Historical)"], horizontal=True)

# --- Backtest Calendar ---
selected_date = None
if trading_mode == "Backtest Mode (Historical)":
    st.warning("⚠️ Yahoo Finance Intraday (H1) data is only available for the last 60 days. Please select a recent date.")
    min_date = date.today() - timedelta(days=59)
    max_date = date.today()
    selected_date = st.date_input("📅 Select Date for Backtest:", value=max_date, min_value=min_date, max_value=max_date)

# --- Pakistan Time & Live Sessions ---
pkt_timezone = timezone(timedelta(hours=5))
now_pkt = datetime.now(pkt_timezone)
st.info(f"🕒 **Live Clock:** {now_pkt.strftime('%I:%M:%S %p')} (PKT) | **Current Mode:** {trading_mode}")

# Advanced Session Logic with Countdown
def get_session_status(now, open_h, close_h):
    open_time = now.replace(hour=open_h, minute=0, second=0, microsecond=0)
    close_time = now.replace(hour=close_h, minute=0, second=0, microsecond=0)
    
    if open_h > close_h: # Overnight Session (e.g., NY 17 to 02)
        if now.hour >= open_h or now.hour < close_h:
            is_active = True
            if now.hour >= open_h:
                close_time += timedelta(days=1)
        else:
            is_active = False
    else: # Normal Day Session
        is_active = open_h <= now.hour < close_h
        if not is_active and now.hour >= close_h:
            open_time += timedelta(days=1)
            
    if is_active:
        diff = close_time - now
        rem = f"⏳ Closes in {diff.seconds // 3600}h {(diff.seconds // 60) % 60}m"
    else:
        diff = open_time - now
        rem = f"⏳ Opens in {diff.seconds // 3600}h {(diff.seconds // 60) % 60}m"
        
    op_str = open_time.strftime("%I %p").lstrip('0')
    cl_str = close_time.strftime("%I %p").lstrip('0')
    timing_str = f"{op_str} - {cl_str}"
    
    return is_active, timing_str, rem

def get_session_html(name, is_active, color, timing_str, rem_str):
    bg_color = color if is_active else "#e0e0e0"
    text_color = "white" if is_active else "#666666"
    status = "🟢 ACTIVE" if is_active else "⚪ CLOSED"
    shadow = "box-shadow: 0px 4px 10px rgba(0,0,0,0.2);" if is_active else ""
    return f"""
    <div class='session-box' style='background-color: {bg_color}; color: {text_color}; {shadow}'>
        <div style='font-size: 1.1em; font-weight: bold;'>{name}</div>
        <div style='font-size: 0.85em; opacity: 0.9; margin-bottom: 4px;'>{timing_str}</div>
        <div style='font-size: 0.9em; font-weight: 500;'>{status}</div>
        <div class='time-badge'>{rem_str}</div>
    </div>
    """

syd_active, syd_time, syd_rem = get_session_status(now_pkt, 3, 12)
tok_active, tok_time, tok_rem = get_session_status(now_pkt, 5, 14)
lon_active, lon_time, lon_rem = get_session_status(now_pkt, 12, 21)
ny_active, ny_time, ny_rem = get_session_status(now_pkt, 17, 2)

c1, c2, c3, c4 = st.columns(4)
with c1: st.markdown(get_session_html("🇦🇺 Sydney", syd_active, "#3498db", syd_time, syd_rem), unsafe_allow_html=True)
with c2: st.markdown(get_session_html("🇯🇵 Tokyo", tok_active, "#9b59b6", tok_time, tok_rem), unsafe_allow_html=True)
with c3: st.markdown(get_session_html("🇬🇧 London", lon_active, "#e67e22", lon_time, lon_rem), unsafe_allow_html=True)
with c4: st.markdown(get_session_html("🇺🇸 New York", ny_active, "#e74c3c", ny_time, ny_rem), unsafe_allow_html=True)

# --- 1. COT REPORT (Information Only) ---
st.subheader("📊 Institutional Sentiment (COT Data - Info Only)")
@st.cache_data(ttl=3600)
def load_cot_data():
    try:
        df_cot = pd.read_excel("COT.xlsm", sheet_name="Main", engine='openpyxl', usecols="A,B,G,K,P", skiprows=2, header=None)
        df_cot.columns = ['Instrument', 'Net Change', 'Direction', 'COT Index', 'OI Change']
        return df_cot.dropna(subset=['Instrument'])
    except Exception as e: return str(e)

cot_df = load_cot_data()
if isinstance(cot_df, pd.DataFrame):
    st.dataframe(cot_df.head(15), use_container_width=True, hide_index=True)

# --- HELPER FUNCTIONS ---
def calculate_angle(price_diff, periods):
    if periods == 0: return 0
    return price_diff / periods

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

# --- MARKET ENGINE ---
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

st.markdown("---")
st.subheader(f"🔍 Price Action Analysis Phase")
df_fx = get_market_data(futures_symbols, trading_mode, selected_date)

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

# --- RECOMMENDATIONS ---
st.markdown("---")
st.subheader("🎯 Active Trade Setups (PA + Volume Lock)")
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

# --- NEWS ---
st.markdown("---")
st.subheader("🚨 High Impact News")
@st.cache_data(ttl=600)
def get_news():
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        data = requests.get(url, timeout=10).json()
        for event in data:
            if event.get('impact') == 'High':
                try:
                    dt_obj = datetime.fromisoformat(event['date'])
                    pkt_dt = dt_obj.astimezone(pkt_timezone)
                    if pkt_dt.date() >= now_pkt.date():
                        st.markdown(f"<div class='news-card'><b>🔴 {event['country']} - {event['title']}</b><br><small>{pkt_dt.strftime('%d %b | %I:%M %p')} (PKT)</small></div>", unsafe_allow_html=True)
                except: pass
    except: pass
get_news()
# --- 5. LIVE BREAKING NEWS (SQUAWK FEED) ---
st.markdown("---")
st.subheader("📰 Live Breaking News (Forex Squawk)")

@st.cache_data(ttl=120)  # Har 2 minute baad naya data fetch karega (120 seconds)
def get_live_squawk_news():
    try:
        # ForexLive ya kisi reliable news source ka RSS feed URL
        url = "https://www.forexlive.com/feed"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        # XML Data ko parse karna
        import xml.etree.ElementTree as ET
        root = ET.fromstring(response.content)
        
        news_items = []
        # Sab se taaza 7 khabrein nikalna
        for item in root.findall('.//item')[:7]:
            title = item.find('title').text
            # Time formatting
            pub_date = item.find('pubDate').text
            link = item.find('link').text
            news_items.append({'title': title, 'time': pub_date, 'link': link})
            
        return news_items
    except Exception as e:
        return []

live_news = get_live_squawk_news()

if live_news:
    for news in live_news:
        # Breaking news ke liye blue border wala card
        st.markdown(f"""
        <div class='news-card' style='border-left-color: #3498db; background-color: #f0f8ff;'>
            <b>⚡ {news['title']}</b><br>
            <small style='color: #555;'>{news['time']} | <a href='{news['link']}' target='_blank' style='text-decoration: none; color: #3498db; font-weight: bold;'>Read Full Update</a></small>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("Live squawk feed is currently fetching or temporarily unavailable.")
    import google.generativeai as genai

# --- 6. GEMINI AI CO-PILOT (MARKET SUMMARY & RISK ANALYSIS) ---
st.markdown("---")
st.subheader("🧠 Gemini AI Co-Pilot (Live Market Analysis)")

# Sidebar mein API key input box banayen taake screen clear rahay
with st.sidebar:
    st.markdown("### 🔑 AI Co-Pilot Settings")
    api_key = st.text_input("Enter Gemini API Key:", type="password", help="Get a free key from Google AI Studio (aistudio.google.com)")

if api_key:
    genai.configure(api_key=api_key)
    # Gemini Flash ya Pro model select karein
    model = genai.GenerativeModel('gemini-pro') 

    if st.button("🚀 Generate AI Market Analysis & Risk Report"):
        with st.spinner("Gemini is analyzing Structure, Volume, and News... Please wait."):
            try:
                # Dashboard ka data text mein convert kar ke AI ko bhejne ki tayari
                market_summary = df_fx.to_string() if not df_fx.empty else "No PA setups currently."
                
                # News ko text mein badalna (agar available ho)
                try:
                    news_summary = "\n".join([n['title'] for n in live_news]) if live_news else "No major squawk news."
                except:
                    news_summary = "News feed data not available."

                # AI ko instructions (Prompt) dena
                prompt = f"""
                Aap ek expert quantitative forex trader aur risk manager hain. Niche diye gaye live market data (VSA/Price Action) aur taaza khabron ka jaiza lein:
                
                MARKET DATA (Pairs, Structure, PA Signal, Volume):
                {market_summary}
                
                LATEST BREAKING NEWS:
                {news_summary}
                
                Bataiye:
                1. Market ka overall mood kya hai?
                2. Kin pairs par sab se behtareen setup ban raha hai aur kyun?
                3. RISKS & WARNINGS: Kya kisi setup mein ghalti ki gunjaish hai? (maslan weak angle, trap volume, ya kisi news ki wajah se market opposite ja sakti hai?). 
                
                Jawab point-to-point aur asaan Roman Urdu / English mix mein dein.
                """

                response = model.generate_content(prompt)
                
                st.success("✅ Analysis Complete!")
                # AI ka jawab screen par dikhana
                st.markdown(f"<div style='background-color: #e8f4f8; padding: 20px; border-radius: 10px; border-left: 5px solid #3498db;'>{response.text}</div>", unsafe_allow_html=True)
                
            except Exception as e:
                st.error(f"⚠️ AI Analysis Error: Please check your API Key or connection. Detail: {e}")
else:
    st.info("👆 AI assistant ko on karne ke liye Sidebar (left side) mein apni Gemini API key enter karein.")
