import os
import requests
import time
import pandas as pd
from flask import Flask
from threading import Thread
import datetime
import json
import queue

# ================= TOKEN RENDER SE AAYEGA =================
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = "762295473"
# ============================================================

app = Flask('')
active_trades = {}
watchlist = set()
SCAN_TIMEFRAME = "15m" 
signal_queue = queue.Queue()

def fmt(p):
    try:
        p = float(p)
        if p >= 1000: return f"{p:.2f}"
        if p >= 10: return f"{p:.3f}"
        if p >= 1: return f"{p:.4f}"
        if p >= 0.01: return f"{p:.5f}"
        return f"{p:.6f}"
    except: return str(p)

# ---------------- MEMORY ----------------
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
    except: pass
    return None

# ---------------- WEB DASHBOARD ----------------
@app.route('/')
def home():
    return "<h1>cripto_adda V47 is Running 24/7!</h1><p>Auto Signals are active on Telegram.</p>"

def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive(): Thread(target=run).start()

# ---------------- TELEGRAM HELPERS ----------------
def send_telegram(text, reply_markup=None):
    if not TG_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup: payload["reply_markup"] = reply_markup
    try: requests.post(url, json=payload)
    except: pass

def send_telegram_photo(photo_bytes, caption, reply_markup=None):
    if not TG_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    files = {'photo': ('chart.png', photo_bytes, 'image/png')}
    data = {"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
    if reply_markup: data["reply_markup"] = json.dumps(reply_markup)
    try: requests.post(url, files=files, data=data)
    except: pass

headers = {'User-Agent': 'Mozilla/5.0'}

# ---------------- DATA FETCHERS ----------------
def get_ticker_data():
    try:
        res = requests.get("https://api.coindcx.com/exchange/ticker", headers=headers, timeout=10)
        if res.status_code == 200: return res.json()
    except: pass
    return []

def get_klines(market, interval="15m", limit=200):
    try:
        c_sym = market if '_' in market else ('B-' + market.replace('USDT', '_USDT') if 'USDT' in market else 'I-' + market.replace('INR', '_INR'))
        url = f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval={interval}&limit={limit}"
        res = requests.get(url, headers=headers, timeout=10).json()
        if isinstance(res, list):
            res.reverse()
            return res
    except: pass
    return []

# ---------------- INDICATORS ----------------
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
    return df

# ---------------- SCANNER LOGIC ----------------
def scan_coin(m):
    try:
        if m in active_trades: return None
        
        res = get_klines(m, "15m", 200)
        if not isinstance(res, list) or len(res) < 200: return None
        
        df = pd.DataFrame(res)
        for col in ['close', 'high', 'low', 'volume', 'open']: df[col] = df[col].astype(float)
        df = calculate_indicators(df)
        
        last, prev = df.iloc[-1], df.iloc[-2]
        
        macd_bullish = last['macd'] > last['macd_signal']
        macd_bearish = last['macd'] < last['macd_signal']
        vol_spike = last['volume'] > (df['volume'].tail(20).mean() * 1.2)
        
        signal = None
        if last['close'] > last['ema200'] and last['rsi'] > 50 and macd_bullish and vol_spike and last['close'] > last['open']:
            signal = "BUY"
        elif last['close'] < last['ema200'] and last['rsi'] < 50 and macd_bearish and vol_spike and last['close'] < last['open']:
            signal = "SELL"
            
        if signal:
            entry, risk = last['close'], last['atr'] * 2.0 
            if signal == "BUY": 
                sl, tp1, tp2, tp3 = entry - risk, entry + (risk * 2.0), entry + (risk * 3.0), entry + (risk * 4.0)
            else: 
                sl, tp1, tp2, tp3 = entry + risk, entry - (risk * 2.0), entry - (risk * 3.0), entry - (risk * 4.0)
                
            clean_sym = m.replace("B-", "").replace("I-", "").replace("_", "")
            
            return {
                'market': m, 'clean': clean_sym, 'signal': signal, 
                'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3,
                'rsi': last['rsi'], 'df': df
            }
    except: pass
    return None

# ---------------- BACKGROUND SCANNER ----------------
def background_scanner():
    print("Auto Scanner Started.")
    while True:
        try:
            data = get_ticker_data()
            if data:
                valid_coins = [c for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market', ''))) and float(c.get('volume', 0)) > 100000]
                valid_coins.sort(key=lambda x: float(x.get('volume', 0)), reverse=True)
                valid_coins = valid_coins[:100] # Scan Top 100 Volume coins for speed
                
                found = 0
                for c in valid_coins:
                    res = scan_coin(c['market'])
                    if res:
                        signal_queue.put(res)
                        found += 1
                    time.sleep(1) # Delay to avoid API ban
                if found > 0: print(f"Queued {found} signals.")
        except Exception as e:
            print("Scanner Error:", e)
        
        time.sleep(300) # Scan every 5 mins

# ---------------- SIGNAL SENDER ----------------
def signal_sender():
    while True:
        try:
            if not signal_queue.empty():
                res = signal_queue.get()
                clean_sym = res['clean']
                
                # 4-Hour cooldown logic
                if res['market'] in active_trades: continue
                
                text = (
                    f"<b>#{clean_sym} {res['signal']} (AUTO)</b>\n\n"
                    f"Entry: {fmt(res['entry'])}\n"
                    f"SL: {fmt(res['sl'])}\n"
                    f"TP1: {fmt(res['tp1'])}\n"
                    f"TP2: {fmt(res['tp2'])}\n"
                    f"TP3: {fmt(res['tp3'])}\n\n"
                    f"📊 RSI: {res['rsi']:.1f}\n"
                    f"#{SCAN_TIMEFRAME.upper()}TRADE"
                )
                
                markup = {"inline_keyboard": [
                    [{"text": f"📋 Copy '{clean_sym}'", "copy_text": {"text": clean_sym}}],
                    [{"text": "📈 Open in CoinDCX", "url": f"coindcx://trade/{clean_sym}"}],
                    [{"text": "❌ Close Trade", "callback_data": f"close_{res['market']}"}]
                ]}
                
                chart_img = generate_chart_image(res['df'], clean_sym, res['signal'], res['entry'], res['sl'], res['tp1'], res['tp2'], res['tp3'])
                if chart_img: send_telegram_photo(chart_img, text, reply_markup=markup)
                else: send_telegram(text, reply_markup=markup)
                
                active_trades[res['market']] = {
                    'type': res['signal'], 'entry': res['entry'], 'sl': res['sl'], 
                    'tp1': res['tp1'], 'tp2': res['tp2'], 'tp3': res['tp3'], 'status': 'OPEN'
                }
                save_active_trades()
                time.sleep(3) # 3 sec gap
            else:
                time.sleep(2)
        except Exception as e:
            print("Sender Error:", e)
            time.sleep(5)

# ---------------- MONITOR TRADES ----------------
def monitor_trades():
    while True:
        try:
            data = get_ticker_data()
            price_map = {t['market']: float(t['last_price']) for t in data if isinstance(t, dict)}
            
            for sym, trade in list(active_trades.items()):
                if sym not in price_map: continue
                curr_price = price_map[sym]
                signal, entry = trade['type'], trade['entry']
                sl, tp1, tp2, tp3 = trade['sl'], trade['tp1'], trade['tp2'], trade['tp3']
                clean_sym = sym.replace("B-", "").replace("I-", "").replace("_", "")
                res_text = None
                
                if signal == "BUY":
                    if curr_price <= sl:
                        res_text = f"❌ <b>{clean_sym} Hit STOP LOSS</b>\nPrice: {fmt(curr_price)}"
                        del active_trades[sym]; save_active_trades()
                    elif curr_price >= tp3:
                        res_text = f"🚀 <b>{clean_sym} Hit TP3!</b>\nTrade Complete."
                        del active_trades[sym]; save_active_trades()
                    elif curr_price >= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1; trade['status'] = "TP2_HIT"
                        res_text = f"🔥 <b>{clean_sym} Hit TP2</b>\nSL moved to TP1."
                        save_active_trades()
                    elif curr_price >= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry; trade['status'] = "TP1_HIT"
                        res_text = f"✅ <b>{clean_sym} Hit TP1</b>\nSL moved to Entry."
                        save_active_trades()

                elif signal == "SELL":
                    if curr_price >= sl:
                        res_text = f"❌ <b>{clean_sym} Hit STOP LOSS</b>\nPrice: {fmt(curr_price)}"
                        del active_trades[sym]; save_active_trades()
                    elif curr_price <= tp3:
                        res_text = f"🚀 <b>{clean_sym} Hit TP3!</b>\nTrade Complete."
                        del active_trades[sym]; save_active_trades()
                    elif curr_price <= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1; trade['status'] = "TP2_HIT"
                        res_text = f"🔥 <b>{clean_sym} Hit TP2</b>\nSL moved to TP1."
                        save_active_trades()
                    elif curr_price <= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry; trade['status'] = "TP1_HIT"
                        res_text = f"✅ <b>{clean_sym} Hit TP1</b>\nSL moved to Entry."
                        save_active_trades()
                
                if res_text: send_telegram(res_text)
        except: pass
        time.sleep(15)

# ---------------- TELEGRAM COMMANDS & MENU ----------------
def telegram_commands():
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
                            try: requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/answerCallbackQuery?callback_query_id={callback_id}")
                            except: pass
                            continue
                    
                    else:
                        text = update.get("message", {}).get("text", "")
                        chat_id = update.get("message", {}).get("chat", {}).get("id")
                    
                    if str(chat_id) == str(TG_CHAT_ID):
                        # -------- MENU --------
                        if text in ["/start", "/menu"]:
                            markup = {"inline_keyboard": [
                                [{"text": "🚀 SCAN NOW (Manual)", "callback_data": "scan_now"}],
                                [{"text": "🏆 Gainers", "callback_data": "/top"}, {"text": "📉 Losers", "callback_data": "/bottom"}],
                                [{"text": "🌡️ Sentiment", "callback_data": "/sentiment"}, {"text": "🚀 Pump/Dump", "callback_data": "/pump"}],
                                [{"text": "📈 Active Trades", "callback_data": "/trades"}],
                                [{"text": "📊 RSI Scanner", "callback_data": "/rsi"}],
                                [{"text": "🔊 Volume Top", "callback_data": "/volume"}]
                            ]}
                            send_telegram(f"👋 <b>Welcome to cripto_adda V47!</b>\nSelect an option:", reply_markup=markup)

                        elif text == "scan_now":
                            send_telegram("⏳ Running Manual Scan... Please wait.")
                            def manual_scan_thread():
                                data = get_ticker_data()
                                if data:
                                    valid_coins = [c for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market', ''))) and float(c.get('volume', 0)) > 100000]
                                    valid_coins.sort(key=lambda x: float(x.get('volume', 0)), reverse=True)
                                    valid_coins = valid_coins[:100]
                                    found = 0
                                    for c in valid_coins:
                                        res = scan_coin(c['market'])
                                        if res:
                                            signal_queue.put(res)
                                            found += 1
                                        time.sleep(1)
                                    send_telegram(f"✅ Manual Scan Complete. Found {found} signals.")
                            Thread(target=manual_scan_thread).start()

                        # -------- FIXED FEATURES --------
                        elif text == "/top" or text == "/bottom":
                            send_telegram("⏳ Fetching...")
                            data = get_ticker_data()
                            valid = [{'m': str(c.get('market')), 'c': float(c.get('change24hour', 0)), 'p': float(c.get('last_price', 0))} for c in data if isinstance(c, dict) and 'USDT' in str(c.get('market'))]
                            
                            # Sort properly
                            is_top = text == "/top"
                            sorted_coins = sorted(valid, key=lambda x: x['c'], reverse=is_top)[:5]
                            
                            msg = f"{'🏆 <b>Top 5 Gainers</b>' if is_top else '📉 <b>Top 5 Losers</b>'}\n\n"
                            for i, c in enumerate(sorted_coins): 
                                msg += f"{i+1}. <b>{c['m'].replace('B-','').replace('_','')}</b>: {c['c']:+.2f}% | ₹{fmt(c['p'])}\n"
                            send_telegram(msg)

                        elif text == "/pump":
                            send_telegram("⏳ Scanning for Pumps/Dumps (>5%)...")
                            data = get_ticker_data()
                            movers = [c for c in data if isinstance(c, dict) and 'USDT' in str(c.get('market')) and abs(float(c.get('change24hour', 0))) > 5]
                            movers = sorted(movers, key=lambda x: abs(float(x.get('change24hour', 0))), reverse=True)[:5]
                            
                            if not movers: return send_telegram("🤷‍♂️ No major pumps/dumps right now.")
                            
                            msg = "🚀 <b>Pump & Dump Alerts</b>\n\n"
                            for c in movers:
                                clean = c['market'].replace("B-", "").replace("_", "")
                                chg = float(c['change24hour'])
                                emoji = "🟢" if chg > 0 else "🔴"
                                msg += f"{emoji} <b>{clean}:</b> {chg:+.2f}% | ₹{fmt(c['last_price'])}\n"
                            send_telegram(msg)

                        elif text == "/sentiment":
                            r = requests.get("https://api.alternative.me/fng/", timeout=5).json()
                            send_telegram(f"🌡️ <b>Market Sentiment</b>\n\n📊 Value: {r['data'][0]['value']}/100\n📝 Status: {r['data'][0]['value_classification']}")

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

                        elif text == "/rsi":
                            send_telegram("⏳ Scanning top 10 volume coins for RSI...")
                            data = get_ticker_data()
                            valid = [c for c in data if isinstance(c, dict) and 'USDT' in str(c.get('market'))]
                            valid = sorted(valid, key=lambda x: float(x.get('volume', 0)), reverse=True)[:10]
                            oversold, overbought = [], []
                            for c in valid:
                                sym = c['market']
                                res = get_klines(sym, "15m", 50)
                                if isinstance(res, list) and len(res) >= 50:
                                    closes = [float(x['close']) for x in res]
                                    s = pd.Series(closes)
                                    delta = s.diff()
                                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                                    rsi = (100 - (100 / (1 + (gain / loss)))).iloc[-1]
                                    clean = sym.replace('B-','').replace('_','')
                                    if rsi < 30: oversold.append(f"🟢 {clean} (RSI: {rsi:.1f})")
                                    elif rsi > 70: overbought.append(f"🔴 {clean} (RSI: {rsi:.1f})")
                            msg = "📊 <b>RSI Scanner</b>\n\n📉 <b>Oversold (<30):</b>\n" + ("\n".join(oversold) if oversold else "None") + "\n\n📈 <b>Overbought (>70):</b>\n" + ("\n".join(overbought) if overbought else "None")
                            send_telegram(msg)

                        elif text == "/volume":
                            data = get_ticker_data()
                            valid = [c for c in data if isinstance(c, dict) and 'USDT' in str(c.get('market'))]
                            valid = sorted(valid, key=lambda x: float(x.get('volume', 0)), reverse=True)[:5]
                            msg = "🔊 <b>Top 5 Volume Coins</b>\n\n"
                            for i, c in enumerate(valid):
                                clean = c['market'].replace('B-','').replace('_','')
                                msg += f"{i+1}. <b>{clean}</b>\nVol: {float(c['volume']):,.0f} | Price: ₹{fmt(c['last_price'])}\n\n"
                            send_telegram(msg)
                            
        except Exception as e:
            print("Command Error:", e)
        time.sleep(2)

if __name__ == "__main__":
    load_active_trades()
    keep_alive()
    Thread(target=monitor_trades).start()
    Thread(target=telegram_commands).start()
    Thread(target=signal_sender).start()
    Thread(target=background_scanner).start()
