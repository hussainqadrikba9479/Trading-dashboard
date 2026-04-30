import streamlit as st
import pandas as pd
import yfinance as yf
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz
from email.utils import parsedate_to_datetime

# --- 1. CONFIGURATION & PAGE SETUP ---
st.set_page_config(page_title="Hussain Algo Terminal V14 (2-Phase UI)", page_icon="⚡", layout="wide")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    working_model = None
    # Google ke saare models ki list check karega
    for m in genai.list_models():
        # Shart 1: Model naya ho (generateContent support kare)
        # Shart 2: Model ke naam mein 'gemini' lazmi aata ho (Purane models ko reject kar dega)
        if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name.lower():
            working_model = m.name.replace('models/', '')
            break # Jaise hi pehla theek Gemini model mile, dhoondna band kar do
            
    if working_model:
        ai_model = genai.GenerativeModel(working_model) 
    else:
        ai_model = None
        
except Exception as e:
    ai_model = None

# --- 2. DATA ENGINES (COT & NEWS ONLY) ---

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
                             'Cur': item.find('country').text, 'Event': title, 'Actual': actual, '_is_past': is_past})
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


# --- 3. DUAL-LEG VSA & STRUCTURE ENGINE ---

@st.cache_data(ttl=60)
def get_all_currency_strengths():
    currencies = ['USD', 'EUR', 'GBP', 'AUD', 'NZD', 'CAD', 'CHF', 'JPY', 'XAU']
    strengths = {}
    
    tickers = {
        'USD': 'DX-Y.NYB', 'EUR': 'EURUSD=X', 'GBP': 'GBPUSD=X',
        'AUD': 'AUDUSD=X', 'NZD': 'NZDUSD=X', 'CAD': 'USDCAD=X',
        'CHF': 'USDCHF=X', 'JPY': 'USDJPY=X', 'XAU': 'GC=F'
    }
    inverted = ['CAD', 'CHF', 'JPY']
    
    for curr in currencies:
        try:
            ticker = yf.Ticker(tickers[curr])
            df = ticker.history(period="5d", interval="1h")
            if df.empty or len(df) < 21: 
                strengths[curr] = "Neutral"
                continue
                
            avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
            curr_vol = df['Volume'].iloc[-1]
            is_high_vol = curr_vol > (avg_vol * 1.5) if avg_vol > 0 else False
            
            last_close = df['Close'].iloc[-1]
            prev_high = df['High'].rolling(20).max().iloc[-2]
            prev_low = df['Low'].rolling(20).min().iloc[-2]
            
            is_bullish = last_close > prev_high
            is_bearish = last_close < prev_low
            
            if curr in inverted:
                is_bullish, is_bearish = is_bearish, is_bullish
                
            if is_bullish and is_high_vol: strengths[curr] = "Strong"
            elif is_bearish and is_high_vol: strengths[curr] = "Weak"
            else: strengths[curr] = "Neutral"
        except:
            strengths[curr] = "Neutral"
            
    return strengths

def check_pair_alignment(pair, strengths_dict):
    base = 'XAU' if pair == 'XAUUSD' else pair[:3]
    quote = 'USD' if pair == 'XAUUSD' else pair[3:]
    
    base_str = strengths_dict.get(base, "Neutral")
    quote_str = strengths_dict.get(quote, "Neutral")
    
    if base_str == "Strong" and quote_str == "Weak":
        return {"Pair": pair, "Type": "BUY", "Logic": f"Base ({base}) is Strong + Quote ({quote}) is Weak"}
    elif base_str == "Weak" and quote_str == "Strong":
        return {"Pair": pair, "Type": "SELL", "Logic": f"Base ({base}) is Weak + Quote ({quote}) is Strong"}
    return None

def verify_signal_with_ai(raw_signal, cot_data, news_data):
    if not ai_model or not raw_signal: return None
    base = 'XAU' if raw_signal['Pair'] == 'XAUUSD' else raw_signal['Pair'][:3]
    quote = 'USD' if raw_signal['Pair'] == 'XAUUSD' else raw_signal['Pair'][3:]
    
    prompt = f"""
    Analyze this dual-leg setup:
    Pair: {raw_signal['Pair']} ({raw_signal['Type']})
    Logic: {raw_signal['Logic']}.
    Are there any extreme COT conditions or High Impact news for {base}/{quote} today?
    Give a short expert verdict and Confidence Score out of 100%.
    """
    try:
        response = ai_model.generate_content(prompt)
        return {"Score": 90, "Reason": response.text[:280]} 
    except Exception as e:
        return {"Score": 0, "Reason": f"Error"} # Simple error tag so it doesn't show in verified section

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

forex_pairs = [
    'EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY',
    'EURGBP', 'EURAUD', 'EURNZD', 'EURCAD', 'EURCHF', 'EURJPY',
    'GBPAUD', 'GBPNZD', 'GBPCAD', 'GBPCHF', 'GBPJPY',
    'AUDNZD', 'AUDCAD', 'AUDCHF', 'AUDJPY',
    'NZDCAD', 'NZDCHF', 'NZDJPY',
    'CADCHF', 'CADJPY', 'CHFJPY',
    'XAUUSD' 
]

show_sessions()
st.divider()
col_left, col_right = st.columns([2.5, 1])

with col_left:
    
    cot_df = load_cot_data() 
    news_df, squawk_list = get_news_and_squawk() 
    
    phase1_setups = []
    ai_verified_setups = []
    
    # ---------------------------------------------
    # PHASE 1: TECHNICAL SCAN (VSA & STRUCTURE ONLY)
    # ---------------------------------------------
    st.subheader("⚙️ Phase 1: Technical Setups (VSA & Structure)")
    
    with st.spinner('Scanning Phase 1 (Base vs Quote)...'):
        currency_strengths = get_all_currency_strengths() 
        for pair in forex_pairs:
            raw_sig = check_pair_alignment(pair, currency_strengths) 
            if raw_sig:
                phase1_setups.append(raw_sig)
                
    if phase1_setups:
        for sig in phase1_setups:
            color = "🟢" if sig['Type'] == "BUY" else "🔴"
            st.info(f"{color} **{sig['Type']} {sig['Pair']}** | 🏗️ {sig['Logic']}")
    else:
        st.write("💤 Filhal koi Technical Setup (Phase 1) align nahi hua. Waiting...")

    st.divider()
    
    # ---------------------------------------------
    # PHASE 2: AI FUNDAMENTAL VERIFICATION
    # ---------------------------------------------
    st.subheader("🤖 Phase 2: AI Verified Setups (COT & News)")
    
    if phase1_setups:
        with st.spinner('AI is verifying Technical Setups...'):
            for sig in phase1_setups:
                ai_verification = verify_signal_with_ai(sig, cot_df, news_df)
                
                # Agar AI ne properly verify kiya aur error nahi aya toh is list mein dalein
                if ai_verification and "Error" not in ai_verification['Reason']:
                    ai_verified_setups.append({"signal": sig, "ai": ai_verification})
        
        if ai_verified_setups:
            for item in ai_verified_setups:
                sig = item['signal']
                ai = item['ai']
                color = "🟢" if sig['Type'] == "BUY" else "🔴"
                with st.expander(f"{color} {sig['Type']} {sig['Pair']} - AI Score: {ai['Score']}%", expanded=True):
                    st.write(f"🏗️ **System Check:** {sig['Logic']}")
                    st.success(f"🤖 **AI Verdict:** {ai['Reason']}")
                    st.progress(ai['Score']/100)
        else:
             st.warning("Phase 1 ke setups ko AI ne Fundamentally (COT/News) reject kar diya hai ya verify nahi kar saka.")
    else:
        st.write("Phase 1 mein koi setup nahi aaya is liye AI Verification pending hai.")

    st.divider()
    st.subheader("📅 Scheduled News (High Impact)")
    if not news_df.empty:
        html_table = "<table style='width:100%; text-align:left; font-size:14px; border-collapse: collapse;'>"
        html_table += "<tr style='border-bottom: 2px solid #555; color:#ccc; background-color: #1e1e1e;'><th>Date</th><th>Time(PKT)</th><th>Imp</th><th>Cur</th><th>Event</th><th>Actual</th></tr>"
        for idx, row in news_df.iterrows():
            row_style = "text-decoration: line-through; color: #666;" if row['_is_past'] else "color: #fff;"
            html_table += f"<tr style='border-bottom: 1px solid #333; {row_style}'>"
            html_table += f"<td style='padding:8px;'>{row['Date']}</td><td>{row['Time (PKT)']}</td><td>{row['Impact']}</td><td><b>{row['Cur']}</b></td><td>{row['Event']}</td><td>{row['Actual']}</td></tr>"
        html_table += "</table>"
        st.markdown(html_table, unsafe_allow_html=True)

with col_right:
    st.subheader("🏦 Smart Money (COT)")
    if not cot_df.empty:
        st.dataframe(cot_df.style.map(style_cot), hide_index=True, use_container_width=True)
    
    st.divider()
query = st.chat_input("Ask Gemini about fundamental alignment...")

if query and ai_model: 
    try:
        # AI ko strict hidayat (Prompt Engineering)
        system_prompt = f"""
        You are an expert Forex Quant Trader assisting a professional trader.
        The user is asking you: "{query}"

        STRICT RULES FOR YOUR RESPONSE:
        1. Language: You MUST reply ONLY in Roman Urdu (Urdu written in English alphabets). DO NOT use Hindi, Devanagari script, or pure English.
        2. Scope: Focus strictly on the Forex market (EUR, GBP, USD, JPY, AUD, NZD, CAD, CHF) and Gold (XAUUSD). 
        3. Restrictions: DO NOT mention the Indian Stock Market (Nifty, Sensex), Crypto, or any irrelevant regional equities. 
        4. Tone: Keep the analysis professional, crisp, and to the point.
        """
        
        with st.spinner("AI is analyzing the market..."):
            response = ai_model.generate_content(system_prompt)
            st.write(f"🤖: {response.text}")
            
    except Exception as e:
        st.error(f"⚠️ Gemini API connection error. Details: {e}")
