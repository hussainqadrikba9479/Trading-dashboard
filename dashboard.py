import streamlit as st
import pandas as pd
import yfinance as yf
import google.generativeai as genai
from datetime import datetime, timezone, timedelta

# --- PAGE CONFIG ---
st.set_page_config(page_title="Hussain Algo Terminal", page_icon="📈", layout="wide")

# --- INITIALIZE AI ---
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    ai_model = genai.GenerativeModel(available_models[0])
except Exception as e:
    ai_model = None

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

# --- UI TABS ---
tab_terminal, tab_risk, tab_psych = st.tabs(["📈 Trading Terminal", "💰 Risk Manager", "🧠 Mindset & Psychology"])

with tab_terminal:
    st.title("📈 Master Trading AI Verified Terminal")
    trading_mode = st.radio("⚙️ Select Trading Engine", ["Intraday (H1 + M30)", "Swing Trading (D1 + H4)"], index=1, horizontal=True)
    
    # 1. MARKET TECHNICALS
    st.subheader("📊 Market Technicals & Volume")
    df_fx = get_market_data(trading_mode)
    st.dataframe(df_fx, use_container_width=True)
    
    # 2. INSTITUTIONAL DATA (COT & OI)
    st.subheader("🏦 Institutional Data (COT & Daily OI)")
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Smart Money COT Data**")
        cot_df = load_cot_data()
        if not cot_df.empty: st.dataframe(cot_df, use_container_width=True)
        else: st.warning("COT Data file read nahi ho saki.")
        
    with col2:
        st.write("**Daily Open Interest (OI)**")
        oi_df = load_daily_oi()
        if not oi_df.empty: st.dataframe(oi_df, use_container_width=True)
        else: st.warning("Daily OI file read nahi ho saki.")

    # 3. ACTIVE SETUPS
    st.subheader("🔥 Active Setups (Volume Confirmed)")
    strong = df_fx[df_fx['Score'] >= 6]
    weak = df_fx[df_fx['Score'] <= 4]
    found_setup = False
    
    if not strong.empty and not weak.empty:
        for _, s in strong.iterrows():
            for _, w in weak.iterrows():
                if "✅" in s['Volume Confirm'] or "✅" in w['Volume Confirm']:
                    st.success(f"**Setup Detected:** Strong {s['Instrument']} vs Weak {w['Instrument']} | Volume Confirmed ✅")
                    found_setup = True
    
    if not found_setup:
        st.info("💤 No active setups matching volume confirmation criteria right now.")

    # 4. AI CHAT
    st.divider()
    st.subheader("💬 Gemini AI Chat (Manual Queries)")
    user_query = st.text_input("Agar market ke bare mein confusion hai toh AI se puchein...")
    if user_query:
        if ai_model:
            st.info(ai_model.generate_content(user_query).text)
        else:
            st.error("⚠️ AI is currently offline. API Key check karein.")

with tab_risk:
    st.title("💰 Risk Manager")
    st.write("Money management tools and lot size calculator will appear here.")

with tab_psych:
    st.title("🧠 Mindset & Psychology")
    st.write("Discipline, patience, and consistency make a profitable trader.")
