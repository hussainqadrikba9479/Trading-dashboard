import yfinance as yf
import pandas as pd
import streamlit as st
import google.generativeai as genai
import requests
import xml.etree.ElementTree as ET
import random
from datetime import datetime, timezone, timedelta

# --- 1. Dashboard Setup & Theme ---
st.set_page_config(page_title="Global Trading Terminal", layout="wide")
st.markdown("""
    <style>
    .main {background-color: transparent;}
    .news-card {border-left: 6px solid #e74c3c; background-color: #1e222d; color: #d1d4dc; padding: 12px; border-radius: 8px; margin-bottom: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);}
    .session-box {padding: 12px; border-radius: 8px; text-align: center; margin-bottom: 15px; transition: 0.3s;}
    .time-badge {background: rgba(255,255,255,0.1); color: #d1d4dc; padding: 4px 8px; border-radius: 4px; display: inline-block; margin-top: 5px;}
    .psych-box {background-color: #1e222d; padding: 20px; border-radius: 10px; border-left: 5px solid #f1c40f; margin-bottom: 20px;}
    .quote-text {font-style: italic; font-size: 1.2em; color: #f1c40f;}
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    ::-webkit-scrollbar {width: 6px; height: 6px;}
    ::-webkit-scrollbar-track {background: #0e1117;} 
    ::-webkit-scrollbar-thumb {background: #3498db; border-radius: 3px;}
    </style>
""", unsafe_allow_html=True)

# ==========================================
# --- SECURITY: LOGIN GATE ---
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br><div style='background-color: #1e222d; padding: 30px; border-radius: 10px; text-align: center;'>", unsafe_allow_html=True)
        st.subheader("🔒 Restricted Access")
        pwd = st.text_input("Enter Password:", type="password")
        if pwd:
            if pwd == st.secrets.get("TERMINAL_PASSWORD", "admin"):
                st.session_state.authenticated = True
                st.rerun()
            else: st.error("❌ Ghalat Password!")
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# =========================================================================
# --- BACKEND DATA FUNCTIONS (Global Scope) ---
# =========================================================================
@st.cache_data(ttl=3600)
def load_cot_data():
    try:
        df_cot = pd.read_excel("COT.xlsm", sheet_name="Main", engine='openpyxl', usecols="A,B,G,K,P", skiprows=2, header=None)
        df_cot.columns = ['Instrument', 'Net Change', 'Direction', 'COT Index', 'OI Change']
        return df_cot.dropna(subset=['Instrument'])
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
                    change = curr_oi - prev_oi
                    status = "Increasing 🟢" if change > 0 else "Decreasing 🔴"
                    oi_list.append({'Instrument': symbol, 'Current OI': int(curr_oi), 'Status': status})
        if not oi_list: return pd.DataFrame([{'Instrument': '⚠️ Error', 'Status': 'Excel format mismatch.'}])
        return pd.DataFrame(oi_list)
    except Exception as e: return pd.DataFrame([{'Instrument': '⚠️ Error', 'Status': str(e)}])

@st.cache_data(ttl=300)
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
            vol_confirm = "✅ Vol Confirmed" if vol > avg_vol else "No Volume Confirm"
            data_list.append({'Instrument': name, 'Structure': 'Uptrend' if close > sma else 'Downtrend', 'PA Signal': 'Buy Pullback' if score >= 6 else 'Sell Pullback' if score <= 4 else 'Neutral', 'Volume Confirm': vol_confirm, 'Score': score})
        except: pass
    return pd.DataFrame(data_list)

@st.cache_data(ttl=3600)
def get_currency_matrix():
    currencies = ['EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
    matrix_df = pd.DataFrame(index=currencies, columns=currencies + ['TOTAL'])
    tickers, pairs_map = [], {}
    for i in range(len(currencies)):
        for j in range(i+1, len(currencies)):
            pair = f"{currencies[i]}{currencies[j]}=X"
            tickers.append(pair)
            pairs_map[pair] = (currencies[i], currencies[j])
    try:
        df = yf.download(tickers, period="1mo", interval="1d", progress=False)
        closes = df['Close'] if isinstance(df.columns, pd.MultiIndex) else df
        scores = {c: 0 for c in currencies}
        for ticker in tickers:
            c1, c2 = pairs_map[ticker]
            try:
                pair_data = closes[ticker].dropna()
                curr, sma = pair_data.iloc[-1], pair_data.rolling(20).mean().iloc[-1]
                diff = (curr - sma) / sma
                if diff > 0.002: 
                    matrix_df.loc[c1, c2], matrix_df.loc[c2, c1] = '⬆', '⬇'
                    scores[c1] += 1; scores[c2] -= 1
                elif diff < -0.002:
                    matrix_df.loc[c1, c2], matrix_df.loc[c2, c1] = '⬇', '⬆'
                    scores[c1] -= 1; scores[c2] += 1
                else: matrix_df.loc[c1, c2], matrix_df.loc[c2, c1] = '↔', '↔'
            except: matrix_df.loc[c1, c2], matrix_df.loc[c2, c1] = '-', '-'
        for c in currencies:
            matrix_df.loc[c, c] = '' 
            matrix_df.loc[c, 'TOTAL'] = scores[c]
        return matrix_df.sort_values(by='TOTAL', ascending=False)
    except: return pd.DataFrame()

@st.cache_data(ttl=120)
def get_live_squawk():
    try:
        r = requests.get("https://www.forexlive.com/feed", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        root = ET.fromstring(r.content)
        return [{'title': i.find('title').text, 'link': i.find('link').text, 'time': i.find('pubDate').text} for i in root.findall('.//item')[:5]]
    except: return []

# --- Initialize Tabs ---
tab_terminal, tab_risk, tab_psych = st.tabs(["🦅 Trading Terminal", "💰 Risk Manager", "🧠 Mindset & Psychology"])

# =========================================================================
# --- TAB 1: TRADING TERMINAL ---
# =========================================================================
with tab_terminal:
    st.title("🦅 Master Trading Terminal")
    trading_mode = st.radio("⚙️ Select Trading Engine", ["Intraday (H1 + M30)", "Swing Trading (D1 + H4)"], index=1, horizontal=True)

    pkt_timezone = timezone(timedelta(hours=5))
    now_pkt = datetime.now(pkt_timezone)
    st.info(f"🕒 **Live Clock:** {now_pkt.strftime('%I:%M:%S %p')} (PKT) | **Current Mode:** {trading_mode}")

    def get_session_status(now, open_h, close_h):
        open_time = now.replace(hour=open_h, minute=0, second=0, microsecond=0)
        close_time = now.replace(hour=close_h, minute=0, second=0, microsecond=0)
        is_weekend = now.weekday() >= 5
        if open_h > close_h:
            if now.hour >= open_h or now.hour < close_h:
                is_active = True
                if now.hour >= open_h: close_time += timedelta(days=1)
            else: is_active = False
        else:
            is_active = open_h <= now.hour < close_h
            if not is_active and now.hour >= close_h: open_time += timedelta(days=1)
        if is_weekend: return False, "Market Closed", "⏸️ Weekend"
        if is_active:
            diff = close_time - now
            rem = f"⏳ Closes in {diff.seconds // 3600}h {(diff.seconds // 60) % 60}m"
        else:
            diff = open_time - now
            rem = f"⏳ Opens in {diff.seconds // 3600}h {(diff.seconds // 60) % 60}m"
        return is_active, f"{open_time.strftime('%I %p')} - {close_time.strftime('%I %p')}", rem

    def get_session_html(name, is_active, color, timing_str, rem_str):
        bg_color = color if is_active else "#2b3040"
        status = "🟢 ACTIVE" if is_active else "⚪ CLOSED"
        return f"""<div class='session-box' style='background-color: {bg_color}; color: white;'>
            <div style='font-size: 1.1em; font-weight: bold;'>{name}</div>
            <div style='font-size: 0.85em; opacity: 0.9;'>{timing_str}</div>
            <div style='font-size: 0.9em; font-weight: 500; margin-top:5px;'>{status}</div>
            <div class='time-badge'>{rem_str}</div></div>"""

    syd_a, syd_t, syd_r = get_session_status(now_pkt, 3, 12)
    tok_a, tok_t, tok_r = get_session_status(now_pkt, 5, 14)
    lon_a, lon_t, lon_r = get_session_status(now_pkt, 12, 21)
    ny_a, ny_t, ny_r = get_session_status(now_pkt, 17, 2)

    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(get_session_html("🇦🇺 Sydney", syd_a, "#3498db", syd_t, syd_r), unsafe_allow_html=True)
    with c2: st.markdown(get_session_html("🇯🇵 Tokyo", tok_a, "#9b59b6", tok_t, tok_r), unsafe_allow_html=True)
    with c3: st.markdown(get_session_html("🇬🇧 London", lon_a, "#e67e22", lon_t, lon_r), unsafe_allow_html=True)
    with c4: st.markdown(get_session_html("🇺🇸 New York", ny_a, "#e74c3c", ny_t, ny_r), unsafe_allow_html=True)

    # Load Data
    cot_df = load_cot_data()
    oi_df = load_daily_oi()
    df_fx = get_market_data(trading_mode)
    matrix_df = get_currency_matrix()
    live_news = get_live_squawk()

    st.markdown("---")
    st.subheader("🎯 Active Trade Setups (PA + VSA + COT + Daily OI Locked)")

    strong = df_fx[df_fx['Score'] >= 6]
    weak = df_fx[df_fx['Score'] <= 4]
    found = False

    if not strong.empty and not weak.empty:
        for _, s in strong.iterrows():
            for _, w in weak.iterrows():
                c1, c2 = s['Instrument'], w['Instrument']
                cot_align = True
                if not cot_df.empty:
                    s_sentiment = cot_df[cot_df['Instrument'].str.contains(c1, case=False)]['Direction'].values
                    if len(s_sentiment) > 0 and "Bearish" in s_sentiment[0]: cot_align = False
                oi_align = True
                if not oi_df.empty and 'Status' in oi_df.columns:
                    s_oi = oi_df[oi_df['Instrument'] == c1]['Status'].values
                    if len(s_oi) > 0 and "Decreasing" in s_oi[0]: oi_align = False
                if cot_align and oi_align and ("✅" in s['Volume Confirm'] or "✅" in w['Volume Confirm']):
                    order = ['GOLD', 'EUR', 'GBP', 'AUD', 'NZD', 'USD', 'CAD', 'CHF', 'JPY']
                    try:
                        if order.index(c1) < order.index(c2): pair, action = f"{c1}{c2}", "BUY"
                        else: pair, action = f"{c2}{c1}", "SELL"
                        st.success(f"🔥 **{action} {pair}** | Strength: {s['Score']} vs {w['Score']} | Smart Money (COT+OI) Aligned 🚀")
                        found = True
                    except: pass
    if not found: st.info("Filhal criteria par koi trade setup nahi mila. Searching for institutional alignments...")

    # --- AI CO-PILOT ---
    st.markdown("---")
    st.subheader("🧠 Gemini AI Co-Pilot (Live Chat & Analysis)")

    if "chat_session" not in st.session_state: st.session_state.chat_session = None
    if "chat_messages" not in st.session_state: st.session_state.chat_messages = []

    try: api_key = st.secrets["GEMINI_API_KEY"]
except: api_key = None; st.error("⚠️ API Key missing in Secrets!")

    if api_key:
        genai.configure(api_key=api_key)
        if st.button("🚀 Generate Institutional Report"):
            with st.spinner("Gemini is processing your PA, Volume, COT, OI and News data..."):
                try:
                    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                    target_model = available_models[0] if available_models else 'models/gemini-pro'
                    model = genai.GenerativeModel(target_model)
                    st.session_state.chat_session = model.start_chat(history=[])
                    st.session_state.chat_messages = [] 
                    pa_data = df_fx.to_string() if not df_fx.empty else "No PA data."
                    cot_data = cot_df.to_string() if not cot_df.empty else "No COT data."
                    oi_data = oi_df.to_string() if not oi_df.empty else "No Daily OI data."
                    matrix_data = matrix_df.to_string() if not matrix_df.empty else "No Matrix data."
                    news_summary = "\n".join([n['title'] for n in live_news]) if live_news else "No major news."
                    prompt = f"""
                    Aap ek expert quantitative forex analyst hain. Niche diye gaye data ka jaiza lein:
                    1. PRICE ACTION & VOLUME: {pa_data}
                    2. CURRENCY STRENGTH MATRIX: {matrix_data}
                    3. INSTITUTIONAL COT DATA: {cot_data}
                    4. DAILY OPEN INTEREST (OI): {oi_data}
                    5. LATEST BREAKING NEWS: {news_summary}
                    Bataiye:
                    1. Market ka overall mood kya hai?
                    2. Kin pairs par PA, Volume, COT, aur OI align ho rahe hain?
                    3. Risks aur trap warnings dein.
                    Jawab Roman Urdu mein point-by-point dein.
                    """
                    response = st.session_state.chat_session.send_message(prompt)
                    st.session_state.chat_messages.append({"role": "assistant", "content": response.text})
                    st.rerun()
                except Exception as e: st.error(f"AI Error: {e}")
                    
        if st.session_state.chat_messages:
            for msg in st.session_state.chat_messages:
                if msg["role"] == "assistant":
                    st.markdown(f"<div style='background-color: #1e222d; padding: 20px; border-radius: 10px; border-left: 5px solid #3498db; margin-bottom: 10px;'><b>🤖 AI Co-Pilot:</b><br>{msg['content']}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='background-color: #2b3040; padding: 15px; border-radius: 10px; border-left: 5px solid #e74c3c; margin-bottom: 10px; text-align: right;'><b>👤 Aap:</b><br>{msg['content']}</div>", unsafe_allow_html=True)
            
        if st.session_state.chat_session:
            user_q = st.chat_input("AI se mazeed sawal puchein...")
            if user_q:
                st.session_state.chat_messages.append({"role": "user", "content": user_q})
                with st.spinner("AI Soch raha hai..."):
                    try:
                        res = st.session_state.chat_session.send_message(f"Forex expert ki hasiyat se Roman Urdu mein is sawal ka jawab dein: {user_q}")
                        st.session_state.chat_messages.append({"role": "assistant", "content": res.text})
                        st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

    # --- MATRIX ---
    st.markdown("---")
    st.subheader("🧮 Weekly Currency Strength Matrix")
    def style_matrix(val):
        if val == '⬆': return 'color: #2ecc71; font-weight: bold; text-align: center; font-size: 22px;'
        if val == '⬇': return 'color: #e74c3c; font-weight: bold; text-align: center; font-size: 22px;'
        if val == '↔': return 'color: #f39c12; font-weight: bold; text-align: center; font-size: 22px;'
        if val == '': return 'background-color: #1e222d;' 
        if isinstance(val, (int, float)):
            if val > 0: return 'background-color: rgba(46, 204, 113, 0.2); color: #2ecc71; font-weight: bold; text-align: center; font-size: 18px;'
            if val < 0: return 'background-color: rgba(231, 76, 60, 0.2); color: #e74c3c; font-weight: bold; text-align: center; font-size: 18px;'
            return 'color: gray; font-weight: bold; text-align: center; font-size: 18px;'
        return ''

    if not matrix_df.empty:
        st.dataframe(matrix_df.style.map(style_matrix), use_container_width=True)
    else: st.write("Calculating Weekly Matrix from 28 cross pairs...")

    # --- BOTTOM TABLES ---
    st.markdown("---")
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("🔍 Price Action Analysis")
        def style_score(val):
            if val >= 6: return 'background-color: rgba(46, 204, 113, 0.2); color: #2ecc71; font-weight: bold'
            elif val <= 4: return 'background-color: rgba(231, 76, 60, 0.2); color: #e74c3c; font-weight: bold'
            return ''
        def style_structure(val):
            if 'Uptrend' in str(val) or 'Buy' in str(val) or '✅' in str(val): return 'color: #2ecc71; font-weight: bold'
            if 'Downtrend' in str(val) or 'Sell' in str(val) or '❌' in str(val) or '🚨' in str(val): return 'color: #e74c3c; font-weight: bold'
            return ''
        if not df_fx.empty:
            styled_df = df_fx.style.map(style_score, subset=['Score']).map(style_structure, subset=['Structure', 'PA Signal', 'Volume Confirm'])
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
        else: st.write("Fetching technicals...")

    with col_r:
        st.subheader("📊 Smart Money (COT & Daily OI)")
        st.markdown("**1. Weekly COT Sentiment:**")
        def style_cot(val):
            try:
                if float(val) > 0: return 'background-color: rgba(46, 204, 113, 0.1); color: #2ecc71; font-weight: bold'
                elif float(val) < 0: return 'background-color: rgba(231, 76, 60, 0.1); color: #e74c3c; font-weight: bold'
            except: pass
            return ''
        if not cot_df.empty:
            styled_cot = cot_df.head(10).style.map(style_cot, subset=['Net Change'])
            st.dataframe(styled_cot, use_container_width=True, hide_index=True)
            
        st.markdown("**2. Daily Futures Open Interest:**")
        def style_oi(val):
            if 'Increasing' in str(val): return 'background-color: rgba(46, 204, 113, 0.1); color: #2ecc71; font-weight: bold'
            if 'Decreasing' in str(val): return 'background-color: rgba(231, 76, 60, 0.1); color: #e74c3c; font-weight: bold'
            return ''
        if not oi_df.empty and 'Status' in oi_df.columns:
            styled_oi = oi_df.style.map(style_oi, subset=['Status'])
            st.dataframe(styled_oi, use_container_width=True, hide_index=True)
        else: st.write("Daily_OI.xlsm not found or loading...")

    # --- NEWS & CALENDAR ---
    st.markdown("---")
    st.subheader("📰 Live Breaking News (Forex Squawk)")
    if live_news:
        for n in live_news: st.markdown(f"<div class='news-card'><b>⚡ {n['title']}</b><br><small>{n['time']}</small></div>", unsafe_allow_html=True)
    else: st.warning("Squawk feed currently unavailable.")

    st.markdown("---")
    st.subheader("📅 High Impact News Calendar")
    try:
        cal_data = requests.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json").json()
        news_by_date = {}
        for e in cal_data:
            if e.get('impact') == 'High':
                dt = datetime.fromisoformat(e['date']).astimezone(pkt_timezone)
                d_str = dt.strftime("%A, %d %b %Y")
                if d_str not in news_by_date: news_by_date[d_str] = []
                news_by_date[d_str].append({'time': dt.strftime('%I:%M %p'), 'curr': e['country'], 'title': e['title'], 'past': dt < now_pkt})
        for day, events in news_by_date.items():
            with st.expander(f"📅 {day}", expanded=True):
                for ev in events:
                    c1, c2, c3 = st.columns([1, 1, 3])
                    if ev['past']:
                        c1.markdown(f"~~{ev['time']}~~")
                        c2.markdown(f"~~{ev['curr']}~~")
                        c3.markdown(f"⚪ *{ev['title']} (Passed)*")
                    else:
                        c1.markdown(f"**{ev['time']}**")
                        c2.markdown(f"**{ev['curr']}**")
                        c3.markdown(f"🔴 **{ev['title']}**")
    except: st.write("Calendar loading...")

# =========================================================================
# --- TAB 2: RISK MANAGER (MONEY MANAGEMENT) ---
# =========================================================================
with tab_risk:
    st.header("💰 Money Management & Lot Size Calculator")
    col_acc, col_calc = st.columns([2, 1])
    with col_acc:
        st.subheader("📊 Multi-Account Tracker")
        st.write("Apne accounts ka aaj ka balance yahan set karein:")
        acc_data = []
        for i in range(1, 6):
            c1, c2, c3 = st.columns([2, 2, 2])
            name = c1.text_input(f"Account {i} Name", f"Prop Firm {i}", key=f"acc_name_{i}")
            bal = c2.number_input(f"Start Balance ($)", value=50000.0, step=100.0, key=f"acc_bal_{i}")
            risk_p = c3.slider(f"Risk %", 0.1, 5.0, 0.5, key=f"acc_risk_{i}")
            acc_data.append({"Name": name, "Balance": bal, "Risk %": risk_p, "Risk Amount": (bal * risk_p / 100)})
        st.table(pd.DataFrame(acc_data))

    with col_calc:
        st.subheader("🧮 Lot Size Calculator")
        selected_acc = st.selectbox("Select Account", [a["Name"] for a in acc_data])
        sl_pips = st.number_input("Stop Loss (Pips)", min_value=1.0, value=20.0)
        pair_type = st.selectbox("Pair Type", ["Standard (1 Lot = $10/pip)", "Gold (1 Lot = $10/pip)", "Custom"])
        target_acc = next(item for item in acc_data if item["Name"] == selected_acc)
        risk_usd = target_acc["Risk Amount"]
        calculated_lots = risk_usd / (sl_pips * 10)
        st.markdown(f"""
        <div style='background-color: #1e222d; padding: 20px; border-radius: 10px; border-left: 5px solid #2ecc71;'>
            <h4 style='margin:0;'>Suggested Lot Size:</h4>
            <h1 style='color: #2ecc71; margin:0;'>{calculated_lots:.2f}</h1>
            <small>Risking: ${risk_usd:.2f} on this trade</small>
        </div>
        """, unsafe_allow_html=True)

# =========================================================================
# --- TAB 3: MINDSET & PSYCHOLOGY ---
# =========================================================================
with tab_psych:
    st.header("🧠 Trading Psychology & Discipline")
    quotes = [
        "Trading is not about being right, it's about being disciplined.",
        "A loss is just a cost of doing business. Don't take it personally.",
        "The market doesn't care about your feelings. Stick to the plan.",
        "Institutional traders don't gamble; they manage risk. Be like them.",
        "Your edge lies in your patience, not in how many trades you take.",
        "Stop looking for 'sure things' and start looking for 'high probabilities'."
    ]
    st.markdown(f"""
    <div class='psych-box'>
        <p style='margin:0; font-weight: bold; color: #aaa;'>Quote of the Day:</p>
        <p class='quote-text'>"{random.choice(quotes)}"</p>
    </div>
    """, unsafe_allow_html=True)

    col_pre, col_post = st.columns(2)
    with col_pre:
        st.subheader("✅ Pre-Trade Checklist")
        st.checkbox("Kya PA + VSA + COT + OI charon align hain?")
        st.checkbox("Kya yeh revenge trade toh nahi?")
        st.checkbox("Kya lot size calculator se confirm kar li hai?")
        st.checkbox("Kya main market ke mood ko samajh chuka hoon?")
        st.checkbox("Kya Stop Loss aur Take Profit set hai?")
    with col_post:
        st.subheader("📝 Post-Trade Journal")
        st.checkbox("Kya main ne apna plan follow kiya?")
        st.checkbox("Kya emotions (Fear/Greed) ne tang kiya?")
        st.text_area("Lesson learned from this trade:")
        if st.button("Save Entry"): st.success("Entry saved for your personal growth!")

    st.markdown("---")
    st.info("💡 **Hussain Bhai**, yaad rakhein: Analysis aap ko entry deta hai, lekin Psychology aap ko profitable rakhti hai.")
