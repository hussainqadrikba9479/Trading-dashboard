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

st.title("🦅 Master Trading Terminal (Price Action + VSA)")

# --- Mode Selector ---
st.markdown("### ⚙️ Select Trading Engine")
trading_mode = st.radio("", ["Intraday (H1 + M30)", "Swing Trading (D1 + H4)"], horizontal=True)

# --- Pakistan Time ---
pkt_timezone = timezone(timedelta(hours=5))
now_pkt = datetime.now(pkt_timezone)
st.info(f"🕒 **Last Updated:** {now_pkt.strftime('%I:%M:%S %p')} (PKT) | **Current Mode:** {trading_mode}")

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
    st.dataframe(cot_df.head(15), use_container_width=True, hide_index=True)
else:
    st.error(f"⚠️ COT File Load Error: {cot_df}")

def get_cot_net_change(inst, df):
    if not isinstance(df, pd.DataFrame) or df.empty: return 0
    search_term = inst if inst != 'GOLD' else 'Gold'
    try:
        match = df[df['Instrument'].astype(str).str.contains(search_term, case=False, na=False)]
        if not match.empty: return float(match['Net Change'].iloc[0])
    except: pass
    return 0

# --- HELPER FUNCTIONS FOR ADVANCED PRICE ACTION ---

def calculate_angle(price_diff, periods):
    # A simple proxy for angle/momentum. Higher absolute value = sharper angle.
    if periods == 0: return 0
    return price_diff / periods

def analyze_market_structure(df, lookback_period=10):
    """
    Analyzes swings to determine trend, ranges, and breakout angles.
    """
    # Find recent Local Highs and Lows
    df['Local_High'] = df['High'][(df['High'].shift(1) < df['High']) & (df['High'].shift(-1) < df['High'])]
    df['Local_Low'] = df['Low'][(df['Low'].shift(1) > df['Low']) & (df['Low'].shift(-1) > df['Low'])]
    
    recent_highs = df['Local_High'].dropna().tail(3).values
    recent_lows = df['Local_Low'].dropna().tail(3).values
    
    if len(recent_highs) < 3 or len(recent_lows) < 3:
        return "Insufficient Data", 0, "Neutral"

    # Evaluate Swings
    h1, h2, h3 = recent_highs[-3], recent_highs[-2], recent_highs[-1] # h3 is most recent
    l1, l2, l3 = recent_lows[-3], recent_lows[-2], recent_lows[-1]

    structure = "➖ Range"
    signal = "Neutral"
    angle = 0
    
    # 1. RANGE LOGIC (Equal Highs/Lows)
    # Check if highs and lows are roughly equal (within 0.1% tolerance)
    tolerance = h1 * 0.001 
    if (abs(h1-h2) < tolerance and abs(h2-h3) < tolerance) and (abs(l1-l2) < tolerance and abs(l2-l3) < tolerance):
        structure = "➖ Range (Valid - 3+ Touches)"
        # Check current price position for Range Entry
        current_price = df['Close'].iloc[-1]
        if current_price >= h3 * 0.999: # At Top
             signal = "🚨 Sell at Range Top (Wait for Upthrust)"
        elif current_price <= l3 * 1.001: # At Bottom
             signal = "🟢 Buy at Range Bottom (Wait for Spring)"
             
    # 2. UPTREND LOGIC (2 Higher Highs broken)
    elif h3 > h2 and h2 > h1 and l3 > l2 and l2 > l1:
        structure = "📈 Uptrend Confirmed"
        # Calculate Angle of the last break
        angle = calculate_angle(h3 - h2, 5) # Assuming roughly 5 periods between swings for proxy
        current_price = df['Close'].iloc[-1]
        
        if angle > (h1*0.0005): # Sharp Angle Threshold
            if current_price < h3 and current_price > l3: # In Pullback Phase
                 signal = "✅ Buy Pullback (Trend Continuation)"
        else:
            signal = "⚠️ Uptrend (Weak Angle - Caution)"

    # 3. DOWNTREND LOGIC (2 Lower Lows broken)
    elif h3 < h2 and h2 < h1 and l3 < l2 and l2 < l1:
        structure = "📉 Downtrend Confirmed"
        angle = calculate_angle(l2 - l3, 5)
        current_price = df['Close'].iloc[-1]
        
        if angle > (l1*0.0005):
            if current_price > l3 and current_price < h3: # In Pullback Phase
                 signal = "❌ Sell Pullback (Trend Continuation)"
        else:
            signal = "⚠️ Downtrend (Weak Angle - Caution)"
            
    # 4. BREAKOUT/PULLBACK SAFE ENTRY LOGIC
    # Range Breakout Up -> Pullback
    elif (h2 <= h1 + tolerance) and (h3 > h1): # Broke resistance
        structure = "🚀 Upward Breakout Phase"
        if df['Close'].iloc[-1] <= h1 * 1.002 and df['Close'].iloc[-1] >= h1 * 0.998: # Pulling back to broken resistance
             signal = "🟢 Safe Buy (Breakout Pullback)"
             
    # Range Breakdown Down -> Pullback
    elif (l2 >= l1 - tolerance) and (l3 < l1): # Broke support
        structure = "🩸 Downward Breakdown Phase"
        if df['Close'].iloc[-1] >= l1 * 0.998 and df['Close'].iloc[-1] <= l1 * 1.002: # Pulling back to broken support
             signal = "🚨 Safe Sell (Breakdown Pullback)"

    return structure, angle, signal

# --- 2. MARKET ANALYSIS ENGINE ---
futures_symbols = {
    'USD': 'DX-Y.NYB', 'GOLD': 'GC=F', 'EUR': '6E=F', 'GBP': '6B=F', 
    'JPY': '6J=F', 'AUD': '6A=F', 'CAD': '6C=F', 'CHF': '6S=F'
}

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

@st.cache_data(ttl=300)
def get_market_data(symbols_dict, mode):
    data_list = []
    for name, ticker in symbols_dict.items():
        try:
            if mode == "Intraday (H1 + M30)":
                df_htf = yf.download(ticker, period="2mo", interval="1h", progress=False)
                df_ltf = yf.download(ticker, period="1mo", interval="30m", progress=False)
                htf_label, ltf_label = "H1", "M30"
            else:
                df_htf = yf.download(ticker, period="6mo", interval="1d", progress=False)
                df_ltf = yf.download(ticker, period="1mo", interval="1h", progress=False)
                htf_label, ltf_label = "D1", "H4"
                
            if df_htf.empty or df_ltf.empty: continue
            if isinstance(df_htf.columns, pd.MultiIndex): df_htf.columns = df_htf.columns.droplevel(1)
            if isinstance(df_ltf.columns, pd.MultiIndex): df_ltf.columns = df_ltf.columns.droplevel(1)

            # Technicals
            close_htf = df_htf['Close'].iloc[-1]
            sma20_htf = df_htf['Close'].rolling(20).mean().iloc[-1]
            rsi_htf = calc_rsi(df_htf['Close']).iloc[-1]
            htf_trend = "UP" if close_htf > sma20_htf else "DOWN"

            close_ltf = df_ltf['Close'].iloc[-1]
            sma20_ltf = df_ltf['Close'].rolling(20).mean().iloc[-1]
            ltf_trend = "UP" if close_ltf > sma20_ltf else "DOWN"
            
            # --- GET PRICE ACTION STRUCTURE & SIGNAL ---
            pa_structure, pa_angle, pa_signal = analyze_market_structure(df_ltf.copy(), lookback_period=10)

            # Score Logic
            score = 5
            if htf_trend == "UP" and ltf_trend == "UP": score = 9
            elif htf_trend == "DOWN" and ltf_trend == "DOWN": score = 1
            elif htf_trend == "UP" and ltf_trend == "DOWN": score = 6
            elif htf_trend == "DOWN" and ltf_trend == "UP": score = 4
            if rsi_htf > 70: score -= 1 
            if rsi_htf < 30: score += 1 

            # --- VSA VOLUME CONFIRMATION ---
            vol = df_ltf['Volume'].iloc[-1]
            prev_vol = df_ltf['Volume'].iloc[-2]
            avg_vol = df_ltf['Volume'].rolling(20).mean().iloc[-1]
            
            vol_confirm = "No Volume Confirm"
            if "Breakout" in pa_structure or "Breakdown" in pa_structure:
                # Need high volume on break, low on pullback
                if vol < prev_vol and vol < avg_vol: vol_confirm = "✅ Pullback Vol Confirmed"
            elif "Pullback" in pa_signal:
                if vol < prev_vol: vol_confirm = "✅ No Supply/Demand Confirmed"
            elif "Range" in pa_signal:
                if vol > avg_vol * 1.2: vol_confirm = "🚨 Trap Vol (Spring/Upthrust)"

            data_list.append({
                'Instrument': name, 
                f'{ltf_label} Structure': pa_structure, 
                f'PA Signal': pa_signal,
                f'Volume Confirm': vol_confirm, 
                'Score': score
            })
        except: pass
    return pd.DataFrame(data_list)

# Tables UI
st.markdown("---")
st.subheader(f"🔍 Price Action Analysis Phase ({trading_mode})")
df_fx = get_market_data(futures_symbols, trading_mode)

def style_score(val):
    if val >= 8: return 'background-color: #2ecc71; color: black; font-weight: bold'
    if val <= 3: return 'background-color: #e74c3c; color: white; font-weight: bold'
    return ''

def style_structure(val):
    if 'Uptrend Confirmed' in str(val) or 'Safe Buy' in str(val) or 'Buy Pullback' in str(val) or '✅' in str(val): return 'color: #2ecc71; font-weight: bold'
    if 'Downtrend Confirmed' in str(val) or 'Safe Sell' in str(val) or 'Sell Pullback' in str(val) or '🚨' in str(val): return 'color: #e74c3c; font-weight: bold'
    return ''

st.dataframe(df_fx.style.map(style_score, subset=['Score'])
             .map(style_structure, subset=[c for c in df_fx.columns if 'Structure' in c][0])
             .map(style_structure, subset=['PA Signal', 'Volume Confirm']), 
             use_container_width=True, hide_index=True)

# --- 3. MASTER CONFLUENCE RECOMMENDATIONS SECTION ---
st.markdown("---")
st.subheader("🎯 Master Setups (Structure + Strength + COT + Volume)")
if not df_fx.empty:
    strong = df_fx[df_fx['Score'] >= 8]
    weak = df_fx[df_fx['Score'] <= 3]
    found = False
    
    for _, s in strong.iterrows():
        for _, w in weak.iterrows():
            c1, c2 = s['Instrument'], w['Instrument']
            
            s_signal, s_vol = str(s['PA Signal']), str(s['Volume Confirm'])
            w_signal, w_vol = str(w['PA Signal']), str(w['Volume Confirm'])
            
            # Rule 1: Master Confluence Check
            # We want C1 to be in a BUY setup, OR C2 to be in a SELL setup (with volume confirmation)
            setup_valid = False
            setup_desc = ""
            
            if ("Buy" in s_signal or "Spring" in s_signal) and "✅" in s_vol:
                setup_valid = True
                setup_desc = f"{c1} is providing a Buy Setup."
            elif ("Sell" in w_signal or "Upthrust" in w_signal) and "✅" in w_vol:
                setup_valid = True
                setup_desc = f"{c2} is providing a Sell Setup."
                
            # Avoid conflicting setups
            if "Sell" in s_signal or "Buy" in w_signal:
                continue

            # Rule 2: COT Data Lock
            c1_cot_bias = get_cot_net_change(c1, cot_df) 
            c2_cot_bias = get_cot_net_change(c2, cot_df) 
            
            if c1_cot_bias <= 0 or c2_cot_bias >= 0:
                continue 
            
            if setup_valid:
                order = ['GOLD', 'EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
                try:
                    if order.index(c1) < order.index(c2): pair, action = f"{c1}{c2}", "BUY"
                    else: pair, action = f"{c2}{c1}", "SELL"
                    
                    st.success(f"⚡ **{action} {pair}** | Institutional Master Confluence 🚀🚀🚀")
                    st.write(f"**Actionable Logic:** {setup_desc}")
                    st.write(f"**COT Alignment:** 📈 Institutions are Long {c1} (+{c1_cot_bias}) | 📉 Short {c2} ({c2_cot_bias})")
                    found = True
                except: pass
                
    if not found: 
        st.warning(f"Filhal {trading_mode} mode mein koi PERFECT MASTER trade nahi hai. Market structure ban'ne ka wait karein.")

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
