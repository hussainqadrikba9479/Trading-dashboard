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
st.set_page_config(page_title="Hussain Algo Terminal V17 (AlertBot Engine)", page_icon="⚡", layout="wide")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    working_model = None
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name.lower():
            working_model = m.name.replace('models/', '')
            break 
            
    if working_model: ai_model = genai.GenerativeModel(working_model) 
    else: ai_model = None
except Exception as e: ai_model = None

# --- 2. ALERTBOT DATA ENGINES (COT, OI, MARKETS) ---

@st.cache_data(ttl=3600)
def load_cot_data():
    try:
        df_cot = pd.read_excel("COT.xlsm", sheet_name="Main", engine='openpyxl', usecols="A,B,G,K,P", skiprows=2, header=None)
        df_cot.columns = ['Instrument', 'Net Change', 'Direction', 'COT Index', 'OI Change']
        return df_cot.dropna(subset=['Instrument'])
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def load_daily_oi():
    try:
        df = pd.read_excel("Daily_OI.xlsm", sheet_name="Data", engine='openpyxl')
        df.columns = df.columns.astype(str).str.replace('\n', ' ').str.replace('\r', '')
        col_map = {'USD': 'USD', 'Euro': 'EUR', 'Pound': 'GBP', 'Australian': 'AUD', 'Zealand': 'NZD', 'Canadian': 'CAD', 'Swiss': 'CHF', 'Yen': 'JPY', 'Gold': 'XAU'}
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

@st.cache_data(ttl=300)
def get_market_data():
    data_list = []
    # UI aur Dashboard dono jagah GOLD ko XAU rakha hai taake sync rahay
    symbols = {'USD': 'DX-Y.NYB', 'XAU': 'GC=F', 'EUR': '6E=F', 'GBP': '6B=F', 'JPY': '6J=F', 'AUD': '6A=F', 'CAD': '6C=F', 'CHF': '6S=F', 'NZD': '6N=F'}
    interval = "1h" # Swing Trading D1 + H4
    
    for name, ticker in symbols.items():
        try:
            df = yf.download(ticker, period="1mo", interval=interval, progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
            
            if df.empty or len(df) < 25: continue
                
            close, sma = df['Close'].iloc[-1], df['Close'].rolling(20).mean().iloc[-1]
            vol, avg_vol = df['Volume'].iloc[-1], df['Volume'].rolling(20).mean().iloc[-1]
            
            score = 5
            if close > sma: score = 7 if close > df['High'].iloc[-5] else 6
            else: score = 3 if close < df['Low'].iloc[-5] else 4
            
            vol_confirm = "✅" if vol > avg_vol else "❌"
            status = "Strong" if score >= 6 else "Weak" if score <= 4 else "Neutral"
            
            data_list.append({
                'Instrument': name, 
                'Score': score, 
                'Status': status,
                'Volume Confirm': vol_confirm
            })
        except: 
            data_list.append({'Instrument': name, 'Score': 5, 'Status': 'Neutral', 'Volume Confirm': 'Error'})
            
    return pd.DataFrame(data_list)

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
        r2 = requests.get("https://www.forexlive.com/feed", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        root2 = ET.fromstring(r2.content)
        for i, item in enumerate(root2.findall('.//item')):
            if i >= 6: break
            pub_date = item.find('pubDate').text
            try:
                dt_obj = parsedate_to_datetime(pub_date)
                dt_pkt_sq = dt_obj.astimezone(pkt_tz)
                time_display = dt_pkt_sq.strftime("%I:%M %p")
            except: time_display = pub_date[:22]
            squawk.append({'Time': time_display, 'Headline': item.find('title').text})
    except: pass
    return pd.DataFrame(news), squawk

# --- 3. TRADE MATCHING LOGIC (Same as AlertBot) ---

def verify_signal_with_ai(action, pair, s_score, w_score, squawk_list):
    if not ai_model: return {"Score": 0, "Reason": "AI Offline"}
    
    news_str = "\n".join([n['Headline'] for n in squawk_list]) if squawk_list else "No major news"
    prompt = f"Expert Analyst: {action} setup on {pair}. Strength {s_score} vs {w_score}. COT/Vol/OI Aligned. Live News: {news_str}. Batao yeh trade safe hai ya news risk? (Roman Urdu, 2 lines max)"
    
    try:
        response = ai_model.generate_content(prompt)
        return {"Score": 90, "Reason": response.text[:300]} 
    except Exception as e:
        return {"Score": 0, "Reason": f"Error"}


# --- 4. OUTPUT UI BLOCKS ---

def show_sessions():
    pkt_tz = pytz.timezone('Asia/Karachi')
    now = datetime.now(pkt_tz)
    if now.weekday() >= 5: 
        st.error("🛑 MARKET CLOSED (WEEKEND)")
        return
    cols = st.columns(4)
    sessions = [{"name": "🇦🇺 AU Sydney", "open": 4, "close": 13}, {"name": "🇯🇵 JP Tokyo", "open": 5, "close": 14},
                {"name": "🇬🇧 GB London", "open": 12, "close": 21}, {"name": "🇺🇸 US New York", "open": 17, "close": 2}]
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

st.subheader("🌍 Global Market Sessions (PKT)")
show_sessions()
st.divider()

col_left, col_right = st.columns([2.5, 1])

with col_left:
    
    # 1. Load Data silently in background like AlertBot
    cot_df = load_cot_data()
    oi_df = load_daily_oi()
    df_fx = get_market_data()
    news_df, squawk_list = get_news_and_squawk() 
    
    # 2. Render Live Engine Status UI
    st.subheader("📡 Live Engine Status (AlertBot Scanner)")
    
    if not df_fx.empty:
        currencies = ['USD', 'EUR', 'GBP', 'AUD', 'NZD', 'CAD', 'CHF', 'JPY', 'XAU']
        cols = st.columns(len(currencies))
        
        for i, cur in enumerate(currencies):
            cur_data = df_fx[df_fx['Instrument'] == cur]
            if not cur_data.empty:
                status = cur_data['Status'].values[0]
            else:
                status = "Neutral"
                
            if status == "Strong":
                bg_color = "#1a5c20"; icon = "🟢"
            elif status == "Weak":
                bg_color = "#5c1a1a"; icon = "🔴"
            else:
                bg_color = "#2b2b2b"; icon = "⚪"
                
            cols[i].markdown(
                f"<div style='text-align:center; padding:10px; margin-bottom:15px; border-radius:8px; background-color:{bg_color}; border:1px solid #444;'>"
                f"<span style='font-size:12px; color:#ccc;'>{cur}</span><br>"
                f"<b>{icon} {status}</b></div>", 
                unsafe_allow_html=True
            )

    # 3. Match Setups using AlertBot Logic
    phase1_setups = []
    ai_verified_setups = []
    
    strong = df_fx[df_fx['Score'] >= 6]
    weak = df_fx[df_fx['Score'] <= 4]
    
    for _, s in strong.iterrows():
        for _, w in weak.iterrows():
            c1, c2 = s['Instrument'], w['Instrument']
            
            # Check COT
            cot_align = True
            if not cot_df.empty:
                s_sent = cot_df[cot_df['Instrument'].str.contains(c1, case=False)]['Direction'].values
                if len(s_sent) > 0 and "Bearish" in s_sent[0]: cot_align = False
            
            # Check Daily OI
            oi_align = True
            if not oi_df.empty and 'Status' in oi_df.columns:
                s_oi = oi_df[oi_df['Instrument'] == c1]['Status'].values
                if len(s_oi) > 0 and "Decreasing" in s_oi[0]: oi_align = False
                
            # If All Aligned (COT + OI + Vol)
            if cot_align and oi_align and ("✅" in s['Volume Confirm'] or "✅" in w['Volume Confirm']):
                order = ['XAU', 'EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
                try:
                    if order.index(c1) < order.index(c2): pair, action = f"{c1}{c2}", "BUY"
                    else: pair, action = f"{c2}{c1}", "SELL"
                    
                    phase1_setups.append({
                        "Pair": pair, 
                        "Type": action, 
                        "s_score": s['Score'], 
                        "w_score": w['Score'],
                        "Logic": f"Strength {s['Score']} vs {w['Score']} (COT/OI/Vol Aligned)"
                    })
                except: pass

    # 4. Show Phase 1 Setups
    st.subheader("⚙️ Phase 1: Technical Setups (Dual-Leg)")
    if phase1_setups:
        for sig in phase1_setups:
            color = "🟢" if sig['Type'] == "BUY" else "🔴"
            st.info(f"{color} **{sig['Type']} {sig['Pair']}** | 🏗️ {sig['Logic']}")
    else:
        st.write("💤 Filhal Phase 1 mein koi AlertBot Alignment nahi. Waiting for Volume, COT & OI confirmation...")

    st.divider()
    
    # 5. Show Phase 2 AI Verification
    st.subheader("🤖 Phase 2: AI Verified Setups (News Fundamentals)")
    
    if phase1_setups:
        with st.spinner('AI is verifying News & Fundamentals like AlertBot...'):
            for sig in phase1_setups:
                ai_verification = verify_signal_with_ai(sig['Type'], sig['Pair'], sig['s_score'], sig['w_score'], squawk_list)
                if ai_verification and "Error" not in ai_verification['Reason']:
                    ai_verified_setups.append({"signal": sig, "ai": ai_verification})
        
        if ai_verified_setups:
            for item in ai_verified_setups:
                sig = item['signal']
                ai = item['ai']
                color = "🟢" if sig['Type'] == "BUY" else "🔴"
                with st.expander(f"{color} {sig['Type']} {sig['Pair']} - AI Signal Ready", expanded=True):
                    st.write(f"🏗️ **System Check:** {sig['Logic']}")
                    st.success(f"🤖 **AI Verdict:** {ai['Reason']}")
        else:
             st.warning("Phase 1 ke setups ko AI ne News Risk ki wajah se reject kar diya hai.")
    else:
        st.write("Phase 1 mein koi setup nahi aaya is liye AI Verification pending hai.")

    st.divider()
    
    # 6. Scheduled News
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
    st.subheader("⚡ Live Squawk")
    if squawk_list:
        for item in squawk_list:
            st.markdown(f"**{item['Headline']}**<br><small>{item['Time']}</small><hr>", unsafe_allow_html=True)
    else:
        st.info("📡 Live news feed se connection check ho raha hai. Filhal koi new headline nahi...")

st.divider()
query = st.chat_input("Ask Gemini about fundamental alignment...")

if query and ai_model: 
    try:
        system_prompt = f"""
        You are an expert Forex Quant Trader assisting a professional trader.
        The user is asking you: "{query}"

        STRICT RULES FOR YOUR RESPONSE:
        1. Language: You MUST reply ONLY in Roman Urdu (Urdu written in English alphabets).
        2. Scope: Focus strictly on the Forex market and Gold (XAUUSD). 
        3. Tone: Keep the analysis professional, crisp, and to the point.
        """
        with st.spinner("AI is analyzing the market..."):
            response = ai_model.generate_content(system_prompt)
            st.write(f"🤖: {response.text}")
            
    except Exception as e:
        st.error(f"⚠️ Gemini API connection error. Details: {e}")
