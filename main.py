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

# ---------------- PERMANENT MEMORY (FILE SAVE) ----------------
def load_active_trades():
    global active_trades
    try:
        if os.path.exists("active_trades.json"):
            with open("active_trades.json", "r") as f:
                active_trades = json.load(f)
            print(f"Loaded {len(active_trades)} active trades from memory.")
    except Exception as e:
        print("Error loading trades:", e)

def save_active_trades():
    try:
        with open("active_trades.json", "w") as f:
            json.dump(active_trades, f)
    except Exception as e:
        print("Error saving trades:", e)

# ---------------- WEB DASHBOARD ----------------
@app.route('/')
def home():
    html = """
    <html>
    <head>
        <title>cripto_adda Dashboard</title>
        <meta http-equiv="refresh" content="30">
        <style>
            body { background-color: #12161e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; padding: 20px; }
            h1 { color: #4a9eff; }
            .container { max-width: 900px; margin: auto; }
            .card { background-color: #1a1e29; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #2a2e39; }
            .buy { border-left: 5px solid #00c864; }
            .sell { border-left: 5px solid #ff3c3c; }
            .status { color: #00c864; font-weight: bold; }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; }
            th, td { text-align: left; padding: 8px; border-bottom: 1px solid #2a2e39; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 cripto_adda Bot</h1>
            <p>Status: <span class="status">● Running 24/7</span> | Scan TF: """ + SCAN_TIMEFRAME + """ | Watchlist: """ + (", ".join(watchlist) if watchlist else "All Coins") + """</p>
            <h2>📈 Active Trades</h2>
    """
    if not active_trades:
        html += "<div class='card'>No active trades right now. Scanning market...</div>"
    else:
        for sym, t in active_trades.items():
            clean = sym.replace("B-", "").replace("I-", "").replace("_", "")
            cls = "buy" if t['type'] == "BUY" else "sell"
            html += f"""
            <div class='card {cls}'>
                <h3>{clean} ({t['type']})</h3>
                <table>
                    <tr><th>Entry</th><th>SL</th><th>TP1</th><th>TP2</th><th>TP3</th></tr>
                    <tr><td>{t['entry']:.4f}</td><td>{t['sl']:.4f}</td><td>{t['tp1']:.4f}</td><td>{t['tp2']:.4f}</td><td>{t['tp3']:.4f}</td></tr>
                </table>
                <p style='color:#888; font-size:12px;'>Status: {t['status']}</p>
            </div>
            """
    html += "</div></body></html>"
    return html

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

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

# ---------------- JOURNAL & SAVE ----------------
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

# ---------------- ORDER BOOK CHECK ----------------
def check_order_book(sym):
    try:
        res = requests.get(f"https://api.coindcx.com/exchange/v1/orders/orderbook?pair={sym}", timeout=5).json()
        bids = sum([float(b[1]) for b in res['bids'][:20]])
        asks = sum([float(a[1]) for a in res['asks'][:20]])
        if asks > (bids * 1.5): return False 
        return True
    except: return True 

# ---------------- MONITOR TRADES ----------------
def monitor_trades():
    while True:
        try:
            tickers = get_ticker_data()
            if not tickers: 
                time.sleep(10)
                continue
            price_map = {t['market']: float(t['last_price']) for t in tickers if isinstance(t, dict)}
            
            for sym, alert_data in list(price_alerts.items()):
                if sym in price_map:
                    curr_price = price_map[sym]
                    target = alert_data['price']
                    alert_type = alert_data['type']
                    if (alert_type == 'above' and curr_price >= target) or (alert_type == 'below' and curr_price <= target):
                        clean = sym.replace("B-", "").replace("I-", "").replace("_", "")
                        send_telegram(f"🚨 *PRICE ALERT!*\n\n🪙 *Coin:* {clean}\n💰 *Target:* {target}\n📈 *Current:* {curr_price}")
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
                        res_text = f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {curr_price:.4f}"
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'BUY', 'result': 'LOSS'})
                        del active_trades[sym]
                        save_active_trades()
                    elif curr_price >= tp3:
                        res_text = f"🚀 *{clean_sym} Hit TP3!*\nTrade Complete."
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'BUY', 'result': 'WIN'})
                        del active_trades[sym]
                        save_active_trades()
                    elif curr_price >= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1 
                        trade['status'] = "TP2_HIT"
                        res_text = f"🔥 *{clean_sym} Hit TP2*\nSL moved to TP1."
                        save_active_trades()
                    elif curr_price >= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry 
                        trade['status'] = "TP1_HIT"
                        res_text = f"✅ *{clean_sym} Hit TP1*\nSL moved to Entry."
                        save_active_trades()
                        
                    if trade.get('status') == "TP2_HIT" and curr_price <= (trade['highest'] * 0.995):
                        res_text = f"🏃‍♂️ *{clean_sym} Trailing TP Hit!*"
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'BUY', 'result': 'WIN'})
                        del active_trades[sym]
                        save_active_trades()

                elif signal == "SELL":
                    if curr_price < trade['lowest']: trade['lowest'] = curr_price
                    if curr_price >= sl:
                        res_text = f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {curr_price:.4f}"
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'SELL', 'result': 'LOSS'})
                        del active_trades[sym]
                        save_active_trades()
                    elif curr_price <= tp3:
                        res_text = f"🚀 *{clean_sym} Hit TP3!*\nTrade Complete."
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'SELL', 'result': 'WIN'})
                        del active_trades[sym]
                        save_active_trades()
                    elif curr_price <= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1 
                        trade['status'] = "TP2_HIT"
                        res_text = f"🔥 *{clean_sym} Hit TP2*\nSL moved to TP1."
                        save_active_trades()
                    elif curr_price <= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry 
                        trade['status'] = "TP1_HIT"
                        res_text = f"✅ *{clean_sym} Hit TP1*\nSL moved to Entry."
                        save_active_trades()
                        
                    if trade.get('status') == "TP2_HIT" and curr_price >= (trade['lowest'] * 1.005):
                        res_text = f"🏃‍♂️ *{clean_sym} Trailing TP Hit!*"
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'SELL', 'result': 'WIN'})
                        del active_trades[sym]
                        save_active_trades()
                
                if res_text: send_telegram(res_text)
        except: pass
        time.sleep(15)

# ---------------- BACKTEST ----------------
def run_backtest(coin, tf):
    send_telegram(f"⏳ Backtesting *{coin}* on {tf}...")
    try:
        c_sym = f"B-{coin}_USDT"
        res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval={tf}&limit=500", headers=headers, timeout=10).json()
        if not isinstance(res, list) or len(res) < 200: return send_telegram("❌ Not enough data.")
        res.reverse()
        df = pd.DataFrame(res)
        for col in ['close', 'high', 'low', 'volume', 'open']: df[col] = df[col].astype(float)
        df = calculate_indicators(df)
        
        wins, losses = 0, 0
        for i in range(200, len(df)-10):
            row, prev = df.iloc[i], df.iloc[i-1]
            
            # Retest logic
            prev_ema50 = prev['ema50']
            pullback_buy = abs(prev['low'] - prev_ema50) / prev_ema50 < 0.005
            bounce_buy = (row['close'] > row['open']) and (row['close'] > prev['high'])
            
            pullback_sell = abs(prev['high'] - prev_ema50) / prev_ema50 < 0.005
            rejection_sell = (row['close'] < row['open']) and (row['close'] < prev['low'])
            
            vol_spike = row['volume'] > (df['volume'].iloc[i-20:i].mean() * 1.5)
            
            if row['adx'] > 25 and vol_spike:
                if row['ema50'] > row['ema200'] and pullback_buy and bounce_buy and row['close'] > row['vwap'] and row['rsi'] > 50:
                    signal = "BUY"
                elif row['ema50'] < row['ema200'] and pullback_sell and rejection_sell and row['close'] < row['vwap'] and row['rsi'] < 50:
                    signal = "SELL"
                else:
                    signal = None
                    
                if signal:
                    entry, risk = row['close'], row['atr'] * 2.5
                    outcome = "OPEN"
                    for j in range(i+1, min(i+11, len(df))):
                        if signal == "BUY":
                            if df.iloc[j]['low'] <= entry - risk: outcome = "LOSS"; break
                            if df.iloc[j]['high'] >= entry + (risk * 1.5): outcome = "WIN"; break
                        else:
                            if df.iloc[j]['high'] >= entry + risk: outcome = "LOSS"; break
                            if df.iloc[j]['low'] <= entry - (risk * 1.5): outcome = "WIN"; break
                    if outcome == "WIN": wins += 1
                    elif outcome == "LOSS": losses += 1
        total = wins + losses
        wr = (wins/total*100) if total > 0 else 0
        send_telegram(f"📊 *Backtest ({coin} {tf})*\n🟢 Wins: {wins} | 🔴 Losses: {losses}\n📈 *Win Rate:* {wr:.1f}%")
    except: send_telegram("❌ Backtest failed.")

# ---------------- TELEGRAM COMMANDS ----------------
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
                    text = update.get("message", {}).get("text", "")
                    chat_id = update.get("message", {}).get("chat", {}).get("id")
                    
                    if str(chat_id) == str(TG_CHAT_ID):
                        if text in ["/start", "/menu"]:
                            markup = {"inline_keyboard": [
                                [{"text": "🌐 Web Dashboard", "url": "https://my-trading-bot-9se1.onrender.com"}],
                                [{"text": "📊 Status", "callback_data": "/status"}, {"text": "🏆 Top Coins", "callback_data": "/top"}],
                                [{"text": "📉 Losers", "callback_data": "/bottom"}, {"text": "📓 Journal", "callback_data": "/journal"}]
                            ]}
                            send_telegram(f"👋 *Welcome to cripto_adda!*\nTF: *{SCAN_TIMEFRAME}* | Watch: *{len(watchlist)}*", reply_markup=markup)
                        
                        elif text == "/status":
                            send_telegram(f"🤖 *cripto_adda Running*\nTF: {SCAN_TIMEFRAME}\nTrades: {len(active_trades)}\nAlerts: {len(price_alerts)}")
                        
                        elif text == "/journal":
                            j = get_journal()
                            if not j: send_telegram("📓 Empty.")
                            else:
                                msg = "📓 *Last 5 Trades:*\n\n"
                                for t in j[-5:]: msg += f"🪙 {t['coin']} ({t['type']}) - {t['result']}\n"
                                send_telegram(msg)
                        
                        elif text == "/top" or text == "/bottom":
                            send_telegram("⏳ Fetching...")
                            try:
                                data = get_ticker_data()
                                valid = [{'m': str(c.get('market')), 'c': float(c.get('change24hour', 0)), 'p': float(c.get('last_price', 0))} for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market')))]
                                is_top = text == "/top"
                                sorted_coins = sorted(valid, key=lambda x: x['c'], reverse=is_top)[:5]
                                msg = f"{'🏆 Top Gainers' if is_top else '📉 Top Losers'}\n\n"
                                for i, c in enumerate(sorted_coins): msg += f"{i+1}. <b>{c['m'].replace('B-','').replace('_','')}</b>: {c['c']:.2f}% | {c['p']}\n"
                                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"})
                            except: send_telegram("❌ API Error.")

                        elif text.startswith("/search"):
                            parts = text.split()
                            if len(parts) > 1:
                                raw_target = parts[1].upper()
                                name_map = {"BITCOIN": "BTC", "ETHEREUM": "ETH", "SOLANA": "SOL", "RIPPLE": "XRP", "CARDANO": "ADA", "DOGECOIN": "DOGE"}
                                target = name_map.get(raw_target, raw_target)
                                send_telegram(f"⏳ Searching *{target}*...")
                                try:
                                    data = get_ticker_data()
                                    matched_coin = None
                                    for c in data:
                                        if isinstance(c, dict):
                                            m = str(c.get('market'))
                                            m_clean = m.replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "").replace("USDT", "").replace("INR", "")
                                            if m_clean == target:
                                                matched_coin = c
                                                if 'USDT' in m: break
                                    
                                    if not matched_coin:
                                        send_telegram(f"❌ {raw_target} not found.")
                                        continue
                                    
                                    m_sym = matched_coin['market']
                                    price = float(matched_coin.get('last_price', 0))
                                    change_24h = float(matched_coin.get('change24hour', 0))
                                    vol_24h = float(matched_coin.get('volume', 0))
                                    
                                    c_sym = m_sym
                                    if '_' not in c_sym and 'USDT' in c_sym: c_sym = 'B-' + c_sym.replace('USDT', '_USDT')
                                    elif '_' not in c_sym and 'INR' in c_sym: c_sym = 'I-' + c_sym.replace('INR', '_INR')
                                    
                                    h1_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval=1h&limit=100", headers=headers, timeout=5).json()
                                    trend = "NEUTRAL 🟡"
                                    if isinstance(h1_res, list) and len(h1_res) >= 50:
                                        h1_res.reverse()
                                        closes = [float(c['close']) for c in h1_res]
                                        ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().iloc[-1]
                                        trend = "BULLISH 🟢" if price > ema50 else "BEARISH 🔴"

                                    clean_sym = m_sym.replace("B-", "").replace("I-", "").replace("_", "")
                                    msg = (f"🔍 <b>{clean_sym} Details</b>\n\n"
                                           f"💰 <b>Price:</b> {price}\n"
                                           f"📈 <b>24h Change:</b> {change_24h:.2f}%\n"
                                           f"📊 <b>24h Volume:</b> {vol_24h:,.0f}\n"
                                           f"🚀 <b>1H Trend:</b> {trend}\n"
                                           f"🔗 <a href='https://coindcx.com/trade/{clean_sym}'>Open Chart</a>")
                                    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True})
                                except: send_telegram(f"❌ Error")
                            else: send_telegram("⚠️ Format: `/search BTC`")

                        elif text.startswith("/zones"):
                            parts = text.split()
                            if len(parts) > 1:
                                target = parts[1].upper()
                                send_telegram(f"⏳ Calculating Zones for *{target}*...")
                                try:
                                    c_sym = f"B-{target}_USDT"
                                    res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval=15m&limit=100", headers=headers, timeout=5).json()
                                    if isinstance(res, list) and len(res) >= 50:
                                        res.reverse()
                                        highs = [float(c['high']) for c in res]
                                        lows = [float(c['low']) for c in res]
                                        current = float(res[-1]['close'])
                                        support = min(lows[-20:])
                                        resistance = max(highs[-20:])
                                        msg = (f"📉 *Zones ({target})*\n\n💰 Current: {current:.4f}\n🟢 *Support:* {support:.4f}\n🔴 *Resistance:* {resistance:.4f}")
                                        send_telegram(msg)
                                    else: send_telegram("❌ Data not found.")
                                except: send_telegram("❌ Error.")
                            else: send_telegram("⚠️ Use: `/zones BTC`")

                        elif text.startswith("/alert"):
                            parts = text.split()
                            if len(parts) == 3:
                                target, pr = parts[1].upper(), float(parts[2])
                                data = get_ticker_data()
                                for c in data:
                                    if isinstance(c, dict) and target in str(c.get('market')):
                                        price_alerts[str(c.get('market'))] = {'price': pr, 'type': 'above' if pr > float(c.get('last_price', 0)) else 'below'}
                                        send_telegram(f"✅ Alert set for {target} at {pr}")
                                        break
                            else: send_telegram("⚠️ Use: `/alert BTC 65000`")

                        elif text.startswith("/backtest"):
                            parts = text.split()
                            if len(parts) >= 2:
                                target_coin = parts[1].upper()
                                tf = parts[2] if len(parts) >= 3 else "15m"
                                Thread(target=run_backtest, args=(target_coin, tf)).start()
                            else: send_telegram("⚠️ Use: `/backtest BTC` or `/backtest BTC 1h`")

                        elif text.startswith("/scan"):
                            parts = text.split()
                            if len(parts) > 1 and parts[1] in ['1m','5m','15m','1h','4h']:
                                SCAN_TIMEFRAME = parts[1]
                                send_telegram(f"✅ Scanner TF: *{SCAN_TIMEFRAME}*")
                            else: send_telegram("⚠️ Use: `/scan 1h`")

                        elif text.startswith("/watch"):
                            parts = text.split()
                            if len(parts) > 1:
                                watchlist.add(parts[1].upper())
                                send_telegram(f"✅ Added {parts[1].upper()} to Watchlist.")
                            else: send_telegram("⚠️ Use: `/watch BTC`")
                        
                        elif text.startswith("/clearwatch"):
                            watchlist.clear()
                            send_telegram("✅ Watchlist cleared. Scanning all coins.")
        except: pass
        time.sleep(2)

# ---------------- INDICATORS ----------------
def calculate_indicators(df):
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    
    df['up_move'] = df['high'] - df['high'].shift(1)
    df['down_move'] = df['low'].shift(1) - df['low']
    df['plus_dm'] = df['up_move'].where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), 0.0)
    df['minus_dm'] = df['down_move'].where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), 0.0)
    df['tr'] = pd.concat([df['high'] - df['low'], abs(df['high'] - df['close'].shift()), abs(df['low'] - df['close'].shift())], axis=1).max(axis=1)
    df['plus_di'] = 100 * (df['plus_dm'].ewm(alpha=1/14, adjust=False).mean() / df['tr'].ewm(alpha=1/14, adjust=False).mean())
    df['minus_di'] = 100 * (df['minus_dm'].ewm(alpha=1/14, adjust=False).mean() / df['tr'].ewm(alpha=1/14, adjust=False).mean())
    df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
    df['adx'] = df['dx'].ewm(alpha=1/14, adjust=False).mean()
    
    df['atr'] = df['tr'].rolling(window=14).mean()
    df['vwap'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
    return df

# ---------------- SCANNER ----------------
def scan_market():
    global SCAN_TIMEFRAME
    try:
        data = get_ticker_data()
        if not data: return
        
        all_coins = []
        for c in data:
            if isinstance(c, dict) and ('USDT' in str(c.get('market', '')) or 'INR' in str(c.get('market', ''))):
                if float(c.get('volume', 0)) > 50000:
                    clean_name = str(c.get('market')).replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "")
                    if not watchlist or clean_name in watchlist:
                        all_coins.append(str(c.get('market')))
        
        for sym in all_coins:
            if sym in active_trades: continue
            if sym in last_signal_time and (time.time() - last_signal_time[sym] < 4 * 3600): continue
            try:
                c_sym = sym
                if '_' not in c_sym and 'USDT' in c_sym: c_sym = 'B-' + c_sym.replace('USDT', '_USDT')
                elif '_' not in c_sym and 'INR' in c_sym: c_sym = 'I-' + c_sym.replace('INR', '_INR')

                k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval={SCAN_TIMEFRAME}&limit=200", headers=headers, timeout=5).json()
                if not isinstance(k_res, list) or len(k_res) < 200: continue
                k_res.reverse() 
                df = pd.DataFrame(k_res)
                for col in ['close', 'high', 'low', 'volume', 'open']: df[col] = df[col].astype(float)
                df = calculate_indicators(df)
                
                last, prev = df.iloc[-1], df.iloc[-2]
                current_price = last['close']
                ema50, ema200, rsi, atr, adx, vwap = last['ema50'], last['ema200'], last['rsi'], last['atr'], last['adx'], last['vwap']
                
                vol_spike = last['volume'] > (df['volume'].tail(20).mean() * 1.5)
                
                # --- RETEST LOGIC (Strong Signal) ---
                prev_ema50 = prev['ema50']
                # BUY: Price > EMA200 (Trend Up), Prev Candle touched EMA50 (Pullback), Current is Bullish (Bounce)
                pullback_buy = abs(prev['low'] - prev_ema50) / prev_ema50 < 0.005 # Within 0.5% of EMA50
                bounce_buy = (current_price > last['open']) and (current_price > prev['high'])
                
                # SELL: Price < EMA200 (Trend Down), Prev Candle touched EMA50 (Pullback), Current is Bearish (Rejection)
                pullback_sell = abs(prev['high'] - prev_ema50) / prev_ema50 < 0.005
                rejection_sell = (current_price < last['open']) and (current_price < prev['low'])

                signal = None
                if adx > 25 and vol_spike:
                    if ema50 > ema200 and pullback_buy and bounce_buy and current_price > vwap and rsi > 50:
                        if check_order_book(c_sym): signal = "BUY"
                    elif ema50 < ema200 and pullback_sell and rejection_sell and current_price < vwap and rsi < 50:
                        if check_order_book(c_sym): signal = "SELL"

                if signal:
                    entry, risk = current_price, atr * 2.5 
                    if signal == "BUY": sl, tp1, tp2, tp3 = entry - risk, entry + (risk * 1.5), entry + (risk * 3.0), entry + (risk * 4.5)
                    else: sl, tp1, tp2, tp3 = entry + risk, entry - (risk * 1.5), entry - (risk * 3.0), entry - (risk * 4.5)

                    active_trades[sym] = {'type': signal, 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3, 'status': 'OPEN'}
                    last_signal_time[sym] = time.time() 
                    save_active_trades() # Save to permanent memory
                    
                    clean_sym = sym.replace("B-", "").replace("I-", "").replace("_", "")
                    dcx_link = f"https://coindcx.com/trade/{clean_sym}"
                    
                    text = (f"🎯 *cripto_adda {signal} (RETEST)*\n\n🪙 *Coin:* {clean_sym}\n"
                            f"💰 *Entry:* {entry:.4f}\n🛑 *SL:* {sl:.4f}\n"
                            f"🎯 *TP1:* {tp1:.4f}\n🎯 *TP2:* {tp2:.4f}\n🎯 *TP3:* {tp3:.4f}\n"
                            f"📊 *ADX:* {adx:.1f} | *VWAP:* ✅ | *Whale:* ✅\n"
                            f"⏱️ *TF:* {SCAN_TIMEFRAME}")
                    
                    markup = {"inline_keyboard": [[{"text": f"📋 Copy '{clean_sym}'", "copy_text": {"text": clean_sym}}], [{"text": "🌐 Open Web Chart", "url": dcx_link}]]}
                    send_telegram(text, reply_markup=markup)
            except: pass
            time.sleep(0.5)
    except: pass

if __name__ == "__main__":
    load_active_trades() # Load trades on start
    keep_alive()
    Thread(target=monitor_trades).start()
    Thread(target=telegram_commands).start()
    while True:
        scan_market()
        time.sleep(300)
