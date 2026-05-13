import streamlit as st
import pandas as pd
import yfinance as yf
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz
from email.utils import parsedate_to_datetime
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import time

# ==========================================
# 1. CONFIGURATION & PAGE SETUP
# ==========================================
st.set_page_config(page_title="Hussain Algo Terminal V18", page_icon="⚡", layout="wide")

# ERROR DETECTOR LAGA DIYA HAI
ai_setup_error = ""
try:
    # BOHAT ZAROORI: GitHub par safety ke liye ab key direct nahi likhi, balkay secrets se aayegi!
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    working_model = None
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name.lower():
            working_model = m.name.replace('models/', '')
            break 
            
    if working_model: 
        ai_model = genai.GenerativeModel(working_model) 
    else: 
        ai_model = None
        ai_setup_error = "Google ki taraf se koi model available nahi."
        
except Exception as e: 
    ai_model = None
    ai_setup_error = str(e)

# ==========================================
# 2. ANTI-SPAM & EMAIL ENGINE
# ==========================================
MEMORY_FILE = "sent_alerts.txt"

def is_already_sent(pair, action):
    if not os.path.exists(MEMORY_FILE):
        return False
    date_str = datetime.now(pytz.timezone('Asia/Karachi')).strftime('%Y-%m-%d')
    record = f"{date_str}_{action}_{pair}"
    with open(MEMORY_FILE, "r") as f:
        return record in f.read().splitlines()

def mark_as_sent(pair, action):
    date_str = datetime.now(pytz.timezone('Asia/Karachi')).strftime('%Y-%m-%d')
    record = f"{date_str}_{action}_{pair}\n"
    with open(MEMORY_FILE, "a") as f:
        f.write(record)

def send_email_alert(subject, body):
    return False
    try:
        sender_email = st.secrets.get("EMAIL_SENDER", os.environ.get("EMAIL_SENDER", ""))
        sender_password = st.secrets.get("EMAIL_PASSWORD", os.environ.get("EMAIL_PASSWORD", ""))
        receiver_email = st.secrets.get("EMAIL_RECEIVER", os.environ.get("EMAIL_RECEIVER", sender_email))
    except: return False
    
    if not sender_email or not sender_password: return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e: return False

# ==========================================
# 3. ADVANCED QUANT ENGINES (ATR & ZONES)
# ==========================================
def get_atr_and_zones(pair, action):
    tickers = {
        'EURUSD': 'EURUSD=X', 'GBPUSD': 'GBPUSD=X', 'AUDUSD': 'AUDUSD=X',
        'NZDUSD': 'NZDUSD=X', 'USDCAD': 'CAD=X', 'USDCHF': 'CHF=X', 
        'USDJPY': 'JPY=X', 'EURJPY': 'EURJPY=X', 'GBPJPY': 'GBPJPY=X',
        'AUDJPY': 'AUDJPY=X', 'XAUUSD': 'GC=F'
    }
    ticker = tickers.get(pair)
    if not ticker: return "N/A", "N/A"
    
    try:
        # ATR Exhaustion Logic (14-Day)
        df_d = yf.download(ticker, period="1mo", interval="1d", progress=False)
        if isinstance(df_d.columns, pd.MultiIndex): df_d.columns = df_d.columns.droplevel(1)
        
        atr_14 = (df_d['High'] - df_d['Low']).rolling(14).mean().iloc[-2]
        today_move = df_d['High'].iloc[-1] - df_d['Low'].iloc[-1]
        exhaustion = (today_move / atr_14) * 100 if atr_14 > 0 else 0
        
        if exhaustion > 80: atr_status = f"⚠️ Warning: Daily ATR {int(exhaustion)}% Exhausted (Room kam hai)"
        else: atr_status = f"✅ Safe: Daily ATR {int(exhaustion)}% Used (Move baqi hai)"

        # Sniper Entry Zones Logic (Fib 50-61.8 + Swing H/L)
        df_h = yf.download(ticker, period="5d", interval="1h", progress=False)
        if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.droplevel(1)
        
        recent_high = df_h['High'].iloc[-48:].max()
        recent_low = df_h['Low'].iloc[-48:].min()
        
        # JPY pairs have different decimal placements
        dec = 2 if 'JPY' in pair else 4
        if pair == 'XAUUSD': dec = 2
        
        if action == "BUY":
            fib_50 = recent_high - 0.5 * (recent_high - recent_low)
            fib_618 = recent_high - 0.618 * (recent_high - recent_low)
            zone = f"🎯 Buy Limit Zone: {round(fib_50, dec)} se {round(fib_618, dec)} (Golden Pullback)"
        else:
            fib_50 = recent_low + 0.5 * (recent_high - recent_low)
            fib_618 = recent_low + 0.618 * (recent_high - recent_low)
            zone = f"🎯 Sell Limit Zone: {round(fib_50, dec)} se {round(fib_618, dec)} (Golden Retest)"
            
        return atr_status, zone
    except:
        return "Data N/A", "Zone Data N/A"

def get_all_currency_strengths():
    currencies = ['USD', 'EUR', 'GBP', 'AUD', 'NZD', 'CAD', 'CHF', 'JPY', 'XAU']
    strengths = {}
    tickers = {
        'USD': 'DX-Y.NYB', 'EUR': 'EURUSD=X', 'GBP': 'GBPUSD=X',
        'AUD': 'AUDUSD=X', 'NZD': 'NZDUSD=X', 'CAD': 'CAD=X',
        'CHF': 'CHF=X', 'JPY': 'JPY=X', 'XAU': 'GC=F'
    }
    inverted = ['CAD', 'CHF', 'JPY']
    
    for curr in currencies:
        try:
            ticker = yf.Ticker(tickers[curr])
            df = ticker.history(period="5d", interval="1h")
            if df.empty or len(df) < 25: 
                strengths[curr] = {"status": "Neutral", "reason": "Not Enough Data"}
                continue
            
            prev_high = df['High'].rolling(20).max().shift(1).iloc[-1]
            prev_low = df['Low'].rolling(20).min().shift(1).iloc[-1]
            avg_vol = df['Volume'].rolling(20).mean().shift(1).iloc[-1]
            
            curr_close = df['Close'].iloc[-1]
            curr_high = df['High'].iloc[-1]
            curr_low = df['Low'].iloc[-1]
            curr_vol = df['Volume'].iloc[-1]
            prev_close = df['Close'].iloc[-2]
            
            is_high_vol = curr_vol > (avg_vol * 1.3) if avg_vol > 0 else False
            
            is_spring = (curr_low < prev_low) and (curr_close > prev_low) and is_high_vol
            is_upthrust = (curr_high > prev_high) and (curr_close < prev_high) and is_high_vol
            recent_bo_up = (df['Close'].iloc[-5:-1] > df['High'].rolling(20).max().shift(1).iloc[-5:-1]).any()
            is_retest_buy = recent_bo_up and (curr_close < prev_close) and (curr_close > prev_low)
            recent_bo_down = (df['Close'].iloc[-5:-1] < df['Low'].rolling(20).min().shift(1).iloc[-5:-1]).any()
            is_retest_sell = recent_bo_down and (curr_close > prev_close) and (curr_close < prev_high)
            
            status = "Neutral"
            reason = "Ranging / No Setup"
            
            if is_spring: status, reason = "Strong", "Spring / Shakeout (Support Rejection)"
            elif is_upthrust: status, reason = "Weak", "Upthrust (Resistance Rejection)"
            elif is_retest_buy: status, reason = "Strong", "Trend Continuation (Pullback Retest)"
            elif is_retest_sell: status, reason = "Weak", "Downtrend Continuation (Pullback Retest)"

            if curr in inverted:
                if status == "Strong": status, reason = "Weak", reason.replace("Strong", "Weak")
                elif status == "Weak": status, reason = "Strong", reason.replace("Weak", "Strong")
                    
            strengths[curr] = {"status": status, "reason": reason}
        except:
            strengths[curr] = {"status": "Neutral", "reason": "Error"}
    return strengths

def check_pair_alignment(pair, strengths_dict):
    base = 'XAU' if pair == 'XAUUSD' else pair[:3]
    quote = 'USD' if pair == 'XAUUSD' else pair[3:]
    base_data = strengths_dict.get(base, {"status": "Neutral"})
    quote_data = strengths_dict.get(quote, {"status": "Neutral"})
    
    if base_data["status"] == "Strong" and quote_data["status"] == "Weak":
        return {"Pair": pair, "Type": "BUY", "Logic": f"Base [{base_data['reason']}] + Quote [{quote_data['reason']}]"}
    elif base_data["status"] == "Weak" and quote_data["status"] == "Strong":
        return {"Pair": pair, "Type": "SELL", "Logic": f"Base [{base_data['reason']}] + Quote [{quote_data['reason']}]"}
    return None

# ===================================================
# SMART AI VERIFICATION (WITH CACHE & DELAY FIX)
# ===================================================
def verify_signal_with_ai(ai_model, action, pair, logic, atr_status, zone, squawk_list, is_background=False):
    cache_key = f"{action}_{pair}_{atr_status}"
    
    if not is_background:
        if "ai_cache" not in st.session_state:
            st.session_state.ai_cache = {}
        if cache_key in st.session_state.ai_cache:
            return st.session_state.ai_cache[cache_key]
            
    if not ai_model: return f"⚠️ AI Offline (Masla: {ai_setup_error})"
    
    time.sleep(15)
    
    news_str = "\n".join([n['Headline'] for n in squawk_list]) if squawk_list else "No major news"
    prompt = f"""Expert Quant Analyst: Setup found: {action} on {pair}.
    Tech Logic: {logic}.
    Exhaustion Status: {atr_status}.
    Planned Entry Zone: {zone}.
    Live News: {news_str}. 
    Batao yeh sniper entry trade news ke hisaab se safe hai ya risk hai? 
    (Roman Urdu, sirf 2 lines. Agar exhausted ho toh limit entry ko safe kaho)"""
    
    try:
        response = ai_model.generate_content(prompt)
        if not is_background:
            st.session_state.ai_cache[cache_key] = response.text
        return response.text
    except Exception as e: 
        return f"⚠️ API Error: {str(e)}"

def run_bot():
    currency_strengths = get_all_currency_strengths()
    live_news, squawk_list = get_news_and_squawk() 
    forex_pairs = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY', 'EURJPY', 'GBPJPY', 'AUDJPY', 'XAUUSD']
    
    for pair in forex_pairs:
        raw_sig = check_pair_alignment(pair, currency_strengths)
        if raw_sig:
            action, logic = raw_sig['Type'], raw_sig['Logic']
            if not is_already_sent(pair, action):
                
                # Naya System: Background mein ATR aur Zone calculate ho raha hai
                atr_stat, zone_stat = get_atr_and_zones(pair, action)
                full_logic = f"{logic}\n{atr_stat}\n{zone_stat}"
                
                verdict = verify_signal_with_ai(ai_model, action, pair, logic, atr_stat, zone_stat, squawk_list, is_background=True)
                if "Error" not in verdict and "Offline" not in verdict:
                    email_subject = f"Setup: {action} {pair} | {atr_stat.split(':')[0]}"
                    email_body = f"Hussain Algo Terminal (Quant V18)\n\nSetup: {action} {pair}\nLogic: {logic}\n\n📊 {atr_stat}\n{zone_stat}\n\n🤖 AI Verdict:\n{verdict}\n\nTime: {datetime.now(pytz.timezone('Asia/Karachi')).strftime('%I:%M %p')} (PKT)"
                    if send_email_alert(email_subject, email_body):
                        mark_as_sent(pair, action)

@st.cache_resource
def start_background_bot():
    def alert_loop():
        while True:
            try: run_bot()
            except: pass
            time.sleep(1800) 
            
    thread = threading.Thread(target=alert_loop, daemon=True)
    thread.start()
    return thread

start_background_bot()

# ==========================================
# 4. DASHBOARD DATA ENGINES
# ==========================================
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
    symbols = {'USD': 'DX-Y.NYB', 'XAU': 'GC=F', 'EUR': '6E=F', 'GBP': '6B=F', 'JPY': '6J=F', 'AUD': '6A=F', 'CAD': '6C=F', 'CHF': '6S=F', 'NZD': '6N=F'}
    interval = "1h" 
    
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
            
            data_list.append({'Instrument': name, 'Score': score, 'Status': status, 'Volume Confirm': vol_confirm})
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
                        dt_pkt = dt_est.astimezone(pkt_tz) - timedelta(hours=4)
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

# ==========================================
# 5. DASHBOARD UI BLOCKS
# ==========================================
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

st.subheader("🌍 Global Market Sessions (PKT)")
show_sessions()
st.divider()

col_left, col_right = st.columns([2.5, 1])

with col_left:
    cot_df = load_cot_data()
    oi_df = load_daily_oi()
    df_fx = get_market_data()
    news_df, squawk_list = get_news_and_squawk() 
    
    st.subheader("📡 Live Engine Status (Dashboard Logic)")
    if not df_fx.empty:
        currencies = ['USD', 'EUR', 'GBP', 'AUD', 'NZD', 'CAD', 'CHF', 'JPY', 'XAU']
        cols = st.columns(len(currencies))
        for i, cur in enumerate(currencies):
            cur_data = df_fx[df_fx['Instrument'] == cur]
            if not cur_data.empty: status = cur_data['Status'].values[0]
            else: status = "Neutral"
                
            if status == "Strong": bg_color = "#1a5c20"; icon = "🟢"
            elif status == "Weak": bg_color = "#5c1a1a"; icon = "🔴"
            else: bg_color = "#2b2b2b"; icon = "⚪"
                
            cols[i].markdown(
                f"<div style='text-align:center; padding:10px; margin-bottom:15px; border-radius:8px; background-color:{bg_color}; border:1px solid #444;'>"
                f"<span style='font-size:12px; color:#ccc;'>{cur}</span><br>"
                f"<b>{icon} {status}</b></div>", 
                unsafe_allow_html=True
            )

    phase1_setups = []
    strong = df_fx[df_fx['Score'] >= 6]
    weak = df_fx[df_fx['Score'] <= 4]
    
    for _, s in strong.iterrows():
        for _, w in weak.iterrows():
            c1, c2 = s['Instrument'], w['Instrument']
            cot_align, oi_align = True, True
            if not cot_df.empty:
                s_sent = cot_df[cot_df['Instrument'].str.contains(c1, case=False)]['Direction'].values
                if len(s_sent) > 0 and "Bearish" in s_sent[0]: cot_align = False
            if not oi_df.empty and 'Status' in oi_df.columns:
                s_oi = oi_df[oi_df['Instrument'] == c1]['Status'].values
                if len(s_oi) > 0 and "Decreasing" in s_oi[0]: oi_align = False
                
            if cot_align and oi_align and ("✅" in s['Volume Confirm'] or "✅" in w['Volume Confirm']):
                order = ['XAU', 'EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
                try:
                    if order.index(c1) < order.index(c2): pair, action = f"{c1}{c2}", "BUY"
                    else: pair, action = f"{c2}{c1}", "SELL"
                    
                    # Naya UI Display Logic
                    atr_stat, zone_stat = get_atr_and_zones(pair, action)
                    
                    phase1_setups.append({
                        "Pair": pair, "Type": action, "s_score": s['Score'], "w_score": w['Score'],
                        "Logic": f"Strength {s['Score']} vs {w['Score']} (COT/OI/Vol Aligned)",
                        "ATR": atr_stat, "Zone": zone_stat
                    })
                except: pass

    st.subheader("⚙️ Phase 1: Technical Setups (Smart Entries)")
    if phase1_setups:
        for sig in phase1_setups:
            color = "🟢" if sig['Type'] == "BUY" else "🔴"
            st.info(f"{color} **{sig['Type']} {sig['Pair']}** | 🏗️ {sig['Logic']}\n\n📊 {sig['ATR']}\n\n{sig['Zone']}")
    else:
        st.write("💤 Filhal Phase 1 mein koi Alignment nahi. Waiting for sniper setup...")

    st.divider()

    st.subheader("🤖 Phase 2: AI Verified Setups (News Fundamentals)")
    if ai_setup_error:
        st.error(f"❌ AI Setup Error: {ai_setup_error}")
        
    if phase1_setups:
        for sig in phase1_setups:
            with st.expander(f"📉 **{sig['Type']} {sig['Pair']}** - AI Signal Ready", expanded=True):
                st.write(f"🏗️ **System Check:** {sig['Logic']}")
                with st.spinner("AI is analyzing live news & entry zones..."):
                    verdict = verify_signal_with_ai(ai_model, sig['Type'], sig['Pair'], sig['Logic'], sig['ATR'], sig['Zone'], squawk_list, is_background=False)
                if "Offline" in verdict or "Error" in verdict:
                    st.error(f"🤖 **AI Verdict:** {verdict}")
                else:
                    st.success(f"🤖 **AI Verdict:** {verdict}")
    else:
        st.write("💤 Waiting for Phase 1 technical setups to verify...")

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
    st.subheader("⚡ Live Squawk")
    if squawk_list:
        for item in squawk_list:
            st.markdown(f"**{item['Headline']}**<br><small>{item['Time']}</small><hr>", unsafe_allow_html=True)
    else:
        st.info("📡 Live news feed se connection check ho raha hai...")

st.divider()
query = st.chat_input("Ask Gemini about fundamental alignment...")

if query:
    if ai_model: 
        try:
            system_prompt = f"""You are an expert Forex Quant Trader assisting a professional trader.
            The user is asking you: "{query}"
            STRICT RULES: 1. Reply ONLY in Roman Urdu. 2. Focus strictly on Forex/Gold. 3. Be crisp and professional."""
            with st.spinner("AI is analyzing the market..."):
                response = ai_model.generate_content(system_prompt)
                st.write(f"🤖: {response.text}")
        except Exception as e:
            st.error(f"⚠️ API Error: {str(e)}")
    else:
        st.error(f"⚠️ AI Offline: System could not start. Error: {ai_setup_error}")
