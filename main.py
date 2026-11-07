import os
import requests
import time
import pandas as pd
from flask import Flask
from threading import Thread
import datetime
import json

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
        res = requests.post("https://quickchart.io/chart", json=payload, timeout=15)
        if res.status_code == 200: return res.content
    except Exception as e:
        print("Chart Error:", e)
    return None

# ---------------- WEB DASHBOARD ----------------
@app.route('/')
def home():
    html = f"""
    <html><head><title>cripto_adda V38</title><meta http-equiv="refresh" content="30">
    <style>body{{background-color:#12161e;color:#e0e0e0;font-family:sans-serif;padding:20px;}}.container{{max-width:900px;margin:auto;}}.card{{background-color:#1a1e29;padding:15px;border-radius:8px;margin-bottom:15px;border:1px solid #2a2e39;}}.buy{{border-left:5px solid #00c864;}}.sell{{border-left:5px solid #ff3c3c;}}table{{width:100%;border-collapse:collapse;margin-top:10px;}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #2a2e39;}}</style></head>
    <body><div class="container"><h1>🤖 cripto_adda V38</h1>
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
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    if reply_markup: payload["reply_markup"] = reply_markup
    try: requests.post(url, json=payload)
    except: pass

def send_telegram_photo(photo_bytes, caption, reply_markup=None):
    if not TG_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    files = {'photo': ('chart.png', photo_bytes, 'image/png')}
    data = {"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
    if reply_markup: data["reply_markup"] = json.dumps(reply_markup)
    try: requests.post(url, files=files, data=data)
    except: pass

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
                f"🇮🇳 *#{name} {signal}*\n\n"
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
                        send_telegram(f"🚨 *PRICE ALERT!*\n\n🪙 *Coin:* {clean}\n💰 *Target:* {fmt(target)}\n📈 *Current:* {fmt(curr_price)}")
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
                        res_text = f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {fmt(curr_price)}"
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'BUY', 'result': 'LOSS'})
                        del active_trades[sym]; save_active_trades()
                    elif curr_price >= tp3:
                        res_text = f"🚀 *{clean_sym} Hit TP3!*\nTrade Complete."
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'BUY', 'result': 'WIN'})
                        del active_trades[sym]; save_active_trades()
                    elif curr_price >= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1; trade['status'] = "TP2_HIT"
                        res_text = f"🔥 *{clean_sym} Hit TP2*\nSL moved to TP1 ({fmt(tp1)})."
                        save_active_trades()
                    elif curr_price >= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry; trade['status'] = "TP1_HIT"
                        res_text = f"✅ *{clean_sym} Hit TP1*\nSL moved to Entry ({fmt(entry)})."
                        save_active_trades()

                elif signal == "SELL":
                    if curr_price < trade['lowest']: trade['lowest'] = curr_price
                    if curr_price >= sl:
                        res_text = f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {fmt(curr_price)}"
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'SELL', 'result': 'LOSS'})
                        del active_trades[sym]; save_active_trades()
                    elif curr_price <= tp3:
                        res_text = f"🚀 *{clean_sym} Hit TP3!*\nTrade Complete."
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'SELL', 'result': 'WIN'})
                        del active_trades[sym]; save_active_trades()
                    elif curr_price <= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1; trade['status'] = "TP2_HIT"
                        res_text = f"🔥 *{clean_sym} Hit TP2*\nSL moved to TP1 ({fmt(tp1)})."
                        save_active_trades()
                    elif curr_price <= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry; trade['status'] = "TP1_HIT"
                        res_text = f"✅ *{clean_sym} Hit TP1*\nSL moved to Entry ({fmt(entry)})."
                        save_active_trades()
                
                # --- ADDED: SEND CHART ON EXIT ---
                if res_text:
                    try:
                        k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={sym}&interval={SCAN_TIMEFRAME}&limit=50", headers=headers, timeout=5).json()
                        k_res.reverse()
                        df_exit = pd.DataFrame(k_res)
                        for col in ['close', 'high', 'low', 'volume', 'open']: df_exit[col] = df_exit[col].astype(float)
                        chart_img = generate_chart_image(df_exit, clean_sym, signal, entry, sl, tp1, tp2, tp3)
                        
                        dcx_link = f"coindcx://trade/{clean_sym}" 
                        markup = {"inline_keyboard": [[{"text": "📈 Open in CoinDCX App", "url": dcx_link}]]}
                        
                        if chart_img:
                            send_telegram_photo(chart_img, res_text, reply_markup=markup)
                        else:
                            send_telegram(res_text, reply_markup=markup)
                    except:
                        send_telegram(res_text)
                        
        except: pass
        time.sleep(15)

# ---------------- MANUAL SIGNAL SCANNER ----------------
def run_manual_scan(tf):
    global MANUAL_SCAN_ACTIVE
    MANUAL_SCAN_ACTIVE = True
    signals_found = 0
    
    try:
        data = get_ticker_data()
        if not data: 
            send_telegram("❌ Failed to fetch market data.")
            return

        for c in data:
            if not isinstance(c, dict): continue
            m = str(c.get('market', ''))
            if ('USDT' in m or 'INR' in m) and float(c.get('volume', 0)) > 50000:
                clean_name = m.replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "")
                if watchlist and clean_name not in watchlist: continue
                
                c_sym = m if '_' in m else ('B-' + m.replace('USDT', '_USDT') if 'USDT' in m else 'I-' + m.replace('INR', '_INR'))
                try:
                    k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval={tf}&limit=200", headers=headers, timeout=5)
                    if k_res.status_code != 200: 
                        time.sleep(1)
                        continue
                        
                    k_res = k_res.json()
                    if not isinstance(k_res, list) or len(k_res) < 200: continue
                    k_res.reverse() 
                    df = pd.DataFrame(k_res)
                    for col in ['close', 'high', 'low', 'volume', 'open']: df[col] = df[col].astype(float)
                    df = calculate_indicators(df)
                    last, prev = df.iloc[-1], df.iloc[-2]
                    
                    macd_bullish = last['macd'] > last['macd_signal']
                    macd_bearish = last['macd'] < last['macd_signal']
                    vol_spike = last['volume'] > (df['volume'].tail(20).mean() * 1.0)

                    signal = None
                    if last['close'] > last['ema200'] and last['close'] > last['vwap'] and last['rsi'] > 50 and macd_bullish and vol_spike and last['close'] > last['open']:
                        signal = "BUY"
                    elif last['close'] < last['ema200'] and last['close'] < last['vwap'] and last['rsi'] < 50 and macd_bearish and vol_spike and last['close'] < last['open']:
                        signal = "SELL"

                    if signal:
                        entry, risk = last['close'], last['atr'] * 2.0 
                        if signal == "BUY": 
                            sl, tp1, tp2, tp3 = entry - risk, entry + (risk * 2.0), entry + (risk * 3.0), entry + (risk * 4.0)
                        else: 
                            sl, tp1, tp2, tp3 = entry + risk, entry - (risk * 2.0), entry - (risk * 3.0), entry - (risk * 4.0)
                            
                        clean_sym = m.replace("B-", "").replace("I-", "").replace("_", "")
                        ema200_status = "🟢" if last['close'] > last['ema200'] else "🔴"
                        
                        text = (
                            f"#{clean_sym} {signal} (STRONG)\n\n"
                            f"Entry: {fmt(entry)}\n"
                            f"SL: {fmt(sl)}\n"
                            f"TP1: {fmt(tp1)}\n"
                            f"TP2: {fmt(tp2)}\n"
                            f"TP3: {fmt(tp3)}\n\n"
                            f"📊 RSI: {last['rsi']:.1f} | EMA200: {ema200_status}\n"
                            f"#{tf.upper()}TRADE"
                        )
                        
                        dcx_link = f"coindcx://trade/{clean_sym}" 
                        markup = {"inline_keyboard": [[{"text": f"📋 Copy '{clean_sym}'", "copy_text": {"text": clean_sym}}], [{"text": "📈 Open in CoinDCX App", "url": dcx_link}]]}
                        
                        chart_img = generate_chart_image(df, clean_sym, signal, entry, sl, tp1, tp2, tp3)
                        if chart_img: send_telegram_photo(chart_img, text, reply_markup=markup)
                        else: send_telegram(text, reply_markup=markup)
                        
                        signals_found += 1
                        time.sleep(1)
                        
                except: pass
                time.sleep(1.0) 
                
        send_telegram(f"✅ Manual Scan Completed for *{tf}*.\nFound {signals_found} strong signals.")
    except Exception as e:
        send_telegram("❌ Error during manual scan.")
    finally:
        MANUAL_SCAN_ACTIVE = False

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
                        text = update["callback_query"]["data"]
                        chat_id = update["callback_query"]["message"]["chat"]["id"]
                    else:
                        text = update.get("message", {}).get("text", "")
                        chat_id = update.get("message", {}).get("chat", {}).get("id")
                    
                    if str(chat_id) == str(TG_CHAT_ID):
                        # -------- MEGA MENU --------
                        if text in ["/start", "/menu"]:
                            markup = {"inline_keyboard": [
                                [{"text": "🌐 Dashboard", "url": "https://my-trading-bot-9se1.onrender.com"}, {"text": "🌍 Global", "callback_data": "/global"}],
                                [{"text": "🇮🇳 Indian Market Scan", "callback_data": "/scanindia"}],
                                [{"text": "📊 Nifty 50", "callback_data": "/nifty"}, {"text": "🏦 Bank Nifty", "callback_data": "/banknifty"}],
                                [{"text": "📈 Top Stocks", "callback_data": "/topstocks"}, {"text": "🪙 Crypto INR", "callback_data": "/cryptoinr"}],
                                [{"text": "🌡️ Sentiment", "callback_data": "/sentiment"}, {"text": "🚀 Pump/Dump", "callback_data": "/pump"}],
                                [{"text": "🏆 Gainers", "callback_data": "/top"}, {"text": "📉 Losers", "callback_data": "/bottom"}],
                                [{"text": "📈 Trades", "callback_data": "/trades"}, {"text": "📓 Journal", "callback_data": "/journal"}],
                                [{"text": "💼 Performance", "callback_data": "/performance"}, {"text": "📊 RSI Scanner", "callback_data": "/rsi"}],
                                [{"text": "🔊 Volume Top", "callback_data": "/volume"}, {"text": "🗑️ Clear Alerts", "callback_data": "/clearalerts"}],
                                [{"text": "🎯 Signal Scan", "callback_data": "help_signal"}, {"text": "⚙️ Scan TF", "callback_data": "help_scan"}],
                                [{"text": "🔍 Search", "callback_data": "help_search"}, {"text": "⚡ Price", "callback_data": "help_price"}],
                                [{"text": "🔬 Analysis", "callback_data": "help_analysis"}, {"text": "📉 Zones", "callback_data": "help_zones"}],
                                [{"text": "🔔 Alert", "callback_data": "help_alert"}, {"text": "⭐ Watchlist", "callback_data": "help_watch"}],
                                [{"text": "🗑️ Clear Watchlist", "callback_data": "/clearwatch"}]
                            ]}
                            send_telegram(f"👋 *Welcome to cripto_adda V38!*\nTF: *{SCAN_TIMEFRAME}* | Coins: *{len(watchlist) if watchlist else 'All'}*\n\nSelect an option:", reply_markup=markup)

                        # -------- INDIAN MARKET FEATURES --------
                        elif text == "/scanindia":
                            send_telegram("⏳ Scanning Indian Stocks (Nifty, Bank Nifty, Reliance, etc.)...")
                            Thread(target=scan_indian_market).start()
                            
                        elif text == "/nifty":
                            closes = get_yahoo_data("^NSEI")
                            if closes:
                                df = calculate_indicators(pd.DataFrame(closes, columns=['close']))
                                last = df.iloc[-1]
                                send_telegram(f"📊 *NIFTY 50*\nPrice: {fmt(last['close'])}\nRSI: {last['rsi']:.1f}\nTrend: {'🟢 BULLISH' if last['close'] > last['ema200'] else '🔴 BEARISH'}")
                            else: send_telegram("❌ Data unavailable.")

                        elif text == "/banknifty":
                            closes = get_yahoo_data("^NSEBANK")
                            if closes:
                                df = calculate_indicators(pd.DataFrame(closes, columns=['close']))
                                last = df.iloc[-1]
                                send_telegram(f"🏦 *BANK NIFTY*\nPrice: {fmt(last['close'])}\nRSI: {last['rsi']:.1f}\nTrend: {'🟢 BULLISH' if last['close'] > last['ema200'] else '🔴 BEARISH'}")
                            else: send_telegram("❌ Data unavailable.")

                        elif text == "/topstocks":
                            send_telegram("⏳ Fetching Top Indian Stocks...")
                            msg = "📈 *Top Indian Stocks (Live)*\n\n"
                            try:
                                for name, ticker in INDIAN_TICKERS.items():
                                    if "NIFTY" in name or "SENSEX" in name: continue
                                    closes = get_yahoo_data(ticker)
                                    if closes:
                                        df = calculate_indicators(pd.DataFrame(closes, columns=['close']))
                                        last = df.iloc[-1]
                                        msg += f"*{name}:* ₹{fmt(last['close'])} (RSI: {last['rsi']:.1f})\n"
                                send_telegram(msg)
                            except: send_telegram("❌ Error fetching stocks.")

                        elif text == "/cryptoinr":
                            send_telegram("⏳ Scanning Crypto INR pairs...")
                            run_manual_scan("15m") 

                        # -------- HELP GUIDES --------
                        elif text == "help_search": send_telegram("🔍 *Search Command:*\nType: `/search BTC`")
                        elif text == "help_price": send_telegram("⚡ *Price Command:*\nType: `/p BTC`")
                        elif text == "help_analysis": send_telegram("🔬 *Analysis Command:*\nType: `/analysis BTC`")
                        elif text == "help_zones": send_telegram("📉 *Zones Command:*\nType: `/zones BTC`")
                        elif text == "help_alert": send_telegram("🔔 *Alert Command:*\nType: `/alert BTC 65000`")
                        elif text == "help_signal": send_telegram("🎯 *Signal Scan:*\nRun manual strong scan:\n`/signal 15m`\n`/signal 1h`\n`/signal 4h`\n\nTo resume auto-scan:\n`/signal clear`")
                        elif text == "help_scan": send_telegram("⚙️ *Scan TF:*\nChange auto-scan TF: `/scan 15m` or `/scan 1h`")
                        elif text == "help_watch": send_telegram("⭐ *Watchlist:*\nAdd: `/watch BTC,ETH`\nClear: `/clearwatch`")

                        # -------- CRYPTO FEATURES --------
                        elif text.startswith("/signal"):
                            parts = text.split()
                            if len(parts) == 1:
                                send_telegram("⚠️ Use: `/signal 15m`, `/signal 1h`, `/signal 4h` or `/signal clear`")
                            elif parts[1].lower() == "clear":
                                SCAN_TIMEFRAME = "15m"
                                send_telegram("✅ *Auto-scan resumed on 15m timeframe.*")
                            elif parts[1] in ['15m', '1h', '4h']:
                                target_tf = parts[1]
                                send_telegram(f"⏳ Running *Strong* manual scan for *{target_tf}*... (Please wait 1-2 mins)")
                                Thread(target=run_manual_scan, args=(target_tf,)).start()
                            else:
                                send_telegram("⚠️ Invalid timeframe.")

                        elif text == "/global":
                            send_telegram("⏳ Fetching Global Markets...")
                            try:
                                symbols = {"GOLD": "GC=F", "SILVER": "SI=F", "OIL": "CL=F", "AMZN": "AMZN", "GOOGL": "GOOGL", "NVDA": "NVDA", "AAPL": "AAPL"}
                                msg = "🌍 *Global Markets*\n\n"
                                for name, sym in symbols.items():
                                    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", headers=headers, timeout=5).json()
                                    price = r['chart']['result'][0]['meta']['regularMarketPrice']
                                    prev = r['chart']['result'][0]['meta']['chartPreviousClose']
                                    chg = ((price - prev) / prev) * 100
                                    msg += f"{'🟢' if chg >= 0 else '🔴'} *{name}:* ${price:.2f} ({chg:+.2f}%)\n"
                                send_telegram(msg)
                            except: pass

                        elif text == "/sentiment":
                            try:
                                r = requests.get("https://api.alternative.me/fng/", timeout=5).json()
                                send_telegram(f"🌡️ *Market Sentiment*\n\n📊 Value: {r['data'][0]['value']}/100\n📝 Status: {r['data'][0]['value_classification']}")
                            except: send_telegram("❌ Error.")

                        elif text == "/pump":
                            send_telegram("⏳ Scanning for Pumps/Dumps...")
                            try:
                                data = get_ticker_data()
                                movers = [c for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market')) or 'INR' in str(c.get('market'))) and abs(float(c.get('change24hour', 0))) > 10]
                                movers = sorted(movers, key=lambda x: abs(float(x.get('change24hour', 0))), reverse=True)[:5]
                                if not movers: return send_telegram("🤷‍♂️ No major pumps/dumps right now.")
                                msg = "🚀 *Pump & Dump Alerts (Top 5)*\n\n"
                                for c in movers:
                                    clean = c['market'].replace("B-", "").replace("I-", "").replace("_", "")
                                    msg += f"{'🟢' if float(c['change24hour']) > 0 else '🔴'} *{clean}:* {float(c['change24hour']):+.2f}% | {fmt(c['last_price'])}\n"
                                send_telegram(msg)
                            except: pass

                        elif text == "/top" or text == "/bottom":
                            send_telegram("⏳ Fetching...")
                            try:
                                data = get_ticker_data()
                                valid = [{'m': str(c.get('market')), 'c': float(c.get('change24hour', 0)), 'p': float(c.get('last_price', 0))} for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market')) or 'INR' in str(c.get('market')))]
                                sorted_coins = sorted(valid, key=lambda x: x['c'], reverse=(text=="/top"))[:5]
                                msg = f"{'🏆 Top Gainers' if text=='/top' else '📉 Top Losers'}\n\n"
                                for i, c in enumerate(sorted_coins): msg += f"{i+1}. <b>{c['m'].replace('B-','').replace('I-','').replace('_','')}</b>: {c['c']:.2f}% | {fmt(c['p'])}\n"
                                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"})
                            except: pass

                        elif text == "/trades":
                            if not active_trades: send_telegram("💤 *No active trades.*")
                            else:
                                msg = "📈 *Active Trades:*\n\n"
                                for s, t in active_trades.items():
                                    msg += f"🪙 *{s.replace('B-','').replace('I-','').replace('_','')}* ({t['type']})\nEntry: {fmt(t['entry'])} | SL: {fmt(t['sl'])}\n\n"
                                send_telegram(msg)

                        elif text == "/journal":
                            j = get_journal()
                            if not j: send_telegram("📓 Empty.")
                            else:
                                msg = "📓 *Last 5 Trades:*\n\n"
                                for t in j[-5:]: msg += f"🪙 {t['coin']} ({t['type']}) - {t['result']}\n"
                                send_telegram(msg)

                        elif text == "/performance":
                            j = get_journal()
                            if not j: send_telegram("💼 *No past trades in journal.*")
                            else:
                                wins = sum(1 for t in j if t['result'] == 'WIN')
                                losses = sum(1 for t in j if t['result'] == 'LOSS')
                                total = wins + losses
                                wr = (wins/total*100) if total > 0 else 0
                                send_telegram(f"💼 *Trading Performance*\n\n🟢 Wins: {wins}\n🔴 Losses: {losses}\n📈 *Win Rate:* {wr:.1f}%\n📊 Total Trades: {total}")

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
                                msg = "📊 *RSI Scanner (Top 10 Coins)*\n\n"
                                msg += "📉 *Oversold (<30):*\n" + ("\n".join(oversold) if oversold else "None") + "\n\n"
                                msg += "📈 *Overbought (>70):*\n" + ("\n".join(overbought) if overbought else "None")
                                send_telegram(msg)
                            except: pass

                        elif text == "/volume":
                            send_telegram("⏳ Fetching Top Volume Coins...")
                            try:
                                data = get_ticker_data()
                                valid = [c for c in data if isinstance(c, dict) and 'USDT' in str(c.get('market'))]
                                valid = sorted(valid, key=lambda x: float(x.get('volume', 0)), reverse=True)[:5]
                                msg = "🔊 *Top 5 Volume Coins (USDT)*\n\n"
                                for i, c in enumerate(valid):
                                    clean = c['market'].replace('B-','').replace('_','')
                                    msg += f"{i+1}. *{clean}*\nVol: {float(c['volume']):,.0f} | Price: {fmt(c['last_price'])}\n\n"
                                send_telegram(msg)
                            except: pass

                        elif text == "/clearalerts":
                            price_alerts.clear()
                            send_telegram("🗑️ *All Alerts Cleared!*")

                        elif text == "/clearwatch":
                            watchlist.clear()
                            send_telegram("✅ Watchlist cleared.")

                        # -------- INPUT COMMANDS --------
                        elif text.startswith("/p "):
                            target = text.split()[1].upper()
                            data = get_ticker_data()
                            found = False
                            for c in data:
                                if isinstance(c, dict):
                                    m_clean = str(c.get('market')).replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "").replace("USDT", "").replace("INR", "")
                                    if m_clean == target:
                                        clean = str(c.get('market')).replace('B-','').replace('I-','').replace('_','')
                                        send_telegram(f"⚡ *{clean}*\n💰 Price: {fmt(c['last_price'])}\n📈 24h: {float(c['change24hour']):+.2f}%")
                                        found = True
                                        break
                            if not found: send_telegram("❌ Coin not found.")

                        elif text.startswith("/watch"):
                            parts = text.split()
                            if len(parts) > 1:
                                coins = parts[1].upper().split(',')
                                for coin in coins: watchlist.add(coin.strip())
                                send_telegram(f"✅ Added {', '.join(coins)} to Watchlist.")
                            else: send_telegram("⚠️ Use: `/watch BTC,ETH`")

                        elif text.startswith("/analysis"):
                            parts = text.split()
                            if len(parts) > 1:
                                target = parts[1].upper()
                                send_telegram(f"⏳ Analyzing *{target}*...")
                                try:
                                    c_sym = f"B-{target}_USDT"
                                    msg = f"🔬 *Analysis: {target}*\n\n"
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
                                        send_telegram(f"📉 *Zones ({target})*\n\nCurrent: {fmt(res[-1]['close'])}\n🟢 Support: {fmt(min(lows[-20:]))}\n🔴 Resistance: {fmt(max(highs[-20:]))}")
                                except: pass

                        elif text.startswith("/alert"):
                            parts = text.split()
                            if len(parts) == 3:
                                target, pr = parts[1].upper(), float(parts[2])
                                data = get_ticker_data()
                                for c in data:
                                    if isinstance(c, dict) and target in str(c.get('market')):
                                        price_alerts[str(c.get('market'))] = {'price': pr, 'type': 'above' if pr > float(c.get('last_price', 0)) else 'below'}
                                        send_telegram(f"✅ Alert set for {target} at {fmt(pr)}")
                                        break
                            else: send_telegram("⚠️ Use: `/alert BTC 65000`")

                        elif text.startswith("/scan"):
                            parts = text.split()
                            if len(parts) > 1 and parts[1] in ['15m','1h','4h']:
                                SCAN_TIMEFRAME = parts[1]
                                send_telegram(f"✅ Scanner TF: *{SCAN_TIMEFRAME}*")

                        elif text.startswith("/search"):
                            parts = text.split()
                            if len(parts) > 1:
                                target = parts[1].upper()
                                send_telegram(f"⏳ Searching *{target}*...")
                                try:
                                    data = get_ticker_data()
                                    for c in data:
                                        if isinstance(c, dict):
                                            m = str(c.get('market'))
                                            m_clean = m.replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "").replace("USDT", "").replace("INR", "")
                                            if m_clean == target:
                                                send_telegram(f"🔍 <b>{m.replace('B-','').replace('_','')}</b>\nPrice: {fmt(c['last_price'])}\nChange: {float(c['change24hour']):.2f}%", parse_mode="HTML")
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

    print("Starting Auto Market Scan...")
    try:
        data = get_ticker_data()
        if not data: return
        
        for c in data:
            if not isinstance(c, dict): continue
            m = str(c.get('market', ''))
            if ('USDT' in m or 'INR' in m) and float(c.get('volume', 0)) > 50000:
                clean_name = m.replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "")
                if watchlist and clean_name not in watchlist: continue
                
                c_sym = m if '_' in m else ('B-' + m.replace('USDT', '_USDT') if 'USDT' in m else 'I-' + m.replace('INR', '_INR'))
                try:
                    k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval={SCAN_TIMEFRAME}&limit=200", headers=headers, timeout=5)
                    if k_res.status_code != 200:
                        time.sleep(1)
                        continue
                        
                    k_res = k_res.json()
                    if not isinstance(k_res, list) or len(k_res) < 200: continue
                    k_res.reverse() 
                    df = pd.DataFrame(k_res)
                    for col in ['close', 'high', 'low', 'volume', 'open']: df[col] = df[col].astype(float)
                    df = calculate_indicators(df)
                    last, prev = df.iloc[-1], df.iloc[-2]
                    
                    macd_bullish = last['macd'] > last['macd_signal']
                    macd_bearish = last['macd'] < last['macd_signal']
                    vol_spike = last['volume'] > (df['volume'].tail(20).mean() * 1.0)

                    signal = None
                    if last['close'] > last['ema200'] and last['close'] > last['vwap'] and last['rsi'] > 50 and macd_bullish and vol_spike and last['close'] > last['open']:
                        signal = "BUY"
                    elif last['close'] < last['ema200'] and last['close'] < last['vwap'] and last['rsi'] < 50 and macd_bearish and vol_spike and last['close'] < last['open']:
                        signal = "SELL"

                    if signal:
                        entry, risk = last['close'], last['atr'] * 2.0 
                        if signal == "BUY": 
                            sl, tp1, tp2, tp3 = entry - risk, entry + (risk * 2.0), entry + (risk * 3.0), entry + (risk * 4.0)
                        else: 
                            sl, tp1, tp2, tp3 = entry + risk, entry - (risk * 2.0), entry - (risk * 3.0), entry - (risk * 4.0)
                            
                        active_trades[m] = {'type': signal, 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3, 'status': 'OPEN'}
                        save_active_trades()
                        
                        clean_sym = m.replace("B-", "").replace("I-", "").replace("_", "")
                        ema200_status = "🟢" if last['close'] > last['ema200'] else "🔴"
                        
                        text = (
                            f"#{clean_sym} {signal} (STRONG)\n\n"
                            f"Entry: {fmt(entry)}\n"
                            f"SL: {fmt(sl)}\n"
                            f"TP1: {fmt(tp1)}\n"
                            f"TP2: {fmt(tp2)}\n"
                            f"TP3: {fmt(tp3)}\n\n"
                            f"📊 RSI: {last['rsi']:.1f} | EMA200: {ema200_status}\n"
                            f"#{SCAN_TIMEFRAME.upper()}TRADE"
                        )
                        
                        dcx_link = f"coindcx://trade/{clean_sym}" 
                        markup = {"inline_keyboard": [[{"text": f"📋 Copy '{clean_sym}'", "copy_text": {"text": clean_sym}}], [{"text": "📈 Open in CoinDCX App", "url": dcx_link}]]}
                        
                        chart_img = generate_chart_image(df, clean_sym, signal, entry, sl, tp1, tp2, tp3)
                        if chart_img: send_telegram_photo(chart_img, text, reply_markup=markup)
                        else: send_telegram(text, reply_markup=markup)
                        
                        print(f"Signal Sent: {clean_sym} {signal}")
                        
                except: pass
                time.sleep(1.2)
    except: pass

if __name__ == "__main__":
    load_active_trades()
    keep_alive()
    Thread(target=monitor_trades).start()
    Thread(target=telegram_commands).start()
    while True:
        scan_market()
        time.sleep(300)
