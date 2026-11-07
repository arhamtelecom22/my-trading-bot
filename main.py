import os
import requests
import time
import pandas as pd
from flask import Flask
from threading import Thread
import datetime
import json
import concurrent.futures

# ================= TOKEN RENDER SE AAYEGA =================
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = "762295473"
# ============================================================

app = Flask('')
active_trades = {}
price_alerts = {}
last_signal_time = {}
watchlist = set()
SCAN_TIMEFRAME = "15m" 
MANUAL_SCAN_ACTIVE = False

def fmt(p):
    try:
        p = float(p)
        if p >= 1000: return f"{p:.2f}"
        if p >= 10: return f"{p:.3f}"
        if p >= 1: return f"{p:.4f}"
        if p >= 0.01: return f"{p:.5f}"
        return f"{p:.6f}"
    except: return str(p)

# ---------------- PERMANENT MEMORY ----------------
def load_active_trades():
    global active_trades
    try:
        if os.path.exists("active_trades.json"):
            with open("active_trades.json", "r") as f: active_trades = json.load(f)
    except: pass

def save_active_trades():
    try:
        with open("active_trades.json", "w") as f: json.dump(active_trades, f)
    except: pass

def save_to_journal(trade_data):
    try:
        journal = []
        if os.path.exists("journal.json"):
            with open("journal.json", "r") as f: journal = json.load(f)
        journal.append(trade_data)
        with open("journal.json", "w") as f: json.dump(journal, f)
    except: pass

def get_journal():
    try:
        if os.path.exists("journal.json"):
            with open("journal.json", "r") as f: return json.load(f)
    except: pass
    return []

# ---------------- CHART GENERATOR ----------------
def generate_chart_image(df, symbol, signal, entry, sl, tp1, tp2, tp3):
    try:
        df_chart = df.tail(30).copy()
        data = []
        labels = []
        
        for i, row in enumerate(df_chart.itertuples()):
            if pd.isna(row.open) or pd.isna(row.high) or pd.isna(row.low) or pd.isna(row.close):
                continue
            data.append({"x": str(i), "o": float(row.open), "h": float(row.high), "l": float(row.low), "c": float(row.close)})
            labels.append(str(i))
        
        if len(data) == 0: return None
        max_x = len(data) - 1

        annotations = {
            "entryLine": {"type": "line", "yMin": entry, "yMax": entry, "borderColor": "#4a9eff", "borderWidth": 3, "borderDash": [0, 0]}
        }

        if signal == "BUY":
            annotations['profitBox'] = {"type": "box", "yMin": entry, "yMax": tp1, "backgroundColor": "rgba(0, 200, 100, 0.05)", "borderColor": "rgba(0, 200, 100, 0.4)", "xMin": 0, "xMax": max_x}
            annotations['lossBox'] = {"type": "box", "yMin": sl, "yMax": entry, "backgroundColor": "rgba(255, 60, 60, 0.05)", "borderColor": "rgba(255, 60, 60, 0.4)", "xMin": 0, "xMax": max_x}
        elif signal == "SELL":
            annotations['profitBox'] = {"type": "box", "yMin": tp1, "yMax": entry, "backgroundColor": "rgba(0, 200, 100, 0.05)", "borderColor": "rgba(0, 200, 100, 0.4)", "xMin": 0, "xMax": max_x}
            annotations['lossBox'] = {"type": "box", "yMin": entry, "yMax": sl, "backgroundColor": "rgba(255, 60, 60, 0.05)", "borderColor": "rgba(255, 60, 60, 0.4)", "xMin": 0, "xMax": max_x}

        chart_config = {
            "type": "candlestick",
            "data": {"labels": labels, "datasets": [{"label": symbol, "data": data, "color": {"up": "#00c864", "down": "#ff3c3c", "unchanged": "#999999"}}]},
            "options": {
                "scales": {"x": {"type": "category", "display": False}, "y": {"position": "right", "grid": {"color": "#2a2e39"}, "ticks": {"color": "#fff"}}},
                "plugins": {"legend": {"display": False}, "annotation": {"annotations": annotations}}
            }
        }
        
        payload = {"chart": chart_config, "width": 800, "height": 450, "backgroundColor": "#131722", "version": "3"}
        res = requests.post("https://quickchart.io/chart", json=payload, timeout=10)
        if res.status_code == 200: return res.content
    except Exception as e:
        print("Chart Error:", e)
    return None

# ---------------- WEB DASHBOARD ----------------
@app.route('/')
def home():
    html = f"""
    <html><head><title>cripto_adda V43</title><meta http-equiv="refresh" content="30">
    <style>body{{background-color:#12161e;color:#e0e0e0;font-family:sans-serif;padding:20px;}}.container{{max-width:900px;margin:auto;}}.card{{background-color:#1a1e29;padding:15px;border-radius:8px;margin-bottom:15px;border:1px solid #2a2e39;}}.buy{{border-left:5px solid #00c864;}}.sell{{border-left:5px solid #ff3c3c;}}table{{width:100%;border-collapse:collapse;margin-top:10px;}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #2a2e39;}}</style></head>
    <body><div class="container"><h1>🤖 cripto_adda V43</h1>
    <p>Status: Running 24/7 | TF: {SCAN_TIMEFRAME} | Watchlist: {", ".join(watchlist) if watchlist else "All Coins"}</p><h2>📈 Active Trades</h2>
    """
    if not active_trades: html += "<div class='card'>No active trades. Scanning...</div>"
    else:
        for sym, t in active_trades.items():
            clean = sym.replace("B-", "").replace("I-", "").replace("_", "")
            cls = "buy" if t['type'] == "BUY" else "sell"
            html += f"<div class='card {cls}'><h3>{clean} ({t['type']})</h3><table><tr><th>Entry</th><th>SL</th><th>TP1</th><th>TP2</th><th>TP3</th></tr><tr><td>{fmt(t['entry'])}</td><td>{fmt(t['sl'])}</td><td>{fmt(t['tp1'])}</td><td>{fmt(t['tp2'])}</td><td>{fmt(t['tp3'])}</td></tr></table><p style='color:#888;font-size:12px;'>Status: {t['status']}</p></div>"
    html += "</div></body></html>"
    return html

def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

def send_telegram(text, reply_markup=None):
    if not TG_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup: payload["reply_markup"] = reply_markup
    try: 
        r = requests.post(url, json=payload)
        if r.status_code != 200:
            print("TG Error:", r.text)
            payload.pop("parse_mode", None)
            payload["text"] = text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")
            requests.post(url, json=payload)
    except: pass

def send_telegram_photo(photo_bytes, caption, reply_markup=None):
    if not TG_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    files = {'photo': ('chart.png', photo_bytes, 'image/png')}
    data = {"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
    if reply_markup: data["reply_markup"] = json.dumps(reply_markup)
    try: 
        r = requests.post(url, files=files, data=data)
        if r.status_code != 200:
            print("TG Photo Error:", r.text)
            send_telegram(caption, reply_markup) 
    except: 
        send_telegram(caption, reply_markup)

headers = {'User-Agent': 'Mozilla/5.0'}
last_ticker_data, last_ticker_time = [], 0

def get_ticker_data():
    global last_ticker_data, last_ticker_time
    now = time.time()
    if last_ticker_data and (now - last_ticker_time < 60): return last_ticker_data
    try:
        res = requests.get("https://api.coindcx.com/exchange/ticker", headers=headers, timeout=10)
        if res.status_code == 200:
            last_ticker_data = res.json()
            last_ticker_time = now
            return last_ticker_data
    except: pass
    return last_ticker_data if last_ticker_data else []

# ---------------- INDIAN MARKET DATA ----------------
INDIAN_TICKERS = {
    "NIFTY 50": "^NSEI", "BANK NIFTY": "^NSEBANK", "SENSEX": "^BSESN",
    "RELIANCE": "RELIANCE.NS", "TCS": "TCS.NS", "HDFC BANK": "HDFCBANK.NS",
    "ICICI BANK": "ICICIBANK.NS", "INFOSYS": "INFY.NS", "ITC": "ITC.NS",
    "SBI": "SBIN.NS", "BHARTI AIRTEL": "BHARTIARTL.NS"
}

def get_yahoo_data(ticker, interval="15m", range="5d"):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={interval}&range={range}"
        res = requests.get(url, headers=headers, timeout=10).json()
        result = res['chart']['result'][0]
        closes = result['indicators']['quote'][0]['close']
        data = [c for c in closes if c is not None]
        if len(data) < 50: return None
        return data
    except: return None

def scan_indian_market():
    signals_found = 0
    for name, ticker in INDIAN_TICKERS.items():
        closes = get_yahoo_data(ticker)
        if not closes: continue
        
        df = pd.DataFrame(closes, columns=['close'])
        df = calculate_indicators(df)
        last, prev = df.iloc[-1], df.iloc[-2]
        
        signal = None
        if last['close'] > last['ema200'] and last['rsi'] > 60 and last['close'] > prev['close']:
            signal = "BUY"
        elif last['close'] < last['ema200'] and last['rsi'] < 40 and last['close'] < prev['close']:
            signal = "SELL"
            
        if signal:
            entry = last['close']
            risk = last['atr'] * 2.0
            if signal == "BUY": 
                sl, tp1 = entry - risk, entry + (risk * 2.0)
            else: 
                sl, tp1 = entry + risk, entry - (risk * 2.0)
                
            text = (
                f"🇮🇳 <b>#{name} {signal}</b>\n\n"
                f"Price: ₹{fmt(entry)}\n"
                f"SL: ₹{fmt(sl)}\n"
                f"Target: ₹{fmt(tp1)}\n\n"
                f"📊 RSI: {last['rsi']:.1f}"
            )
            send_telegram(text)
            signals_found += 1
            time.sleep(2)
    return signals_found

# ---------------- MONITOR TRADES ----------------
def monitor_trades():
    while True:
        try:
            tickers = get_ticker_data()
            if not tickers: time.sleep(10); continue
            price_map = {t['market']: float(t['last_price']) for t in tickers if isinstance(t, dict)}
            
            for sym, alert_data in list(price_alerts.items()):
                if sym in price_map:
                    curr_price = price_map[sym]
                    target = alert_data['price']
                    if (alert_data['type'] == 'above' and curr_price >= target) or (alert_data['type'] == 'below' and curr_price <= target):
                        clean = sym.replace("B-", "").replace("I-", "").replace("_", "")
                        send_telegram(f"🚨 <b>PRICE ALERT!</b>\n\n🪙 <b>Coin:</b> {clean}\n💰 <b>Target:</b> {fmt(target)}\n📈 <b>Current:</b> {fmt(curr_price)}")
                        del price_alerts[sym]
            
            for sym, trade in list(active_trades.items()):
                if sym not in price_map: continue
                curr_price = price_map[sym]
                signal, entry = trade['type'], trade['entry']
                sl, tp1, tp2, tp3 = trade['sl'], trade['tp1'], trade['tp2'], trade['tp3']
                clean_sym = sym.replace("B-", "").replace("I-", "").replace("_", "")
                res_text = None
                
                if 'highest' not in trade: trade['highest'] = entry
                if 'lowest' not in trade: trade['lowest'] = entry

                if signal == "BUY":
                    if curr_price > trade['highest']: trade['highest'] = curr_price
                    if curr_price <= sl:
                        res_text = f"❌ <b>{clean_sym} Hit STOP LOSS</b>\nPrice: {fmt(curr_price)}"
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'BUY', 'result': 'LOSS'})
                        del active_trades[sym]; save_active_trades()
                    elif curr_price >= tp3:
                        res_text = f"🚀 <b>{clean_sym} Hit TP3!</b>\nTrade Complete."
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'BUY', 'result': 'WIN'})
                        del active_trades[sym]; save_active_trades()
                    elif curr_price >= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1; trade['status'] = "TP2_HIT"
                        res_text = f"🔥 <b>{clean_sym} Hit TP2</b>\nSL moved to TP1 ({fmt(tp1)})."
                        save_active_trades()
                    elif curr_price >= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry; trade['status'] = "TP1_HIT"
                        res_text = f"✅ <b>{clean_sym} Hit TP1</b>\nSL moved to Entry ({fmt(entry)})."
                        save_active_trades()

                elif signal == "SELL":
                    if curr_price < trade['lowest']: trade['lowest'] = curr_price
                    if curr_price >= sl:
                        res_text = f"❌ <b>{clean_sym} Hit STOP LOSS</b>\nPrice: {fmt(curr_price)}"
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'SELL', 'result': 'LOSS'})
                        del active_trades[sym]; save_active_trades()
                    elif curr_price <= tp3:
                        res_text = f"🚀 <b>{clean_sym} Hit TP3!</b>\nTrade Complete."
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'SELL', 'result': 'WIN'})
                        del active_trades[sym]; save_active_trades()
                    elif curr_price <= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1; trade['status'] = "TP2_HIT"
                        res_text = f"🔥 <b>{clean_sym} Hit TP2</b>\nSL moved to TP1 ({fmt(tp1)})."
                        save_active_trades()
                    elif curr_price <= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry; trade['status'] = "TP1_HIT"
                        res_text = f"✅ <b>{clean_sym} Hit TP1</b>\nSL moved to Entry ({fmt(entry)})."
                        save_active_trades()
                
                if res_text:
                    try:
                        c_sym_exit = sym if '_' in sym else ('B-' + sym.replace('USDT', '_USDT') if 'USDT' in sym else 'I-' + sym.replace('INR', '_INR'))
                        k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym_exit}&interval={SCAN_TIMEFRAME}&limit=50", headers=headers, timeout=10).json()
                        if isinstance(k_res, list) and len(k_res) > 0:
                            k_res.reverse()
                            df_exit = pd.DataFrame(k_res)
                            for col in ['close', 'high', 'low', 'volume', 'open']: df_exit[col] = df_exit[col].astype(float)
                            chart_img = generate_chart_image(df_exit, clean_sym, signal, entry, sl, tp1, tp2, tp3)
                            dcx_link = f"coindcx://trade/{clean_sym}" 
                            markup = {"inline_keyboard": [[{"text": "📈 Open in CoinDCX App", "url": dcx_link}]]}
                            if chart_img: send_telegram_photo(chart_img, res_text, reply_markup=markup)
                            else: send_telegram(res_text, reply_markup=markup)
                        else: send_telegram(res_text)
                    except: send_telegram(res_text)
                        
        except: pass
        time.sleep(15)

# ---------------- FAST MULTI-THREADED SCANNER ----------------
def check_single_coin(c):
    try:
        m = str(c.get('market', ''))
        clean_name = m.replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "")
        if watchlist and clean_name not in watchlist: return None
        
        c_sym = m if '_' in m else ('B-' + m.replace('USDT', '_USDT') if 'USDT' in m else 'I-' + m.replace('INR', '_INR'))
        
        k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval={SCAN_TIMEFRAME}&limit=200", headers=headers, timeout=5)
        if k_res.status_code != 200: return None
            
        k_res = k_res.json()
        if not isinstance(k_res, list) or len(k_res) < 200: return None
        
        k_res.reverse() 
        df = pd.DataFrame(k_res)
        for col in ['close', 'high', 'low', 'volume', 'open']: df[col] = df[col].astype(float)
        df = calculate_indicators(df)
        last, prev = df.iloc[-1], df.iloc[-2]
        
        macd_bullish = last['macd'] > last['macd_signal']
        macd_bearish = last['macd'] < last['macd_signal']
        # Vol Spike relaxed to 0.8x for more signals
        vol_spike = last['volume'] > (df['volume'].tail(20).mean() * 0.8)

        signal = None
        # VWAP removed for faster signals
        if last['close'] > last['ema200'] and last['rsi'] > 50 and macd_bullish and vol_spike and last['close'] > last['open']: signal = "BUY"
        elif last['close'] < last['ema200'] and last['rsi'] < 50 and macd_bearish and vol_spike and last['close'] < last['open']: signal = "SELL"

        if signal:
            return {
                'market': m, 'clean': clean_name, 'signal': signal, 
                'entry': last['close'], 'rsi': last['rsi'], 
                'df': df, 'ema200': last['ema200']
            }
    except: pass
    return None

def run_manual_scan(tf):
    global MANUAL_SCAN_ACTIVE
    MANUAL_SCAN_ACTIVE = True
    send_telegram(f"⏳ Scanning Market on <b>{tf}</b>...")
    signals_found = 0
    
    try:
        data = get_ticker_data()
        if not data: return send_telegram("❌ Failed to fetch market data.")

        valid_coins = [c for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market', '')) or 'INR' in str(c.get('market', ''))) and float(c.get('volume', 0)) > 50000]
        
        # Multi-threading: 10 coins at a time
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(check_single_coin, valid_coins))

        for res in results:
            if res:
                m, clean_sym, signal = res['market'], res['clean'], res['signal']
                entry, risk = res['entry'], res['df'].iloc[-1]['atr'] * 2.0 
                rsi, ema200_val = res['rsi'], res['ema200']
                
                if signal == "BUY": 
                    sl, tp1, tp2, tp3 = entry - risk, entry + (risk * 2.0), entry + (risk * 3.0), entry + (risk * 4.0)
                else: 
                    sl, tp1, tp2, tp3 = entry + risk, entry - (risk * 2.0), entry - (risk * 3.0), entry - (risk * 4.0)
                    
                ema200_status = "🟢" if entry > ema200_val else "🔴"
                
                text = (
                    f"<b>#{clean_sym} {signal} (AUTO)</b>\n\n"
                    f"Entry: {fmt(entry)}\n"
                    f"SL: {fmt(sl)}\n"
                    f"TP1: {fmt(tp1)}\n"
                    f"TP2: {fmt(tp2)}\n"
                    f"TP3: {fmt(tp3)}\n\n"
                    f"📊 RSI: {rsi:.1f} | EMA200: {ema200_status}\n"
                    f"#{tf.upper()}TRADE"
                )
                
                dcx_link = f"coindcx://trade/{clean_sym}" 
                markup = {"inline_keyboard": [
                    [{"text": f"📋 Copy '{clean_sym}'", "copy_text": {"text": clean_sym}}],
                    [{"text": "📈 Open in CoinDCX App", "url": dcx_link}],
                    [{"text": "❌ Close Trade", "callback_data": f"close_{m}"}]
                ]}
                
                chart_img = generate_chart_image(res['df'], clean_sym, signal, entry, sl, tp1, tp2, tp3)
                if chart_img: send_telegram_photo(chart_img, text, reply_markup=markup)
                else: send_telegram(text, reply_markup=markup)
                
                active_trades[m] = {'type': signal, 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3, 'status': 'OPEN'}
                save_active_trades()
                signals_found += 1
                time.sleep(1)
                
        send_telegram(f"✅ Scan Completed. Found {signals_found} signals.")
    except Exception as e:
        send_telegram(f"❌ Scan Error: {str(e)}")
    finally: MANUAL_SCAN_ACTIVE = False

# ---------------- NEW FEATURES IMPLEMENTATION ----------------
def calc_risk(symbol, capital):
    try:
        data = get_ticker_data()
        price = None
        for c in data:
            if isinstance(c, dict):
                m_clean = str(c.get('market')).replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "").replace("USDT", "").replace("INR", "")
                if m_clean == symbol:
                    price = float(c['last_price'])
                    break
        if not price: return send_telegram(f"❌ {symbol} not found.")
        
        risk_amt = capital * 0.01
        sl_dist = price * 0.02
        qty = risk_amt / sl_dist
        
        msg = (f"🛡️ <b>Position Size Calculator</b>\n\n"
               f"🪙 Coin: {symbol}\n"
               f"💰 Price: {fmt(price)}\n"
               f"💼 Capital: ₹${capital}\n"
               f"⚠️ Risk (1%): ₹${risk_amt:.2f}\n"
               f"🛑 SL (2%): {fmt(price * 0.98)}\n\n"
               f"👉 <b>Buy Quantity:</b> {qty:.4f} {symbol}\n"
               f"💵 <b>Total Invest:</b> ₹${(qty*price):.2f}")
        send_telegram(msg)
    except: send_telegram("❌ Error calculating risk.")

def scan_mtf(symbol):
    try:
        c_sym = f"B-{symbol}_USDT"
        msg = f"📊 <b>Multi-Timeframe Trend: {symbol}</b>\n\n"
        for tf in ['15m', '1h', '4h', '1d']:
            res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval={tf}&limit=200", headers=headers, timeout=5).json()
            if isinstance(res, list) and len(res) >= 50:
                res.reverse()
                closes = [float(c['close']) for c in res]
                ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().iloc[-1]
                trend = "🟢 BULLISH" if closes[-1] > ema50 else "🔴 BEARISH"
                msg += f"⏱️ <b>{tf}:</b> {trend}\n"
        send_telegram(msg)
    except: send_telegram("❌ Error scanning MTF.")

def run_backtest(symbol):
    send_telegram(f"⏳ Backtesting <b>{symbol}</b> (Last 500 Candles)...")
    try:
        c_sym = f"B-{symbol}_USDT"
        res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval=15m&limit=500", headers=headers, timeout=10).json()
        if not isinstance(res, list) or len(res) < 200: return send_telegram("❌ Not enough data.")
        res.reverse()
        df = pd.DataFrame(res)
        for col in ['close', 'high', 'low', 'volume', 'open']: df[col] = df[col].astype(float)
        df = calculate_indicators(df)
        
        wins, losses = 0, 0
        for i in range(200, len(df)-10):
            row, prev = df.iloc[i], df.iloc[i-1]
            macd_bullish = row['macd'] > row['macd_signal']
            macd_bearish = row['macd'] < row['macd_signal']
            vol_spike = row['volume'] > (df['volume'].iloc[i-20:i].mean() * 0.8)
            
            signal = None
            if row['close'] > row['ema200'] and row['rsi'] > 50 and macd_bullish and vol_spike and row['close'] > row['open']: signal = "BUY"
            elif row['close'] < row['ema200'] and row['rsi'] < 50 and macd_bearish and vol_spike and row['close'] < row['open']: signal = "SELL"
                
            if signal:
                entry, risk = row['close'], row['atr'] * 2.0
                outcome = "OPEN"
                for j in range(i+1, min(i+11, len(df))):
                    if signal == "BUY":
                        if df.iloc[j]['low'] <= entry - risk: outcome = "LOSS"; break
                        if df.iloc[j]['high'] >= entry + (risk * 2.0): outcome = "WIN"; break
                    else:
                        if df.iloc[j]['high'] >= entry + risk: outcome = "LOSS"; break
                        if df.iloc[j]['low'] <= entry - (risk * 2.0): outcome = "WIN"; break
                if outcome == "WIN": wins += 1
                elif outcome == "LOSS": losses += 1
                
        total = wins + losses
        wr = (wins/total*100) if total > 0 else 0
        send_telegram(f"📈 <b>Backtest ({symbol} 15m)</b>\n\n🟢 Wins: {wins}\n🔴 Losses: {losses}\n📊 <b>Win Rate:</b> {wr:.1f}%")
    except: send_telegram("❌ Backtest failed.")

def check_whale(symbol):
    try:
        c_sym = f"B-{symbol}_USDT"
        res = requests.get(f"https://api.coindcx.com/exchange/v1/orders/orderbook?pair={c_sym}", headers=headers, timeout=5).json()
        bids = sum([float(b[1]) for b in res['bids'][:20]])
        asks = sum([float(a[1]) for a in res['asks'][:20]])
        
        msg = f"🐋 <b>Whale Order Book: {symbol}</b>\n\n"
        msg += f"🟢 Buy Volume (Bids): {bids:,.2f}\n"
        msg += f"🔴 Sell Volume (Asks): {asks:,.2f}\n\n"
        
        if asks > bids * 1.5: msg += "⚠️ <b>Heavy Selling Pressure!</b> Fake breakout likely."
        elif bids > asks * 1.5: msg += "🚀 <b>Heavy Buying Pressure!</b> Strong support."
        else: msg += "⚖️ <b>Balanced Market</b>"
        send_telegram(msg)
    except: send_telegram("❌ Order book not available right now.")

# ---------------- TELEGRAM COMMANDS & MENU ----------------
def telegram_commands():
    global SCAN_TIMEFRAME
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates?offset={offset}&timeout=30"
            res = requests.get(url, timeout=35).json()
            if res.get("ok") and res["result"]:
                for update in res["result"]:
                    offset = update["update_id"] + 1
                    
                    if "callback_query" in update:
                        callback_id = update["callback_query"]["id"]
                        text = update["callback_query"]["data"]
                        chat_id = update["callback_query"]["message"]["chat"]["id"]
                        
                        if text.startswith("close_"):
                            sym_to_close = text.replace("close_", "")
                            if sym_to_close in active_trades:
                                del active_trades[sym_to_close]
                                save_active_trades()
                                clean = sym_to_close.replace("B-", "").replace("I-", "").replace("_", "")
                                send_telegram(f"🛑 <b>Trade Manually Closed</b>\n🪙 Coin: {clean}")
                            else: send_telegram("⚠️ Trade already closed.")
                            try: requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/answerCallbackQuery?callback_query_id={callback_id}")
                            except: pass
                            continue
                    
                    else:
                        text = update.get("message", {}).get("text", "")
                        chat_id = update.get("message", {}).get("chat", {}).get("id")
                    
                    if str(chat_id) == str(TG_CHAT_ID):
                        # -------- MEGA MENU --------
                        if text in ["/start", "/menu"]:
                            markup = {"inline_keyboard": [
                                [{"text": "🚀 SCAN NOW (Auto Signal)", "callback_data": "scan_now"}],
                                [{"text": "🌐 Dashboard", "url": "https://my-trading-bot-9se1.onrender.com"}, {"text": "🌍 Global", "callback_data": "/global"}],
                                [{"text": "🇮🇳 Indian Market Scan", "callback_data": "/scanindia"}],
                                [{"text": "📊 Nifty 50", "callback_data": "/nifty"}, {"text": "🏦 Bank Nifty", "callback_data": "/banknifty"}],
                                [{"text": "📈 Top Stocks", "callback_data": "/topstocks"}, {"text": "🪙 Crypto INR", "callback_data": "/cryptoinr"}],
                                [{"text": "🌡️ Sentiment", "callback_data": "/sentiment"}, {"text": "🚀 Pump/Dump", "callback_data": "/pump"}],
                                [{"text": "🏆 Gainers", "callback_data": "/top"}, {"text": "📉 Losers", "callback_data": "/bottom"}],
                                [{"text": "📈 Active Trades", "callback_data": "/trades"}, {"text": "📓 Journal", "callback_data": "/journal"}],
                                [{"text": "💼 Performance", "callback_data": "/performance"}, {"text": "📊 RSI Scanner", "callback_data": "/rsi"}],
                                [{"text": "🔊 Volume Top", "callback_data": "/volume"}, {"text": "🗑️ Clear Alerts", "callback_data": "/clearalerts"}],
                                [{"text": "🎯 Signal Scan", "callback_data": "help_signal"}, {"text": "⚙️ Scan TF", "callback_data": "help_scan"}],
                                [{"text": "🛡️ Risk Calc", "callback_data": "help_risk"}, {"text": "📊 MTF Trend", "callback_data": "help_mtf"}],
                                [{"text": "📉 Backtest", "callback_data": "help_backtest"}, {"text": "🐋 Whale", "callback_data": "help_whale"}],
                                [{"text": "🔍 Search", "callback_data": "help_search"}, {"text": "⚡ Price", "callback_data": "help_price"}],
                                [{"text": "🔬 Analysis", "callback_data": "help_analysis"}, {"text": "📉 Zones", "callback_data": "help_zones"}],
                                [{"text": "🔔 Alert", "callback_data": "help_alert"}, {"text": "⭐ Watchlist", "callback_data": "help_watch"}],
                                [{"text": "🗑️ Close All Trades", "callback_data": "/closeall"}]
                            ]}
                            send_telegram(f"👋 <b>Welcome to cripto_adda V43!</b>\nTF: <b>{SCAN_TIMEFRAME}</b> | Coins: <b>{len(watchlist) if watchlist else 'All'}</b>\n\nSelect an option:", reply_markup=markup)

                        elif text == "scan_now":
                            send_telegram("⏳ Running Fast Multi-Threaded Scan... Please wait.")
                            Thread(target=run_manual_scan, args=(SCAN_TIMEFRAME,)).start()

                        # -------- HELP GUIDES --------
                        elif text == "help_search": send_telegram("🔍 <b>Search Command:</b>\nType: <code>/search BTC</code>")
                        elif text == "help_price": send_telegram("⚡ <b>Price Command:</b>\nType: <code>/p BTC</code>")
                        elif text == "help_analysis": send_telegram("🔬 <b>Analysis Command:</b>\nType: <code>/analysis BTC</code>")
                        elif text == "help_zones": send_telegram("📉 <b>Zones Command:</b>\nType: <code>/zones BTC</code>")
                        elif text == "help_alert": send_telegram("🔔 <b>Alert Command:</b>\nType: <code>/alert BTC 65000</code>")
                        elif text == "help_signal": send_telegram("🎯 <b>Signal Scan:</b>\nRun manual strong scan:\n<code>/signal 15m</code>\n<code>/signal 1h</code>\n<code>/signal 4h</code>\n\nTo resume auto-scan:\n<code>/signal clear</code>")
                        elif text == "help_scan": send_telegram("⚙️ <b>Scan TF:</b>\nChange auto-scan TF: <code>/scan 15m</code> or <code>/scan 1h</code>")
                        elif text == "help_watch": send_telegram("⭐ <b>Watchlist:</b>\nAdd: <code>/watch BTC,ETH</code>\nClear: <code>/clearwatch</code>")
                        
                        elif text == "help_risk": send_telegram("🛡️ <b>Risk Command:</b>\nType: <code>/risk BTC 10000</code>")
                        elif text == "help_mtf": send_telegram("📊 <b>MTF Command:</b>\nType: <code>/mtf BTC</code>")
                        elif text == "help_backtest": send_telegram("📉 <b>Backtest Command:</b>\nType: <code>/backtest BTC</code>")
                        elif text == "help_whale": send_telegram("🐋 <b>Whale Command:</b>\nType: <code>/whale BTC</code>")

                        # -------- INDIAN MARKET FEATURES --------
                        elif text == "/scanindia":
                            send_telegram("⏳ Scanning Indian Stocks...")
                            Thread(target=scan_indian_market).start()
                            
                        elif text == "/nifty":
                            closes = get_yahoo_data("^NSEI")
                            if closes:
                                df = calculate_indicators(pd.DataFrame(closes, columns=['close']))
                                last = df.iloc[-1]
                                send_telegram(f"📊 <b>NIFTY 50</b>\nPrice: {fmt(last['close'])}\nRSI: {last['rsi']:.1f}\nTrend: {'🟢 BULLISH' if last['close'] > last['ema200'] else '🔴 BEARISH'}")
                            else: send_telegram("❌ Data unavailable.")

                        elif text == "/banknifty":
                            closes = get_yahoo_data("^NSEBANK")
                            if closes:
                                df = calculate_indicators(pd.DataFrame(closes, columns=['close']))
                                last = df.iloc[-1]
                                send_telegram(f"🏦 <b>BANK NIFTY</b>\nPrice: {fmt(last['close'])}\nRSI: {last['rsi']:.1f}\nTrend: {'🟢 BULLISH' if last['close'] > last['ema200'] else '🔴 BEARISH'}")
                            else: send_telegram("❌ Data unavailable.")

                        elif text == "/topstocks":
                            send_telegram("⏳ Fetching Top Indian Stocks...")
                            msg = "📈 <b>Top Indian Stocks (Live)</b>\n\n"
                            try:
                                for name, ticker in INDIAN_TICKERS.items():
                                    if "NIFTY" in name or "SENSEX" in name: continue
                                    closes = get_yahoo_data(ticker)
                                    if closes:
                                        df = calculate_indicators(pd.DataFrame(closes, columns=['close']))
                                        last = df.iloc[-1]
                                        msg += f"<b>{name}:</b> ₹{fmt(last['close'])} (RSI: {last['rsi']:.1f})\n"
                                send_telegram(msg)
                            except: send_telegram("❌ Error fetching stocks.")

                        elif text == "/cryptoinr":
                            send_telegram("⏳ Scanning Crypto INR pairs...")
                            Thread(target=run_manual_scan, args=("15m",)).start() 

                        # -------- NEW CRYPTO FEATURES --------
                        elif text.startswith("/risk "):
                            parts = text.split()
                            if len(parts) == 3: Thread(target=calc_risk, args=(parts[1].upper(), float(parts[2]))).start()
                            else: send_telegram("⚠️ Format: <code>/risk BTC 10000</code>")

                        elif text.startswith("/mtf "):
                            parts = text.split()
                            if len(parts) == 2: Thread(target=scan_mtf, args=(parts[1].upper(),)).start()
                            else: send_telegram("⚠️ Format: <code>/mtf BTC</code>")

                        elif text.startswith("/backtest "):
                            parts = text.split()
                            if len(parts) == 2: Thread(target=run_backtest, args=(parts[1].upper(),)).start()
                            else: send_telegram("⚠️ Format: <code>/backtest BTC</code>")

                        elif text.startswith("/whale "):
                            parts = text.split()
                            if len(parts) == 2: Thread(target=check_whale, args=(parts[1].upper(),)).start()
                            else: send_telegram("⚠️ Format: <code>/whale BTC</code>")

                        elif text == "/closeall":
                            active_trades.clear()
                            save_active_trades()
                            send_telegram("🛑 <b>All Active Trades Cleared!</b>")

                        elif text == "/trades":
                            if not active_trades: send_telegram("💤 <b>No active trades.</b>")
                            else:
                                send_telegram("📈 <b>Your Active Trades:</b>")
                                for s, t in active_trades.items():
                                    clean_s = s.replace("B-","").replace("I-","").replace("_","")
                                    msg = f"🪙 <b>{clean_s}</b> ({t['type']})\nEntry: {fmt(t['entry'])} | SL: {fmt(t['sl'])}"
                                    markup = {"inline_keyboard": [[{"text": f"❌ Close {clean_s}", "callback_data": f"close_{s}"}]]}
                                    send_telegram(msg, reply_markup=markup)
                                    time.sleep(0.5)

                        # -------- STANDARD CRYPTO FEATURES --------
                        elif text.startswith("/signal"):
                            parts = text.split()
                            if len(parts) == 1: send_telegram("⚠️ Use: <code>/signal 15m</code> or <code>/signal clear</code>")
                            elif parts[1].lower() == "clear":
                                SCAN_TIMEFRAME = "15m"
                                send_telegram("✅ <b>Auto-scan resumed on 15m timeframe.</b>")
                            elif parts[1] in ['15m', '1h', '4h']:
                                target_tf = parts[1]
                                send_telegram(f"⏳ Running <b>Strong</b> manual scan for <b>{target_tf}</b>...")
                                Thread(target=run_manual_scan, args=(target_tf,)).start()
                            else: send_telegram("⚠️ Invalid timeframe.")

                        elif text == "/global":
                            send_telegram("⏳ Fetching Global Markets...")
                            try:
                                symbols = {"GOLD": "GC=F", "SILVER": "SI=F", "OIL": "CL=F", "AMZN": "AMZN", "GOOGL": "GOOGL", "NVDA": "NVDA", "AAPL": "AAPL"}
                                msg = "🌍 <b>Global Markets</b>\n\n"
                                for name, sym in symbols.items():
                                    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", headers=headers, timeout=5).json()
                                    price = r['chart']['result'][0]['meta']['regularMarketPrice']
                                    prev = r['chart']['result'][0]['meta']['chartPreviousClose']
                                    chg = ((price - prev) / prev) * 100
                                    msg += f"{'🟢' if chg >= 0 else '🔴'} <b>{name}:</b> ${price:.2f} ({chg:+.2f}%)\n"
                                send_telegram(msg)
                            except: pass

                        elif text == "/sentiment":
                            try:
                                r = requests.get("https://api.alternative.me/fng/", timeout=5).json()
                                send_telegram(f"🌡️ <b>Market Sentiment</b>\n\n📊 Value: {r['data'][0]['value']}/100\n📝 Status: {r['data'][0]['value_classification']}")
                            except: send_telegram("❌ Error.")

                        elif text == "/pump":
                            send_telegram("⏳ Scanning for Pumps/Dumps...")
                            try:
                                data = get_ticker_data()
                                movers = [c for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market')) or 'INR' in str(c.get('market'))) and abs(float(c.get('change24hour', 0))) > 10]
                                movers = sorted(movers, key=lambda x: abs(float(x.get('change24hour', 0))), reverse=True)[:5]
                                if not movers: return send_telegram("🤷‍♂️ No major pumps/dumps right now.")
                                msg = "🚀 <b>Pump & Dump Alerts (Top 5)</b>\n\n"
                                for c in movers:
                                    clean = c['market'].replace("B-", "").replace("I-", "").replace("_", "")
                                    msg += f"{'🟢' if float(c['change24hour']) > 0 else '🔴'} <b>{clean}:</b> {float(c['change24hour']):+.2f}% | {fmt(c['last_price'])}\n"
                                send_telegram(msg)
                            except: pass

                        elif text == "/top" or text == "/bottom":
                            send_telegram("⏳ Fetching...")
                            try:
                                data = get_ticker_data()
                                valid = [{'m': str(c.get('market')), 'c': float(c.get('change24hour', 0)), 'p': float(c.get('last_price', 0))} for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market')) or 'INR' in str(c.get('market')))]
                                sorted_coins = sorted(valid, key=lambda x: x['c'], reverse=(text=="/top"))[:5]
                                msg = f"{'🏆 <b>Top Gainers</b>' if text=='/top' else '📉 <b>Top Losers</b>'}\n\n"
                                for i, c in enumerate(sorted_coins): msg += f"{i+1}. <b>{c['m'].replace('B-','').replace('I-','').replace('_','')}</b>: {c['c']:.2f}% | {fmt(c['p'])}\n"
                                send_telegram(msg)
                            except: pass

                        elif text == "/journal":
                            j = get_journal()
                            if not j: send_telegram("📓 Empty.")
                            else:
                                msg = "📓 <b>Last 5 Trades:</b>\n\n"
                                for t in j[-5:]: msg += f"🪙 {t['coin']} ({t['type']}) - {t['result']}\n"
                                send_telegram(msg)

                        elif text == "/performance":
                            j = get_journal()
                            if not j: send_telegram("💼 <b>No past trades in journal.</b>")
                            else:
                                wins = sum(1 for t in j if t['result'] == 'WIN')
                                losses = sum(1 for t in j if t['result'] == 'LOSS')
                                total = wins + losses
                                wr = (wins/total*100) if total > 0 else 0
                                send_telegram(f"💼 <b>Trading Performance</b>\n\n🟢 Wins: {wins}\n🔴 Losses: {losses}\n📈 <b>Win Rate:</b> {wr:.1f}%\n📊 Total Trades: {total}")

                        elif text == "/rsi":
                            send_telegram("⏳ Scanning top volume coins for RSI extremes (15m)...")
                            try:
                                data = get_ticker_data()
                                valid = [c for c in data if isinstance(c, dict) and 'USDT' in str(c.get('market'))]
                                valid = sorted(valid, key=lambda x: float(x.get('volume', 0)), reverse=True)[:10]
                                oversold, overbought = [], []
                                for c in valid:
                                    sym = c['market']
                                    c_sym = 'B-' + sym.replace('USDT', '_USDT') if '_' not in sym else sym
                                    k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval=15m&limit=50", headers=headers, timeout=5).json()
                                    if isinstance(k_res, list) and len(k_res) >= 50:
                                        k_res.reverse()
                                        closes = [float(x['close']) for x in k_res]
                                        s = pd.Series(closes)
                                        delta = s.diff()
                                        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                                        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                                        rsi = (100 - (100 / (1 + (gain / loss)))).iloc[-1]
                                        clean = sym.replace('B-','').replace('_','')
                                        if rsi < 30: oversold.append(f"🟢 {clean} (RSI: {rsi:.1f})")
                                        elif rsi > 70: overbought.append(f"🔴 {clean} (RSI: {rsi:.1f})")
                                msg = "📊 <b>RSI Scanner (Top 10 Coins)</b>\n\n"
                                msg += "📉 <b>Oversold (<30):</b>\n" + ("\n".join(oversold) if oversold else "None") + "\n\n"
                                msg += "📈 <b>Overbought (>70):</b>\n" + ("\n".join(overbought) if overbought else "None")
                                send_telegram(msg)
                            except: pass

                        elif text == "/volume":
                            send_telegram("⏳ Fetching Top Volume Coins...")
                            try:
                                data = get_ticker_data()
                                valid = [c for c in data if isinstance(c, dict) and 'USDT' in str(c.get('market'))]
                                valid = sorted(valid, key=lambda x: float(x.get('volume', 0)), reverse=True)[:5]
                                msg = "🔊 <b>Top 5 Volume Coins (USDT)</b>\n\n"
                                for i, c in enumerate(valid):
                                    clean = c['market'].replace('B-','').replace('_','')
                                    msg += f"{i+1}. <b>{clean}</b>\nVol: {float(c['volume']):,.0f} | Price: {fmt(c['last_price'])}\n\n"
                                send_telegram(msg)
                            except: pass

                        elif text == "/clearalerts":
                            price_alerts.clear()
                            send_telegram("🗑️ <b>All Alerts Cleared!</b>")

                        elif text == "/clearwatch":
                            watchlist.clear()
                            send_telegram("✅ <b>Watchlist cleared.</b>")

                        elif text.startswith("/p "):
                            target = text.split()[1].upper()
                            data = get_ticker_data()
                            found = False
                            for c in data:
                                if isinstance(c, dict):
                                    m_clean = str(c.get('market')).replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "").replace("USDT", "").replace("INR", "")
                                    if m_clean == target:
                                        clean = str(c.get('market')).replace('B-','').replace('I-','').replace('_','')
                                        send_telegram(f"⚡ <b>{clean}</b>\n💰 Price: {fmt(c['last_price'])}\n📈 24h: {float(c['change24hour']):+.2f}%")
                                        found = True
                                        break
                            if not found: send_telegram("❌ Coin not found.")

                        elif text.startswith("/watch"):
                            parts = text.split()
                            if len(parts) > 1:
                                coins = parts[1].upper().split(',')
                                for coin in coins: watchlist.add(coin.strip())
                                send_telegram(f"✅ <b>Added {', '.join(coins)} to Watchlist.</b>")
                            else: send_telegram("⚠️ Use: <code>/watch BTC,ETH</code>")

                        elif text.startswith("/analysis"):
                            parts = text.split()
                            if len(parts) > 1:
                                target = parts[1].upper()
                                send_telegram(f"⏳ Analyzing <b>{target}</b>...")
                                try:
                                    c_sym = f"B-{target}_USDT"
                                    msg = f"🔬 <b>Analysis: {target}</b>\n\n"
                                    for tf in ['15m', '1h', '4h']:
                                        res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval={tf}&limit=100", headers=headers, timeout=5).json()
                                        if isinstance(res, list) and len(res) >= 50:
                                            res.reverse()
                                            closes = [float(c['close']) for c in res]
                                            ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().iloc[-1]
                                            msg += f"⏱️ <b>{tf}:</b> {'🟢 BULLISH' if closes[-1] > ema50 else '🔴 BEARISH'}\n"
                                    send_telegram(msg)
                                except: pass

                        elif text.startswith("/zones"):
                            parts = text.split()
                            if len(parts) > 1:
                                target = parts[1].upper()
                                try:
                                    c_sym = f"B-{target}_USDT"
                                    res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval=15m&limit=100", headers=headers, timeout=5).json()
                                    if isinstance(res, list) and len(res) >= 50:
                                        res.reverse()
                                        highs = [float(c['high']) for c in res]
                                        lows = [float(c['low']) for c in res]
                                        send_telegram(f"📉 <b>Zones ({target})</b>\n\nCurrent: {fmt(res[-1]['close'])}\n🟢 Support: {fmt(min(lows[-20:]))}\n🔴 Resistance: {fmt(max(highs[-20:]))}")
                                except: pass

                        elif text.startswith("/alert"):
                            parts = text.split()
                            if len(parts) == 3:
                                target, pr = parts[1].upper(), float(parts[2])
                                data = get_ticker_data()
                                for c in data:
                                    if isinstance(c, dict) and target in str(c.get('market')):
                                        price_alerts[str(c.get('market'))] = {'price': pr, 'type': 'above' if pr > float(c.get('last_price', 0)) else 'below'}
                                        send_telegram(f"✅ <b>Alert set for {target} at {fmt(pr)}</b>")
                                        break
                            else: send_telegram("⚠️ Use: <code>/alert BTC 65000</code>")

                        elif text.startswith("/scan"):
                            parts = text.split()
                            if len(parts) > 1 and parts[1] in ['15m','1h','4h']:
                                SCAN_TIMEFRAME = parts[1]
                                send_telegram(f"✅ <b>Scanner TF: {SCAN_TIMEFRAME}</b>")

                        elif text.startswith("/search"):
                            parts = text.split()
                            if len(parts) > 1:
                                target = parts[1].upper()
                                send_telegram(f"⏳ Searching <b>{target}</b>...")
                                try:
                                    data = get_ticker_data()
                                    for c in data:
                                        if isinstance(c, dict):
                                            m = str(c.get('market'))
                                            m_clean = m.replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "").replace("USDT", "").replace("INR", "")
                                            if m_clean == target:
                                                send_telegram(f"🔍 <b>{m.replace('B-','').replace('_','')}</b>\nPrice: {fmt(c['last_price'])}\nChange: {float(c['change24hour']):.2f}%")
                                                break
                                except: pass
                            
        except: pass
        time.sleep(2)

# ---------------- INDICATORS & AUTO SCANNER ----------------
def calculate_indicators(df):
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    df['tr'] = pd.concat([df['high'] - df['low'], abs(df['high'] - df['close'].shift()), abs(df['low'] - df['close'].shift())], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(window=14).mean()
    df['vwap'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
    return df

def scan_market():
    global MANUAL_SCAN_ACTIVE
    if MANUAL_SCAN_ACTIVE:
        time.sleep(10)
        return
    run_manual_scan(SCAN_TIMEFRAME)

if __name__ == "__main__":
    load_active_trades()
    keep_alive()
    Thread(target=monitor_trades).start()
    Thread(target=telegram_commands).start()
    while True:
        scan_market()
        time.sleep(300)
