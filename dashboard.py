import yfinance as yf
import pandas as pd
import streamlit as st
import numpy as np
from datetime import datetime, timezone, timedelta

# --- 14. Classic Design & UI Tweaks ---
st.set_page_config(page_title="Trading Dashboard", layout="centered")
st.markdown("""
    <style>
    .main {background-color: #f4f6f9;}
    h1 {color: #1e3d59; font-family: 'Segoe UI', sans-serif; font-weight: bold;}
    h2, h3 {color: #ff6e40;}
    .caution-box {background-color: #ff9a3c; padding: 12px; border-radius: 8px; color: black; font-weight: bold; border-left: 6px solid #d35400; margin-bottom: 10px;}
    .news-box {background-color: #ffffff; padding: 15px; border-radius: 8px; box-shadow: 0px 4px 6px rgba(0,0,0,0.1); border-left: 6px solid #1e3d59;}
    </style>
""", unsafe_allow_html=True)

# --- 1 & 2. Title Update ---
st.title("📊 Trading Dashboard")

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
            
            # --- 6. Only Net Change ---
            net_change = ((close_price - prev_close) / prev_close) * 100
            
            df['RSI'] = calc_rsi(df['Close'])
            current_rsi = df['RSI'].iloc[-1]
            
            # --- 7. Basic Structure ---
            sma_20 = df['Close'].rolling(20).mean().iloc[-1]
            structure = "Trending" if close_price > sma_20 else "Volatile" 
            
            score = 5
            if current_rsi >= 75: score += 2 
            elif current_rsi <= 25: score -= 2 
            if close_price > sma_20: score += 3 
            else: score -= 3 
            
            final_score = round(score + net_change, 3)
            
            # --- 10. Remarks based on RSI and Score ---
            remarks = "Normal"
            if final_score >= 8 and current_rsi >= 75:
                remarks = "⚠️ Extreme Overbought"
            elif final_score <= 4 and current_rsi <= 25:
                remarks = "⚠️ Extreme Oversold"
            elif current_rsi >= 75:
                remarks = "RSI High (Watch)"
            elif current_rsi <= 25:
                remarks = "RSI Low (Watch)"

            data_list.append({
                'Currency': currency,
                'Net Change (%)': round(net_change, 2),
                'Structure': structure,
                'RSI (14)': round(current_rsi, 2),
                'Strength Score': final_score,
                'Remarks': remarks
            })
        except: pass 
            
    df_res = pd.DataFrame(data_list)
    # --- 5. Index Starts at 1 ---
    df_res.index = np.arange(1, len(df_res) + 1)
    return df_res

# --- 3. Refresh Button ---
col1, col2 = st.columns([4, 1])
with col2:
    st.write("") 
    if st.button("🔄 Refresh Data Now", use_container_width=True):
        get_futures_data.clear() 
        st.rerun()

# --- PAKISTAN TIME LOGIC (UTC + 5) ---
pkt_timezone = timezone(timedelta(hours=5))
pkt_time = datetime.now(pkt_timezone).strftime('%I:%M:%S %p')
st.info(f"🕒 **Last Updated:** {pkt_time} (PKT)")

df = get_futures_data()

# --- 9. Colors ---
def highlight_cells(val):
    if isinstance(val, (int, float)):
        if val >= 8: return 'background-color: #2ecc71; color: black; font-weight: bold'
        elif val <= 4: return 'background-color: #e74c3c; color: white; font-weight: bold'
    return ''

def highlight_remarks(val):
    if "⚠️" in str(val): return 'color: #c0392b; font-weight: bold'
    return ''

# --- 4. Analysis Phase ---
st.markdown("---")
st.subheader("🔍 Analysis Phase")
st.dataframe(df.style.map(highlight_cells, subset=['Strength Score']).map(highlight_remarks, subset=['Remarks']))

# --- 11. Recommendation Section ---
st.markdown("---")
st.subheader("🎯 Recommendation")

if not df.empty:
    # --- 8. Filter Logic ---
    strong_candidates = df[(df['Strength Score'] >= 8) & (df['RSI (14)'] < 75)]
    weak_candidates = df[(df['Strength Score'] <= 4) & (df['RSI (14)'] > 25)]
    
    # --- 12. Caution Section ---
    extreme_strong = df[(df['Strength Score'] >= 8) & (df['RSI (14)'] >= 75)]
    extreme_weak = df[(df['Strength Score'] <= 4) & (df['RSI (14)'] <= 25)]
    
    currency_order = ['EUR', 'GBP', 'AUD', 'USD', 'CAD', 'CHF', 'JPY']
    
    st.write("#### 🟢 Valid Trade Setups")
    if not strong_candidates.empty and not weak_candidates.empty:
        for _, s_row in strong_candidates.iterrows():
            for _, w_row in weak_candidates.iterrows():
                c1, c2 = s_row['Currency'], w_row['Currency']
                if currency_order.index(c1) < currency_order.index(c2):
                    pair = f"{c1}{c2}"
                    st.success(f"**BUY {pair}** -> ({c1} is Strong, {c2} is Weak)")
                else:
                    pair = f"{c2}{c1}"
                    st.success(f"**SELL {pair}** -> ({c1} is Strong, {c2} is Weak)")
    else:
        st.info("Filhal koi clear high-probability setup nahi hai. Market conditions ranging hain.")

    st.write("#### ⚠️ Extreme Conditions (Caution)")
    if not extreme_strong.empty:
        for _, row in extreme_strong.iterrows():
            st.markdown(f"<div class='caution-box'>🚫 <b>Avoid Buying {row['Currency']} Pairs:</b> Score is High ({row['Strength Score']}) but RSI is Overbought ({row['RSI (14)']}). Wait for Pullback.</div>", unsafe_allow_html=True)
            
    if not extreme_weak.empty:
        for _, row in extreme_weak.iterrows():
            st.markdown(f"<div class='caution-box'>🚫 <b>Avoid Selling {row['Currency']} Pairs:</b> Score is Low ({row['Strength Score']}) but RSI is Oversold ({row['RSI (14)']}). Wait for Bounce.</div>", unsafe_allow_html=True)

# --- 13. News Section ---
st.markdown("---")
st.subheader("📰 Market News & Events")
st.markdown("""
<div class='news-box'>
    <b>Live Forex Factory News Feed</b><br>
    <i>Yeh section aglay phase mein live news API ke zariye connect hoga taake aap ko time aur impact pata chal sakay.</i>
</div>
""", unsafe_allow_html=True)
