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

# --- EMAIL ALERT FUNCTION ---
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
        print("✅ Alert Email Sent Successfully!")
    except Exception as e:
        print(f"❌ Email Error: {e}")

# =========================================================================
# --- SAME BACKEND DATA FUNCTIONS (Identical to Dashboard) ---
# =========================================================================
def load_cot_data():
    try:
        df_cot = pd.read_excel("COT.xlsm", sheet_name="Main", engine='openpyxl', usecols="A,B,G,K,P", skiprows=2, header=None)
        df_cot.columns = ['Instrument', 'Net Change', 'Direction', 'COT Index', 'OI Change']
        return df_cot.dropna(subset=['Instrument'])
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
                    change = curr_oi - prev_oi
                    status = "Increasing 🟢" if change > 0 else "Decreasing 🔴"
                    oi_list.append({'Instrument': symbol, 'Current OI': int(curr_oi), 'Status': status})
        return pd.DataFrame(oi_list)
    except: return pd.DataFrame()

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

def get_live_squawk():
    try:
        r = requests.get("https://www.forexlive.com/feed", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        root = ET.fromstring(r.content)
        return [{'title': i.find('title').text} for i in root.findall('.//item')[:5]]
    except: return []

# --- MAIN BOT LOGIC ---
def run_bot():
    print("🔄 Starting 30-Min Market Scan...")
    
    # Initialize AI
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    
    # Auto-Detect Model (Google se khud poochay ga)
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    best_model = available_models[0] # Jo model available ho wo utha lo
    ai_model = genai.GenerativeModel(best_model)
except Exception as e:
    st.error(f"AI Error: {e}")
    api_key = None
    ai_model = None

    # Load Data (Same as Dashboard)
    trading_mode = "Swing Trading (D1 + H4)" # Aap ka selected mode
    cot_df = load_cot_data()
    oi_df = load_daily_oi()
    df_fx = get_market_data(trading_mode)
    live_news = get_live_squawk()

    strong = df_fx[df_fx['Score'] >= 6]
    weak = df_fx[df_fx['Score'] <= 4]
    found_setup = False

    if not strong.empty and not weak.empty:
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
                
                # If All Aligned (Strict Rules matched!)
                if cot_align and oi_align and ("✅" in s['Volume Confirm'] or "✅" in w['Volume Confirm']):
                    order = ['GOLD', 'EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
                    try:
                        if order.index(c1) < order.index(c2): pair, action = f"{c1}{c2}", "BUY"
                        else: pair, action = f"{c2}{c1}", "SELL"
                        
                        print(f"🔥 Setup Detected: {action} {pair}")
                        
                        # AI Verification
                        verdict = "⚠️ AI verification offline."
                        if ai_model:
                            print("🤖 AI Verifying...")
                            news_str = "\n".join([n['title'] for n in live_news]) if live_news else "No major news"
                            prompt = f"Expert Analyst: {action} setup on {pair}. Strength {s['Score']} vs {w['Score']}. COT/Vol/OI Aligned. Live News: {news_str}. Batao yeh trade safe hai ya news risk? (Roman Urdu, 2 lines max)"
                            response = ai_model.generate_content(prompt)
                            verdict = response.text
                        
                        # Time formatting
                        pkt_timezone = timezone(timedelta(hours=5))
                        now_pkt = datetime.now(pkt_timezone)
                        
                        # Send Email
                        email_subject = f"🚨 AI Setup Alert: {action} {pair}"
                        email_body = f"Hussain Algo Terminal (24/7 Watchdog)\n\nSetup: {action} {pair}\nStrength: {s['Score']} vs {w['Score']}\n\n🤖 AI Verdict:\n{verdict}\n\nTime: {now_pkt.strftime('%I:%M %p')} (PKT)\nMode: {trading_mode}"
                        
                        send_email_alert(email_subject, email_body)
                        found_setup = True
                    except Exception as e:
                        print(f"Error processing {c1}{c2}: {e}")

    if not found_setup:
        print("💤 No active institutional setup found right now. Sleeping till next cycle.")

if __name__ == "__main__":
    print("📧 Sending Manual Test Email...")
    send_email_alert("🚀 Hussain Algo: Connection Test", "Alhamdulillah! Aap ka 24/7 Bot ab emails bhej raha hai aur AI verification bhi theek kaam kar rahi hai.")
    run_bot()
