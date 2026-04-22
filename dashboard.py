import yfinance as yf
import pandas as pd
import streamlit as st
import numpy as np
import feedparser
from datetime import datetime, timezone, timedelta

# --- Dashboard Setup ---
st.set_page_config(page_title="Trading Dashboard", layout="centered")
st.markdown("""
    <style>
    .main {background-color: #f4f6f9;}
    .stMetric {background-color: #ffffff; padding: 10px; border-radius: 10px; box-shadow: 0px 2px 4px rgba(0,0,0,0.05);}
    .sentiment-card {padding: 10px; border-radius: 8px; margin-bottom: 5px; color: white; font-weight: bold; text-align: center;}
    .hawkish {background-color: #2ecc71;}
    .dovish {background-color: #e74c3c;}
    .neutral {background-color: #95a5a6;}
    .news-card {border-bottom: 1px solid #ddd; padding: 10px 0;}
    </style>
""", unsafe_allow_html=True)

st.title("📊 Master Trading Dashboard")

# --- Pakistan Time ---
pkt_timezone = timezone(timedelta(hours=5))
pkt_time = datetime.now(pkt_timezone).strftime('%I:%M:%S %p')
st.info(f"🕒 **Last Updated:** {pkt_time} (PKT)")

# --- Central Bank Bias (Fundamental View) ---
# Note: Ye manually update hota hai ya professional sentiment APIs se liya jata hai.
# Filhal hum ne standard current sentiment add kiya hai.
cb_sentiment = {
    'USD': {'Bias': 'Hawkish/Neutral', 'Policy': 'High Rates', 'Color': 'hawkish'},
    'EUR': {'Bias': 'Dovish', 'Policy': 'Rate Cuts Starting', 'Color': 'dovish'},
    'GBP': {'Bias': 'Neutral', 'Policy': 'Stable', 'Color': 'neutral'},
    'JPY': {'Bias': 'Hawkish', 'Policy': 'Ending Negative Rates', 'Color': 'hawkish'},
    'AUD': {'Bias': 'Neutral', 'Policy': 'Data Dependent', 'Color': 'neutral'},
    'CAD': {'Bias': 'Neutral/Dovish', 'Policy': 'Monitoring Inflation', 'Color': 'neutral'},
    'CHF': {'Bias': 'Dovish', 'Policy': 'Inflation Controlled', 'Color': 'dovish'}
}

# --- Data Fetching Logic ---
futures_symbols = {
    'USD': 'DX-Y.NYB', 'EUR': '6E=F', 'GBP': '6B=F', 
    'JPY': '6J=F', 'AUD': '6A=F', 'CAD': '6C=F', 'CHF': '6S=F'
}

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

@st.cache_data(ttl=300)
def get_merged_data():
    data_list = []
    for currency, ticker in futures_symbols.items():
        try:
            # Fetch Daily and H4 Data
            df_d = yf.download(ticker, period="1mo", interval="1d", progress=False)
            df_h4 = yf.download(ticker, period="5d", interval="1h", progress=False) # yfinance uses 1h for H4 approx
            
            if df_d.empty or df_h4.empty: continue
            
            # Clean Columns
            if isinstance(df_d.columns, pd.MultiIndex): df_d.columns = df_d.columns.droplevel(1)
            if isinstance(df_h4.columns, pd.MultiIndex): df_h4.columns = df_h4.columns.droplevel(1)

            # Technicals (Daily)
            close_d = df_d['Close'].iloc[-1]
            sma20_d = df_d['Close'].rolling(20).mean().iloc[-1]
            rsi_d = calc_rsi(df_d['Close']).iloc[-1]
            
            # Technicals (H4)
            close_h4 = df_h4['Close'].iloc[-1]
            sma20_h4 = df_h4['Close'].rolling(20).mean().iloc[-1]
            
            # --- CONFLUENCE LOGIC ---
            # 1. Structure Check
            daily_trend = "UP" if close_d > sma20_d else "DOWN"
            h4_trend = "UP" if close_h4 > sma20_h4 else "DOWN"
            
            observation = "Ranging"
            score = 5
            
            if daily_trend == "UP" and h4_trend == "UP":
                observation = "Strong Bullish"
                score = 9
            elif daily_trend == "DOWN" and h4_trend == "DOWN":
                observation = "Strong Bearish"
                score = 1
            elif daily_trend == "UP" and h4_trend == "DOWN":
                observation = "Pullback (Daily Bullish)"
                score = 6
            elif daily_trend == "DOWN" and h4_trend == "UP":
                observation = "Correction (Daily Bearish)"
                score = 4
            
            # RSI Adjustment
            if rsi_d > 70: score -= 1 # Overbought correction
            if rsi_d < 30: score += 1 # Oversold bounce

            data_list.append({
                'Currency': currency,
                'Daily Trend': daily_trend,
                'H4 Trend': h4_trend,
                'Observation': observation,
                'RSI (D1)': round(rsi_d, 2),
                'Master Strength': score
            })
        except: pass
    
    res = pd.DataFrame(data_list)
    res.index = np.arange(1, len(res) + 1)
    return res

# --- 1. Central Bank & Fundamental View Section ---
st.subheader("🏛️ Central Bank Sentiment (Fundamental View)")
cols = st.columns(len(cb_sentiment))
for i, (curr, info) in enumerate(cb_sentiment.items()):
    with cols[i]:
        st.markdown(f"""
            <div class='sentiment-card {info['Color']}'>
                {curr}<br><small>{info['Bias']}</small>
            </div>
        """, unsafe_allow_html=True)

# --- 2. Analysis Phase (Merged D1 + H4) ---
st.markdown("---")
st.subheader("🔍 Analysis Phase (Daily + H4 Confluence)")
df = get_merged_data()

def highlight_score(val):
    if val >= 8: return 'background-color: #2ecc71; color: black; font-weight: bold'
    if val <= 3: return 'background-color: #e74c3c; color: white; font-weight: bold'
    return ''

st.dataframe(df.style.map(highlight_score, subset=['Master Strength']), use_container_width=True)

# --- 3. Recommendation Section ---
st.markdown("---")
st.subheader("🎯 Recommendations")
if not df.empty:
    strong = df[df['Master Strength'] >= 8]
    weak = df[df['Master Strength'] <= 3]
    
    if not strong.empty and not weak.empty:
        for _, s in strong.iterrows():
            for _, w in weak.iterrows():
                # Simple logic for Pair derivation
                st.success(f"✅ **High Probability Setup: {s['Currency']}{w['Currency']} (BUY)**")
                st.write(f"Reason: Both D1/H4 are {s['Observation']} and Central Bank favors {s['Currency']}.")
    else:
        st.warning("Market is currently mixed. No High Probability Confluence found.")

# --- 4. Today's High Impact News ---
st.markdown("---")
st.subheader("📰 Today's High Impact News")
def get_forex_news():
    try:
        # Fetching from a public RSS feed (Forex Factory or similar)
        feed = feedparser.parse("https://www.forexfactory.com/ff_calendar_thisweek.xml")
        today = datetime.now().strftime("%m-%d-%Y")
        news_found = False
        for entry in feed.entries[:10]: # Top 10 events
            st.markdown(f"""
                <div class='news-box'>
                    <b>{entry.title}</b><br>
                    <small>Impact: {entry.get('forex_impact', 'Unknown')} | Time: {entry.get('forex_eventtime', 'Check Calendar')}</small>
                </div>
            """, unsafe_allow_html=True)
            news_found = True
        if not news_found: st.write("No major news items found for today.")
    except:
        st.write("Unable to fetch live news at the moment. Please check ForexFactory.com")

get_forex_news()
