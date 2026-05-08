import yfinance as yf
import pandas as pd
import google.generativeai as genai
import requests
import smtplib
import os
import xml.etree.ElementTree as ET
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import pytz

# ==========================================
# 1. ANTI-SPAM MEMORY ENGINE
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
        return True
    except Exception as e:
        print(f"❌ Email Error: {e}")
        return False

# ==========================================
# 2. MARKET DATA ENGINE (Wyckoff VSA Only)
# ==========================================
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
            if df.empty or len(df) < 25: 
                strengths[curr] = {"status": "Neutral", "reason": "Not Enough Data"}
                continue
            
            # Volume & Structure Analysis
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

def get_live_squawk():
    squawk = []
    try:
        r = requests.get("https://www.forexlive.com/feed", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        root = ET.fromstring(r.content)
        for i, item in enumerate(root.findall('.//item')):
            if i >= 5: break
            squawk.append({'Headline': item.find('title').text})
    except: pass
    return squawk

# ==========================================
# 3. AI VERIFICATION ENGINE
# ==========================================
def verify_signal_with_ai(ai_model, action, pair, logic, squawk_list):
    if not ai_model: return "⚠️ AI Offline"
    news_str = "\n".join([n['Headline'] for n in squawk_list]) if squawk_list else "No major news"
    prompt = f"Expert Analyst: {action} setup on {pair}. Logic: {logic}. Live News: {news_str}. Batao yeh trade safe hai ya news risk? (Roman Urdu, 2 lines max)"
    try:
        response = ai_model.generate_content(prompt)
        return response.text
    except: return "⚠️ AI Error"

# ==========================================
# 4. MAIN EXECUTION LOOP
# ==========================================
def run_bot():
    print("🔄 Starting Auto-Scan (GitHub Actions)...")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    ai_model = None
    if api_key:
        genai.configure(api_key=api_key)
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name.lower():
                ai_model = genai.GenerativeModel(m.name.replace('models/', ''))
                break
    
    currency_strengths = get_all_currency_strengths()
    live_news = get_live_squawk()
    
    forex_pairs = [
        'EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY', 
        'EURJPY', 'GBPJPY', 'AUDJPY', 'XAUUSD'
    ]
    
    found_setup = False
    for pair in forex_pairs:
        raw_sig = check_pair_alignment(pair, currency_strengths)
        if raw_sig:
            action, logic = raw_sig['Type'], raw_sig['Logic']
            print(f"🏗️ Phase 1 Technical Setup Match: {action} {pair}")
            
            # Memory Check (Anti-Spam)
            if not is_already_sent(pair, action):
                print("🤖 Verifying with AI Phase 2...")
                verdict = verify_signal_with_ai(ai_model, action, pair, logic, live_news)
                
                if "Error" not in verdict and "Offline" not in verdict:
                    now_pkt = datetime.now(pytz.timezone('Asia/Karachi'))
                    email_subject = f"Setup: {action} {pair}"
                    email_body = f"Hussain Algo Terminal (24/7 Background Watchdog)\n\nSetup: {action} {pair}\nLogic: {logic}\n\n🤖 AI Verdict:\n{verdict}\n\nTime: {now_pkt.strftime('%I:%M %p')} (PKT)"
                    
                    if send_email_alert(email_subject, email_body):
                        mark_as_sent(pair, action)
                        found_setup = True
            else:
                print(f"⏭️ {action} {pair} alert already sent today. Skipping to avoid spam.")

    if not found_setup:
        print("💤 No new unique setups found in this cycle.")

if __name__ == "__main__":
    run_bot()
File 2: .yml File (GitHub Actions Workflow)
Jo file aap ke .github/workflows/ folder ke andar mojood hai (algo_bot.yml ya jo bhi aap ne naam rakha hai), us ka purana code mita kar sirf yeh code paste karein, aur Commit changes kar dein:

YAML
name: Algo Trading Bot Auto-Run

on:
  schedule:
    - cron: '*/30 * * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  run-bot:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install Dependencies
        run: |
          pip install yfinance pandas requests google-generativeai pytz openpyxl

      - name: Run AlertBot
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          EMAIL_SENDER: ${{ secrets.EMAIL_SENDER }}
          EMAIL_PASSWORD: ${{ secrets.EMAIL_PASSWORD }}
        run: python alert_bot.py

      - name: Commit and Push sent alerts memory
        run: |
          git config --local user.email "action@github.com"
          git config --local user.name "GitHub Action"
          touch sent_alerts.txt
          git add sent_alerts.txt
          git commit -m "Auto-update sent alerts memory" || echo "No new alerts to save"
          git push
