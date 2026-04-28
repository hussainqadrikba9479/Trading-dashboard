import streamlit as st
import pandas as pd
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timezone, timedelta

# --- PAGE CONFIG ---
st.set_page_config(page_title="Hussain Algo Terminal", page_icon="📈", layout="wide")

# --- DATA FUNCTIONS ---
@st.cache_data(ttl=3600)
def load_cot_data():
    try:
        df = pd.read_excel("COT.xlsm", sheet_name="Main", engine='openpyxl', usecols="A,B,G,K,P", skiprows=2, header=None)
        df.columns = ['Instrument', 'Net Change', 'Direction', 'COT Index', 'OI Change']
        return df.dropna(subset=['Instrument'])
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
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
                    status = "Increasing 🟢" if (curr_oi - prev_oi) > 0 else "Decreasing 🔴"
                    oi_list.append({'Instrument': symbol, 'Current OI': int(curr_oi), 'Status': status})
        return pd.DataFrame(oi_list)
    except: return pd.DataFrame()

@st.cache_data(ttl=1800)
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
            data_list.append({'Instrument': name, 'Score': score, 'Volume Confirm': "✅" if vol > avg_vol else "❌"})
        except: pass
    return pd.DataFrame(data_list)

# --- INITIALIZE AI ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    ai_model = genai.GenerativeModel(available_models[0])
except Exception as e:
    st.error(f"AI Error: {e}")
    ai_model = None

# --- UI TABS ---
tab_terminal, tab_risk, tab_psych = st.tabs(["📈 Trading Terminal", "💰 Risk Manager", "🧠 Mindset & Psychology"])

with tab_terminal:
    st.title("📈 Master Trading AI Verified Terminal")
    trading_mode = st.radio("⚙️ Select Trading Engine", ["Intraday (H1 + M30)", "Swing Trading (D1 + H4)"], index=1, horizontal=True)
    
    st.subheader("📊 Market Technicals & Volume")
    df_fx = get_market_data(trading_mode)
    st.dataframe(df_fx, use_container_width=True)
    
    st.subheader("💬 Gemini AI Chat (Manual Queries)")
    user_query = st.text_input("Agar market ke bare mein confusion hai toh AI se puchein...")
    if user_query and ai_model:
        st.info(ai_model.generate_content(user_query).text)

with tab_risk:
    st.title("💰 Risk Manager")
    st.write("Lot size calculator will be here.")

with tab_psych:
    st.title("🧠 Mindset & Psychology")
    st.write("Discipline is the key to success.")
