import yfinance as yf
import pandas as pd
import streamlit as st
import numpy as np
from datetime import datetime

# --- Dashboard Configuration ---
st.set_page_config(page_title="Futures Strength Dashboard", layout="wide")

# --- Header & Refresh Button ---
col1, col2 = st.columns([4, 1])
with col1:
    st.title("🦅 Pro Futures to Forex Dashboard")
    st.write("Yeh system individual Currency Futures ko analyze kar ke highest probability Forex Pair nikalta hai.")
with col2:
    st.write("") # Thori space ke liye
    if st.button("🔄 Refresh Data Now"):
        st.cache_data.clear() # Purana cache delete karega
        st.rerun() # Page ko fresh data ke sath reload karega

# Updated Time Show Karne Ke Liye
st.info(f"🕒 **Last Market Data Updated:** {datetime.now().strftime('%I:%M:%S %p')}")

# --- Currency Futures Symbols ---
futures_symbols = {
    'USD': 'DX-Y.NYB', 
    'EUR': '6E=F',     
    'GBP': '6B=F',     
    'JPY': '6J=F',     
    'AUD': '6A=F',     
    'CAD': '6C=F',     
    'CHF': '6S=F'      
}

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

@st.cache_data(ttl=300) 
def get_futures_data():
    data_list = []
    
    for currency, ticker in futures_symbols.items():
        try:
            df = yf.download(ticker, period="1mo", interval="1d", progress=False)
            if df.empty: continue
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
                
            close_price = df['Close'].iloc[-1]
            prev_close = df['Close'].iloc[-2]
            
            daily_change = ((close_price - prev_close) / prev_close) * 100
            df['RSI'] = calc_rsi(df['Close'])
            current_rsi = df['RSI'].iloc[-1]
            
            sma_20 = df['Close'].rolling(20).mean().iloc[-1]
            structure = "⬆️ Bullish" if close_price > sma_20 else "⬇️ Bearish"
            
            score = 5
            if current_rsi > 55: score += 2 
            elif current_rsi < 45: score -= 2 
            
            if close_price > sma_20: score += 3 
            else: score -= 3 
            
            final_score = round(score + daily_change, 3)
            
            data_list.append({
                'Currency': currency,
                'Close Price': round(close_price, 4),
                'Change (%)': round(daily_change, 2),
                'Structure': structure,
                'RSI (14)': round(current_rsi, 2),
                'Strength Score': final_score
            })
        except:
            pass 
            
    return pd.DataFrame(data_list)

df = get_futures_data()

# --- UI Highlighting ---
def highlight_strength(val):
    if val >= 7: return 'background-color: #00FF00; color: black; font-weight: bold'
    elif val <= 3: return 'background-color: #FF4136; color: white; font-weight: bold'
    return ''

st.subheader("1️⃣ Currency Futures Strength Meter")
st.dataframe(df.style.map(highlight_strength, subset=['Strength Score']), use_container_width=True)

# --- Pair Derivation Engine ---
st.markdown("---")
st.subheader("2️⃣ Derived Highest Probability Trade")

if not df.empty:
    strongest = df.loc[df['Strength Score'].idxmax()]
    weakest = df.loc[df['Strength Score'].idxmin()]
    
    currency_order = ['EUR', 'GBP', 'AUD', 'USD', 'CAD', 'CHF', 'JPY']
    c1 = strongest['Currency']
    c2 = weakest['Currency']
    
    if currency_order.index(c1) < currency_order.index(c2):
        pair = f"{c1}{c2}"
        action = "BUY 🟢"
        reason = f"{c1} strong hai aur {c2} weak hai."
    else:
        pair = f"{c2}{c1}"
        action = "SELL 🔴"
        reason = f"{c1} strong hai is liye hum {c2} ko sell kar rahay hain."
        
    st.success(f"### 🎯 Recommended Trade Setup: **{action} {pair}**")
    st.info(f"**Reason:** {reason}")