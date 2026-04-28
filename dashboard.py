import streamlit as st
import pandas as pd
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timezone, timedelta

# --- PAGE CONFIG ---
st.set_page_config(page_title="Hussain Algo Terminal", page_icon="📈", layout="wide")

# --- DATA FUNCTIONS ---
@st.cache_data(ttl=3600)
def load_cot_data():
    try:
        df = pd.read_excel("COT.xlsm", sheet_name="Main", engine='openpyxl', usecols="A,B,G,K,P", skiprows=2, header=None)
        df.columns = ['Instrument', 'Net Change', 'Direction', 'COT Index', 'OI Change']
        return df.dropna(subset=['Instrument'])
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
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
                    status = "Increasing 🟢" if (curr_oi - prev_oi) > 0 else "Decreasing 🔴"
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
            data_list.append({'Instrument': name, 'Score': score, 'Volume Confirm': "✅" if vol > avg_vol else "❌"})
        except: pass
    return pd.DataFrame(data_list)

# --- INITIALIZE AI ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    ai_model = genai.GenerativeModel(available_models[0])
except Exception as e:
    st.error(f"AI Error: {e}")
    ai_model = None

# --- UI TABS ---
tab_terminal, tab_risk, tab_psych = st.tabs(["📈 Trading Terminal", "💰 Risk Manager", "🧠 Mindset & Psychology"])

with tab_terminal:
    st.title("📈 Master Trading AI Verified Terminal")
    trading_mode = st.radio("⚙️ Select Trading Engine", ["Intraday (H1 + M30)", "Swing Trading (D1 + H4)"], index=1, horizontal=True)
    
    st.subheader("📊 Market Technicals & Volume")
    df_fx = get_market_data(trading_mode)
    st.dataframe(df_fx, use_container_width=True)
    
    st.subheader("💬 Gemini AI Chat (Manual Queries)")
    user_query = st.text_input("Agar market ke bare mein confusion hai toh AI se puchein...")
    if user_query and ai_model:
        st.info(ai_model.generate_content(user_query).text)

with tab_risk:
    st.title("💰 Risk Manager")
    st.write("Lot size calculator will be here.")

with tab_psych:
    st.title("🧠 Mindset & Psychology")
    st.write("Discipline is the key to success.")
Step 2: Yeh alert_bot.py ka Mukammal Code hai (Email Bot ke liye)
Ab apne GitHub mein alert_bot.py file kholain. Us mein jo kuch likha hai sab mita dein, aur neechay wala AI Scoring (1 to 10) wala code paste kar ke Commit changes kar dein:

Python
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import requests
import smtplib
import os
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta

def send_email_alert(subject, body):
    sender_email = os.environ.get("EMAIL_SENDER")
    sender_password = os.environ.get("EMAIL_PASSWORD")
    receiver_email = os.environ.get("EMAIL_RECEIVER", sender_email)
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
        print("✅ Alert Email Sent!")
    except Exception as e: print(f"❌ Email Error: {e}")

def load_cot_data():
    try:
        df = pd.read_excel("COT.xlsm", sheet_name="Main", engine='openpyxl', usecols="A,B,G,K,P", skiprows=2, header=None)
        df.columns = ['Instrument', 'Net Change', 'Direction', 'COT Index', 'OI Change']
        return df.dropna(subset=['Instrument'])
    except: return pd.DataFrame()

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
                    status = "Increasing 🟢" if (curr_oi - prev_oi) > 0 else "Decreasing 🔴"
                    oi_list.append({'Instrument': symbol, 'Current OI': int(curr_oi), 'Status': status})
        return pd.DataFrame(oi_list)
    except: return pd.DataFrame()

def get_market_data():
    data_list = []
    symbols = {'USD': 'DX-Y.NYB', 'GOLD': 'GC=F', 'EUR': '6E=F', 'GBP': '6B=F', 'JPY': '6J=F', 'AUD': '6A=F', 'CAD': '6C=F', 'CHF': '6S=F'}
    for name, ticker in symbols.items():
        try:
            df = yf.download(ticker, period="1mo", interval="1h", progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.droplevel(1)
            close, sma = df['Close'].iloc[-1], df['Close'].rolling(20).mean().iloc[-1]
            vol, avg_vol = df['Volume'].iloc[-1], df['Volume'].rolling(20).mean().iloc[-1]
            score = 7 if close > sma else 3
            data_list.append({'Instrument': name, 'Score': score, 'Volume Confirm': "✅" if vol > avg_vol else "❌"})
        except: pass
    return pd.DataFrame(data_list)

def get_live_squawk():
    try:
        r = requests.get("https://www.forexlive.com/feed", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        root = ET.fromstring(r.content)
        return [{'title': i.find('title').text} for i in root.findall('.//item')[:5]]
    except: return []

def run_bot():
    print("🔄 Starting AI Bot Scan...")
    api_key = os.environ.get("GEMINI_API_KEY")
    ai_model = None
    if api_key:
        try:
            genai.configure(api_key=api_key)
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            ai_model = genai.GenerativeModel(available_models[0])
        except Exception as e: print(f"AI Error: {e}")

    cot_df = load_cot_data()
    oi_df = load_daily_oi()
    df_fx = get_market_data()
    live_news = get_live_squawk()

    strong = df_fx[df_fx['Score'] >= 6]
    weak = df_fx[df_fx['Score'] <= 4]
    found_setup = False

    if not strong.empty and not weak.empty:
        for _, s in strong.iterrows():
            for _, w in weak.iterrows():
                c1, c2 = s['Instrument'], w['Instrument']
                
                # Sirf Volume verification zaroori hai (AI ko score karne do baqi cheezein)
                if "✅" in s['Volume Confirm'] or "✅" in w['Volume Confirm']:
                    c1_cot = cot_df[cot_df['Instrument'].str.contains(c1, case=False)]['Direction'].values[0] if not cot_df.empty and len(cot_df[cot_df['Instrument'].str.contains(c1, case=False)])>0 else "Neutral"
                    c1_oi = oi_df[oi_df['Instrument'] == c1]['Status'].values[0] if not oi_df.empty and len(oi_df[oi_df['Instrument'] == c1])>0 else "Neutral"
                    
                    order = ['GOLD', 'EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
                    try:
                        pair = f"{c1}{c2}" if order.index(c1) < order.index(c2) else f"{c2}{c1}"
                        action = "BUY" if order.index(c1) < order.index(c2) else "SELL"
                        
                        verdict = "AI verification offline."
                        if ai_model:
                            news_str = "\n".join([n['title'] for n in live_news]) if live_news else "No news"
                            prompt = f"Setup: {action} {pair}. Tech Score: {c1}({s['Score']}) vs {c2}({w['Score']}). Vol is confirmed. COT is {c1_cot}. OI is {c1_oi}. News: {news_str}. Task: Rate this trade out of 10 and give 2 lines reason in Roman Urdu."
                            verdict = ai_model.generate_content(prompt).text
                        
                        now_pkt = datetime.now(timezone(timedelta(hours=5))).strftime('%I:%M %p')
                        body = f"Setup: {action} {pair}\nVolume: Confirmed ✅\n\n🤖 AI Score & Reason:\n{verdict}\n\nTime: {now_pkt} (PKT)"
                        send_email_alert(f"🔔 AI Alert [{pair}]", body)
                        found_setup = True
                    except: pass

    if not found_setup: print("💤 No volume confirmed technical setups right now.")

if __name__ == "__main__":
    run_bot()
