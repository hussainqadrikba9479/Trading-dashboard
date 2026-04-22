import yfinance as yf
import pandas as pd
import streamlit as st
import numpy as np
import requests
from datetime import datetime, timezone, timedelta

# --- Dashboard Setup ---
st.set_page_config(page_title="Global Trading Terminal", layout="wide")
st.markdown("""
    <style>
    .main {background-color: #f4f6f9;}
    .sentiment-card {padding: 10px; border-radius: 8px; margin-bottom: 5px; color: white; font-weight: bold; text-align: center; font-size: 0.8rem;}
    .hawkish {background-color: #2ecc71;}
    .dovish {background-color: #e74c3c;}
    .neutral {background-color: #95a5a6;}
    .news-card {border-left: 6px solid #e74c3c; background-color: #ffffff; padding: 12px; border-radius: 8px; box-shadow: 0px 4px 6px rgba(0,0,0,0.1); margin-bottom: 10px;}
    </style>
""", unsafe_allow_html=True)

st.title("🦅 Global Trading Terminal (VSA + COT Edition)")

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
    except Exception as e: return str(e)

cot_df = load_cot_data()
if isinstance(cot_df, pd.DataFrame):
    st.dataframe(cot_df.head(12), use_container_width=True, hide_index=True)
else:
    st.error(f"⚠️ COT File Load Error: {cot_df}")

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

            close_d = df_d['Close'].iloc[-1]
            prev_close_d = df_d['Close'].iloc[-2]
            sma20_d = df_d['Close'].rolling(20).mean().iloc[-1]
            rsi_d = calc_rsi(df_d['Close']).iloc[-1]
            close_h4 = df_h4['Close'].iloc[-1]
            sma20_h4 = df_h4['Close'].rolling(20).mean().iloc[-1]
            
            daily_trend = "UP" if close_d > sma20_d else "DOWN"
            h4_trend = "UP" if close_h4 > sma20_h4 else "DOWN"
            
            score = 5
            if daily_trend == "UP" and h4_trend == "UP": score = 9
            elif daily_trend == "DOWN" and h4_trend == "DOWN": score = 1
            elif daily_trend == "UP" and h4_trend == "DOWN": score = 6
            elif daily_trend == "DOWN" and h4_trend == "UP": score = 4
            if rsi_d > 70: score -= 1 
            if rsi_d < 30: score += 1 

            # --- VSA LOGIC ---
            high, low, vol = df_d['High'].iloc[-1], df_d['Low'].iloc[-1], df_d['Volume'].iloc[-1]
            prev_vol, prev_prev_vol = df_d['Volume'].iloc[-2], df_d['Volume'].iloc[-3]
            avg_vol = df_d['Volume'].rolling(20).mean().iloc[-1]
            spread = high - low
            avg_spread = (df_d['High'] - df_d['Low']).rolling(20).mean().iloc[-1]
            close_pos = (close_d - low) / spread if spread > 0 else 0.5
            
            vsa_signal = "Neutral"
            if (close_d > prev_close_d) and (spread > avg_spread) and (close_pos < 0.3) and (vol > avg_vol * 1.2):
                vsa_signal = "🚨 Upthrust (SOW)"
            elif (close_d < prev_close_d) and (spread > avg_spread) and (close_pos > 0.7) and (vol > avg_vol * 1.2):
                vsa_signal = "🟢 Shakeout (SOS)"
            elif (close_d > prev_close_d) and (spread < avg_spread) and (vol < prev_vol) and (vol < prev_prev_vol):
                vsa_signal = "📉 No Demand"
            elif (close_d < prev_close_d) and (spread < avg_spread) and (vol < prev_vol) and (vol < prev_prev_vol):
                vsa_signal = "📈 No Supply"

            data_list.append({'Instrument': name, 'D1': daily_trend, 'H4': h4_trend, 'RSI': round(rsi_d, 2), 'VSA': vsa_signal, 'Score': score})
        except: pass
    return pd.DataFrame(data_list)

# Tables UI
st.markdown("---")
st.subheader("🔍 Market Analysis Phase")
df_fx = get_market_data(futures_symbols)

def style_score(val):
    if val >= 8: return 'background-color: #2ecc71; color: black; font-weight: bold'
    if val <= 3: return 'background-color: #e74c3c; color: white; font-weight: bold'
    return ''

st.dataframe(df_fx.style.map(style_score, subset=['Score']), use_container_width=True, hide_index=True)

# --- 3. STRICT RECOMMENDATIONS SECTION (Technical + VSA Locked) ---
st.markdown("---")
st.subheader("🎯 Refined Trade Recommendations (Technicals + VSA)")
if not df_fx.empty:
    strong = df_fx[df_fx['Score'] >= 8]
    weak = df_fx[df_fx['Score'] <= 3]
    found = False
    
    for _, s in strong.iterrows():
        for _, w in weak.iterrows():
            c1, c2 = s['Instrument'], w['Instrument']
            s_vsa, w_vsa = str(s['VSA']), str(w['VSA'])
            
            # Rule 1: No Contradiction (Filter out opposing volume signals)
            if "SOW" in s_vsa or "Demand" in s_vsa: continue # Strong pair rejecting higher prices
            if "SOS" in w_vsa or "Supply" in w_vsa: continue # Weak pair rejecting lower prices
            
            # Rule 2: VSA Confirmation (At least one must have active Smart Money footprint)
            vsa_confirmed = False
            if "SOS" in s_vsa or "Supply" in s_vsa: vsa_confirmed = True
            if "SOW" in w_vsa or "Demand" in w_vsa: vsa_confirmed = True
            
            if vsa_confirmed:
                order = ['EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
                try:
                    if order.index(c1) < order.index(c2): pair, action = f"{c1}{c2}", "BUY"
                    else: pair, action = f"{c2}{c1}", "SELL"
                    
                    st.success(f"✅ **{action} {pair}** | Double Confluence 🚀")
                    st.write(f"**Smart Money Footprint:** {c1} ({s_vsa}) vs {c2} ({w_vsa})")
                    found = True
                except: pass
                
    if not found: st.warning("Filhal strict criteria (Technicals + VSA) par koi trade setup nahi mila. Market ka wait karein.")

# --- 4. NEWS ---
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
    except: st.error("News error.")
get_news()
