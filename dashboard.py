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
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Global Trading Terminal (VSA Powered)")

# --- Pakistan Time ---
pkt_timezone = timezone(timedelta(hours=5))
now_pkt = datetime.now(pkt_timezone)
st.info(f"🕒 **Last Updated:** {now_pkt.strftime('%I:%M:%S %p')} (PKT)")

# --- 1. COT REPORT ---
st.subheader("📊 Institutional Sentiment (COT Data)")

@st.cache_data(ttl=3600)
def load_cot_data():
    try:
        df_cot = pd.read_excel("COT.xlsm", sheet_name="Main", engine='openpyxl', usecols="A,B,G,K,P", skiprows=2, header=None)
        df_cot.columns = ['Instrument', 'Net Change', 'Direction', 'COT Index', 'OI Change']
        df_cot = df_cot.dropna(subset=['Instrument'])
        return df_cot
    except Exception as e:
        return str(e)

cot_data = load_cot_data()

if isinstance(cot_data, pd.DataFrame):
    st.dataframe(cot_data.head(15), use_container_width=True, hide_index=True)
else:
    st.error(f"⚠️ COT File load error: {cot_data}")

# --- 2. Market Analysis & VSA Engine ---
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
            df_d = yf.download(ticker, period="2mo", interval="1d", progress=False)
            df_h4 = yf.download(ticker, period="5d", interval="1h", progress=False) 
            
            if df_d.empty or df_h4.empty: continue
            if isinstance(df_d.columns, pd.MultiIndex): df_d.columns = df_d.columns.droplevel(1)
            if isinstance(df_h4.columns, pd.MultiIndex): df_h4.columns = df_h4.columns.droplevel(1)

            # Technicals
            close_d = df_d['Close'].iloc[-1]
            prev_close_d = df_d['Close'].iloc[-2]
            sma20_d = df_d['Close'].rolling(20).mean().iloc[-1]
            rsi_d = calc_rsi(df_d['Close']).iloc[-1]
            close_h4 = df_h4['Close'].iloc[-1]
            sma20_h4 = df_h4['Close'].rolling(20).mean().iloc[-1]
            
            daily_trend = "UP" if close_d > sma20_d else "DOWN"
            h4_trend = "UP" if close_h4 > sma20_h4 else "DOWN"
            
            # Master Score Logic
            score = 5
            if daily_trend == "UP" and h4_trend == "UP": score = 9
            elif daily_trend == "DOWN" and h4_trend == "DOWN": score = 1
            elif daily_trend == "UP" and h4_trend == "DOWN": score = 6
            elif daily_trend == "DOWN" and h4_trend == "UP": score = 4
            
            if rsi_d > 70: score -= 1 
            if rsi_d < 30: score += 1 

            # --- TOM WILLIAMS VSA LOGIC ---
            high = df_d['High'].iloc[-1]
            low = df_d['Low'].iloc[-1]
            vol = df_d['Volume'].iloc[-1]
            prev_vol = df_d['Volume'].iloc[-2]
            prev_prev_vol = df_d['Volume'].iloc[-3]
            
            avg_vol = df_d['Volume'].rolling(20).mean().iloc[-1]
            spread = high - low
            avg_spread = (df_d['High'] - df_d['Low']).rolling(20).mean().iloc[-1]
            
            close_pos = (close_d - low) / spread if spread > 0 else 0.5
            
            vsa_signal = "Neutral"
            
            # 1. Upthrust (SOW) - Wide spread, High Vol, Closes in bottom 30%
            if (close_d > prev_close_d) and (spread > avg_spread) and (close_pos < 0.3) and (vol > avg_vol * 1.2):
                vsa_signal = "🚨 Upthrust (SOW)"
            
            # 2. Shakeout / Stopping Volume (SOS) - Wide spread, High Vol, Closes in top 30%
            elif (close_d < prev_close_d) and (spread > avg_spread) and (close_pos > 0.7) and (vol > avg_vol * 1.2):
                vsa_signal = "🟢 Shakeout (SOS)"
                
            # 3. No Demand - Up bar, narrow spread, volume less than previous 2 bars
            elif (close_d > prev_close_d) and (spread < avg_spread) and (vol < prev_vol) and (vol < prev_prev_vol):
                vsa_signal = "📉 No Demand"
                
            # 4. No Supply - Down bar, narrow spread, volume less than previous 2 bars
            elif (close_d < prev_close_d) and (spread < avg_spread) and (vol < prev_vol) and (vol < prev_prev_vol):
                vsa_signal = "📈 No Supply"

            data_list.append({
                'Instrument': name,
                'D1 Trend': daily_trend,
                'H4 Trend': h4_trend,
                'RSI (D1)': round(rsi_d, 2),
                'VSA Footprint': vsa_signal,
                'Master Score': score
            })
        except: pass
    return pd.DataFrame(data_list)

# Analysis Tables
st.markdown("---")
st.subheader("🔍 Technicals & VSA Footprints")
df_fx = get_market_data(futures_symbols)

def style_score(val):
    if val >= 8: return 'background-color: #2ecc71; color: black; font-weight: bold'
    if val <= 3: return 'background-color: #e74c3c; color: white; font-weight: bold'
    return ''

def style_vsa(val):
    if 'SOS' in val or 'Supply' in val: return 'color: #2ecc71; font-weight: bold'
    if 'SOW' in val or 'Demand' in val: return 'color: #e74c3c; font-weight: bold'
    return ''

st.dataframe(df_fx.style.map(style_score, subset=['Master Score']).map(style_vsa, subset=['VSA Footprint']), use_container_width=True, hide_index=True)

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
                            <div style='border-left: 6px solid #e74c3c; background-color: #ffffff; padding: 12px; border-radius: 8px; box-shadow: 0px 4px 6px rgba(0,0,0,0.1); margin-bottom: 10px;'>
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
