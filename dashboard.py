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
        df.columns = df.columns.astype(str).str.replace('\n', ' ').str.replace
