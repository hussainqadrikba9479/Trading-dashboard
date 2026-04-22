import yfinance as yf
import pandas as pd
import streamlit as st
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

st.title("🦅 Global Trading Terminal (VSA + Gold Edition)")

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

# --- 2. MARKET ANALYSIS ENGINE ---
# Gold (GC=F) added to the symbols list
futures_symbols = {
    'USD': 'DX-Y.NYB', 'EUR': '6E=F', 'GBP': '6B=F', 
    'JPY': '6J=F', 'AUD': '6A=F', 'CAD': '6C=F', 
    'CHF': '6S=F', 'GOLD': 'GC=F'
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
                df_htf = yf.download(ticker, period="1mo", interval="1h", progress=False)
                df_ltf = yf.download(ticker, period="1mo", interval="30m", progress=False)
                htf_label, ltf_label = "H1", "M30"
            else:
                df_htf = yf.download(ticker, period="2mo", interval="1d", progress=False)
                df_ltf = yf.download(ticker, period="5d", interval="1h", progress=False)
                htf_label, ltf_label = "D1", "H4"
                
            if df_htf.empty or df_ltf.empty: continue
            if isinstance(df_htf.columns, pd.MultiIndex): df_htf.columns = df_htf.columns.droplevel(1)
            if isinstance(df_ltf.columns, pd.MultiIndex): df_ltf.columns = df_ltf.columns.droplevel(1)

            close_htf = df_htf['Close'].iloc[-1]
            sma20_htf = df_htf['Close'].rolling(20).mean().iloc[-1]
            rsi_htf = calc_rsi(df_htf['Close']).iloc[-1]
            htf_trend = "UP" if close_htf > sma20_htf else "DOWN"

            close_ltf = df_ltf['Close'].iloc[-1]
            prev_close_ltf = df_ltf['Close'].iloc[-2]
            sma20_ltf = df_ltf['Close'].rolling(20).mean().iloc[-1]
            ltf_trend = "UP" if close_ltf > sma20_ltf else "DOWN"
            
            score = 5
            if htf_trend == "UP" and ltf_trend == "UP": score = 9
            elif htf_trend == "DOWN" and ltf_trend == "DOWN": score = 1
            elif htf_trend == "UP" and ltf_trend == "DOWN": score = 6
            elif htf_trend == "DOWN" and ltf_trend == "UP": score = 4
            
            if rsi_htf > 70: score -= 1 
            if rsi_htf < 30: score += 1 

            high, low, vol = df_ltf['High'].iloc[-1], df_ltf['Low'].iloc[-1], df_ltf['Volume'].iloc[-1]
            prev_vol, prev_prev_vol = df_ltf['Volume'].iloc[-2], df_ltf['Volume'].iloc[-3]
            avg_vol = df_ltf['Volume'].rolling(20).mean().iloc[-1]
            spread = high - low
            avg_spread = (df_ltf['High'] - df_ltf['Low']).rolling(20).mean().iloc[-1]
            close_pos = (close_ltf - low) / spread if spread > 0 else 0.5
            
            vsa_signal = "Neutral"
            if (close_ltf > prev_close_ltf) and (spread > avg_spread) and (close_pos < 0.3) and (vol > avg_vol * 1.2):
                vsa_signal = "🚨 Upthrust (SOW)"
            elif (close_ltf < prev_close_ltf) and (spread > avg_spread) and (close_pos > 0.7) and (vol > avg_vol * 1.2):
                vsa_signal = "🟢 Shakeout (SOS)"
            elif (close_ltf > prev_close_ltf) and (spread < avg_spread) and (vol < prev_vol) and (vol < prev_prev_vol):
                vsa_signal = "📉 No Demand"
            elif (close_ltf < prev_close_ltf) and (spread < avg_spread) and (vol < prev_vol) and (vol < prev_prev_vol):
                vsa_signal = "📈 No Supply"

            data_list.append({
                'Instrument': name, 
                f'{htf_label} Trend': htf_trend, 
                f'{ltf_label} Trend': ltf_trend, 
                f'RSI ({htf_label})': round(rsi_htf, 2), 
                f'{ltf_label} VSA': vsa_signal, 
                'Score': score
            })
        except: pass
    return pd.DataFrame(data_list)

# Tables UI
st.markdown("---")
st.subheader(f"🔍 Analysis Phase ({trading_mode})")
df_fx = get_market_data(futures_symbols, trading_mode)

def style_score(val):
    if val >= 8: return 'background-color: #2ecc71; color: black; font-weight: bold'
    if val <= 3: return 'background-color: #e74c3c; color: white; font-weight: bold'
    return ''

st.dataframe(df_fx.style.map(style_score, subset=['Score']), use_container_width=True, hide_index=True)

# --- 3. RECOMMENDATIONS SECTION ---
st.markdown("---")
st.subheader("🎯 Refined Trade Setups (Score + Volume Locked)")
if not df_fx.empty:
    strong = df_fx[df_fx['Score'] >= 8]
    weak = df_fx[df_fx['Score'] <= 3]
    found = False
    
    vsa_col = 'M30 VSA' if trading_mode == "Intraday (H1 + M30)" else 'H4 VSA'
    
    for _, s in strong.iterrows():
        for _, w in weak.iterrows():
            c1, c2 = s['Instrument'], w['Instrument']
            s_vsa, w_vsa = str(s[vsa_col]), str(w[vsa_col])
            
            if "SOW" in s_vsa or "Demand" in s_vsa: continue 
            if "SOS" in w_vsa or "Supply" in w_vsa: continue 
            
            vsa_confirmed = False
            if "SOS" in s_vsa or "Supply" in s_vsa: vsa_confirmed = True
            if "SOW" in w_vsa or "Demand" in w_vsa: vsa_confirmed = True
            
            if vsa_confirmed:
                # Pair logic with Gold
                if c1 == 'GOLD' or c2 == 'GOLD':
                    pair = "GOLD/USD" if (c1 == 'GOLD' or c2 == 'USD') else f"{c1}/{c2}"
                    action = "BUY" if c1 == 'GOLD' else "SELL"
                else:
                    order = ['EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
                    try:
                        if order.index(c1) < order.index(c2): pair, action = f"{c1}{c2}", "BUY"
                        else: pair, action = f"{c2}{c1}", "SELL"
                    except: pair, action = f"{c1}{c2}", "TRADE"

                st.success(f"⚡ **{action} {pair}** | High Probability Setup")
                st.write(f"**Footprint:** {c1} ({s_vsa}) vs {c2} ({w_vsa})")
                found = True
                
    if not found: st.warning(f"Filhal koi trade setup nahi mila. Market observe karein.")

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
