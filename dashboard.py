import yfinance as yf
import pandas as pd
import streamlit as st
import numpy as np
import requests
from datetime import datetime, timezone, timedelta

# --- Dashboard Setup ---
st.set_page_config(page_title="Global Trading Terminal", layout="centered")
st.markdown("""
    <style>
    .main {background-color: #f4f6f9;}
    .sentiment-card {padding: 10px; border-radius: 8px; margin-bottom: 5px; color: white; font-weight: bold; text-align: center; font-size: 0.8rem;}
    .hawkish {background-color: #2ecc71;}
    .dovish {background-color: #e74c3c;}
    .neutral {background-color: #95a5a6;}
    .cot-box {background-color: #ffffff; padding: 15px; border-radius: 10px; border-top: 5px solid #1e3d59; margin-top: 10px;}
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Global Trading Terminal")

# --- Pakistan Time ---
pkt_timezone = timezone(timedelta(hours=5))
now_pkt = datetime.now(pkt_timezone)
st.info(f"🕒 **Last Updated:** {now_pkt.strftime('%I:%M:%S %p')} (PKT)")

# --- 1. COT REPORT (GitHub Excel Integration) ---
st.subheader("📊 Institutional Sentiment (COT Data)")

# Cache hata diya hai taake foran fresh error dikhaye
def load_cot_data():
    try:
        # File read karne ki koshish
        df_cot = pd.read_excel("COT.xlsm", sheet_name="Main", engine='openpyxl')
        return df_cot[['Instruments', 'Net Change', 'Direction', 'COT Index', 'OI Change']]
    except Exception as e:
        return str(e) # Ab yeh exact error wapis bhejayga!

cot_data = load_cot_data()

# Check agar data table ban gaya hai ya error text aaya hai
if isinstance(cot_data, pd.DataFrame):
    st.dataframe(cot_data.head(15), use_container_width=True)
    st.caption("💡 Tip: Net Change (+) aur OI Change (+) ka matlab hai New Positions add ho rahi hain.")
else:
    # Error message ko screen par lal rang mein dikhayega
    st.error(f"⚠️ File load nahi hui. Server ka Error yeh hai: {cot_data}")

# --- 2. Market Analysis (Technicals) ---
futures_symbols = {'USD': 'DX-Y.NYB', 'EUR': '6E=F', 'GBP': '6B=F', 'JPY': '6J=F', 'AUD': '6A=F', 'CAD': '6C=F', 'CHF': '6S=F'}

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

@st.cache_data(ttl=300)
def get_market_data(symbols_dict):
    data_list = []
    for name, ticker in symbols_dict.items():
        try:
            df_d = yf.download(ticker, period="1mo", interval="1d", progress=False)
            df_h4 = yf.download(ticker, period="5d", interval="1h", progress=False) 
            
            if df_d.empty or df_h4.empty: continue
            if isinstance(df_d.columns, pd.MultiIndex): df_d.columns = df_d.columns.droplevel(1)
            if isinstance(df_h4.columns, pd.MultiIndex): df_h4.columns = df_h4.columns.droplevel(1)

            close_d, sma20_d = df_d['Close'].iloc[-1], df_d['Close'].rolling(20).mean().iloc[-1]
            rsi_d = calc_rsi(df_d['Close']).iloc[-1]
            close_h4, sma20_h4 = df_h4['Close'].iloc[-1], df_h4['Close'].rolling(20).mean().iloc[-1]
            
            daily_trend = "UP" if close_d > sma20_d else "DOWN"
            h4_trend = "UP" if close_h4 > sma20_h4 else "DOWN"
            
            score = 5
            if daily_trend == "UP" and h4_trend == "UP": score = 9
            elif daily_trend == "DOWN" and h4_trend == "DOWN": score = 1
            elif daily_trend == "UP" and h4_trend == "DOWN": score = 6
            elif daily_trend == "DOWN" and h4_trend == "UP": score = 4
            
            if rsi_d > 70: score -= 1 
            if rsi_d < 30: score += 1 

            data_list.append({
                'Instrument': name,
                'D1 Trend': daily_trend,
                'H4 Trend': h4_trend,
                'RSI (D1)': round(rsi_d, 2),
                'Master Score': score
            })
        except: pass
    return pd.DataFrame(data_list)

# Analysis Tables
st.markdown("---")
st.subheader("🔍 Currency Futures Analysis (D1 + H4)")
df_fx = get_market_data(futures_symbols)

def style_score(val):
    if val >= 8: return 'background-color: #2ecc71; color: black; font-weight: bold'
    if val <= 3: return 'background-color: #e74c3c; color: white; font-weight: bold'
    return ''

st.dataframe(df_fx.style.map(style_score, subset=['Master Score']), use_container_width=True)

# --- News Section ---
st.markdown("---")
st.subheader("🚨 High Impact News (This Week)")
@st.cache_data(ttl=600)
def get_news():
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        data = requests.get(url, timeout=10).json()
        news_found = False
        
        for event in data:
            if event.get('impact') == 'High':
                try:
                    dt_obj = datetime.fromisoformat(event['date'])
                    pkt_dt = dt_obj.astimezone(pkt_timezone)
                    
                    if pkt_dt.date() >= now_pkt.date():
                        display_date = pkt_dt.strftime("%d %b")
                        display_time = pkt_dt.strftime("%I:%M %p")
                        
                        st.markdown(f"""
                            <div class='news-card'>
                                <b>🔴 {event['country']} - {event['title']}</b><br>
                                <small>Date: {display_date} | Time: {display_time} (PKT) | Forecast: {event.get('forecast', '-')} | Previous: {event.get('previous', '-')}</small>
                            </div>
                        """, unsafe_allow_html=True)
                        news_found = True
                except: pass
        if not news_found:
            st.info("Is hafte mazeed koi High Impact news nahi hai.")
    except: st.error("News load nahi ho sakin.")
get_news()
