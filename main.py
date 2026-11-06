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
SCAN_TIMEFRAME = "1h"

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

# ---------------- WEB DASHBOARD ----------------
@app.route('/')
def home():
    html = f"""
    <html><head><title>cripto_adda V22</title><meta http-equiv="refresh" content="30">
    <style>body{{background-color:#12161e;color:#e0e0e0;font-family:sans-serif;padding:20px;}}.container{{max-width:900px;margin:auto;}}.card{{background-color:#1a1e29;padding:15px;border-radius:8px;margin-bottom:15px;border:1px solid #2a2e39;}}.buy{{border-left:5px solid #00c864;}}.sell{{border-left:5px solid #ff3c3c;}}table{{width:100%;border-collapse:collapse;margin-top:10px;}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #2a2e39;}}</style></head>
    <body><div class="container"><h1>🤖 cripto_adda V22</h1>
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

def is_btc_bullish():
    try:
        res = requests.get("https://public.coindcx.com/market_data/candles?pair=B-BTC_USDT&interval=1h&limit=200", headers=headers, timeout=5).json()
        if isinstance(res, list) and len(res) >= 200:
            res.reverse()
            closes = [float(c['close']) for c in res]
            ema200 = pd.Series(closes).ewm(span=200, adjust=False).mean().iloc[-1]
            return closes[-1] > ema200
    except: pass
    return True

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
                
                if res_text: send_telegram(res_text)
        except: pass
        time.sleep(15)

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
                        # -------- COMPLETE ULTIMATE MENU --------
                        if text in ["/start", "/menu"]:
                            markup = {"inline_keyboard": [
                                [{"text": "🌐 Dashboard", "url": "https://my-trading-bot-9se1.onrender.com"}, {"text": "🌍 Global", "callback_data": "/global"}],
                                [{"text": "🌡️ Sentiment", "callback_data": "/sentiment"}, {"text": "🚀 Pump/Dump", "callback_data": "/pump"}],
                                [{"text": "🏆 Gainers", "callback_data": "/top"}, {"text": "📉 Losers", "callback_data": "/bottom"}],
                                [{"text": "📈 Active Trades", "callback_data": "/trades"}, {"text": "📓 Journal", "callback_data": "/journal"}],
                                [{"text": "💼 Performance", "callback_data": "/performance"}, {"text": "📊 RSI Scanner", "callback_data": "/rsi"}],
                                [{"text": "🔊 Volume Top", "callback_data": "/volume"}, {"text": "🔍 Search", "callback_data": "help_search"}],
                                [{"text": "⚡ Price", "callback_data": "help_price"}, {"text": "🔬 Analysis", "callback_data": "help_analysis"}],
                                [{"text": "📉 Zones", "callback_data": "help_zones"}, {"text": "🔔 Alert", "callback_data": "help_alert"}],
                                [{"text": "🗑️ Clear Alerts", "callback_data": "/clearalerts"}, {"text": "⚙️ Scan TF", "callback_data": "help_scan"}],
                                [{"text": "⭐ Watchlist", "callback_data": "help_watch"}]
                            ]}
                            send_telegram(f"👋 *Welcome to cripto_adda V22!*\nTF: *{SCAN_TIMEFRAME}* | Coins: *{len(watchlist) if watchlist else 'All'}*\n\nSelect an option:", reply_markup=markup)

                        # -------- HELP GUIDES (For inputs) --------
                        elif text == "help_search": send_telegram("🔍 *Search Command:*\nType: `/search BTC`")
                        elif text == "help_price": send_telegram("⚡ *Price Command:*\nType: `/p BTC` (Short & Fast)")
                        elif text == "help_analysis": send_telegram("🔬 *Analysis Command:*\nType: `/analysis BTC`")
                        elif text == "help_zones": send_telegram("📉 *Zones Command:*\nType: `/zones BTC`")
                        elif text == "help_alert": send_telegram("🔔 *Alert Command:*\nType: `/alert BTC 65000`")
                        elif text == "help_scan": send_telegram("⚙️ *Scan Command:*\nType: `/scan 15m` or `/scan 1h`")
                        elif text == "help_watch": send_telegram("⭐ *Watchlist:*\nAdd: `/watch BTC,ETH`\nClear: `/clearwatch`")

                        # -------- DIRECT FEATURES --------
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
                            except: send_telegram("❌ Error scanning RSI.")

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

                        elif text.startswith("/clearwatch"):
                            watchlist.clear()
                            send_telegram("✅ Watchlist cleared.")
                            
        except: pass
        time.sleep(2)

# ---------------- INDICATORS & SCANNER ----------------
def calculate_indicators(df):
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    df['tr'] = pd.concat([df['high'] - df['low'], abs(df['high'] - df['close'].shift()), abs(df['low'] - df['close'].shift())], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(window=14).mean()
    df['vwap'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
    return df

def scan_market():
    try:
        data = get_ticker_data()
        if not data: return
        btc_bull = is_btc_bullish()
        for c in data:
            if not isinstance(c, dict): continue
            m = str(c.get('market', ''))
            if ('USDT' in m or 'INR' in m) and float(c.get('volume', 0)) > 50000:
                clean_name = m.replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "")
                if watchlist and clean_name not in watchlist: continue
                
                c_sym = m if '_' in m else ('B-' + m.replace('USDT', '_USDT') if 'USDT' in m else 'I-' + m.replace('INR', '_INR'))
                try:
                    k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval={SCAN_TIMEFRAME}&limit=200", headers=headers, timeout=5).json()
                    if not isinstance(k_res, list) or len(k_res) < 200: continue
                    k_res.reverse() 
                    df = pd.DataFrame(k_res)
                    for col in ['close', 'high', 'low', 'volume', 'open']: df[col] = df[col].astype(float)
                    df = calculate_indicators(df)
                    last, prev = df.iloc[-1], df.iloc[-2]
                    
                    vol_spike = last['volume'] > (df['volume'].tail(20).mean() * 1.5)
                    recent_low = df['low'].iloc[-30:-1].min()
                    recent_high = df['high'].iloc[-30:-1].max()
                    sweep_low = (last['low'] < recent_low) and (last['close'] > recent_low)
                    sweep_high = (last['high'] > recent_high) and (last['close'] < recent_high)

                    signal = None
                    if vol_spike and btc_bull and last['close'] > last['ema200'] and sweep_low and last['close'] > last['open'] and last['close'] > last['vwap'] and last['rsi'] > 50:
                        signal = "BUY"
                    elif vol_spike and not btc_bull and last['close'] < last['ema200'] and sweep_high and last['close'] < last['open'] and last['close'] < last['vwap'] and last['rsi'] < 50:
                        signal = "SELL"

                    if signal:
                        entry, risk = last['close'], last['atr'] * 3.0 
                        if signal == "BUY": sl, tp1 = entry - risk, entry + (risk * 2.0)
                        else: sl, tp1 = entry + risk, entry - (risk * 2.0)
                        active_trades[m] = {'type': signal, 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp1*1.5, 'tp3': tp1*2, 'status': 'OPEN'}
                        save_active_trades()
                        
                        clean_sym = m.replace("B-", "").replace("I-", "").replace("_", "")
                        text = f"#{clean_sym} {signal} FROM {fmt(entry)}\n\nSL {fmt(sl)}\n\nTARGET {fmt(tp1)}\n\n#{SCAN_TIMEFRAME.upper()}TRADE"
                        markup = {"inline_keyboard": [[{"text": f"📋 Copy '{clean_sym}'", "copy_text": {"text": clean_sym}}], [{"text": "🌐 Chart", "url": f"https://coindcx.com/trade/{clean_sym}"}]]}
                        send_telegram(text, reply_markup=markup)
                except: pass
                time.sleep(0.5)
    except: pass

if __name__ == "__main__":
    load_active_trades()
    keep_alive()
    Thread(target=monitor_trades).start()
    Thread(target=telegram_commands).start()
    while True:
        scan_market()
        time.sleep(300)
