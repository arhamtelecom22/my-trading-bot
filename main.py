import os
import requests
import time
import pandas as pd
from flask import Flask
from threading import Thread
import datetime

# ================= TOKEN RENDER SE AAYEGA =================
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = "762295473"
# ============================================================

app = Flask('')

@app.route('/')
def home():
    return "CoinDCX Ultimate Sniper Bot is Running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

def send_telegram(text, reply_markup=None):
    if not TG_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload)
    except: pass

headers = {'User-Agent': 'Mozilla/5.0'}

last_ticker_data = []
last_ticker_time = 0
active_trades = {}
price_alerts = {} 
last_signal_time = {} 

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

# ---------------- MONITOR TRADES & ALERTS ----------------
def monitor_trades():
    while True:
        try:
            tickers = get_ticker_data()
            if not tickers:
                time.sleep(10)
                continue
                
            price_map = {t['market']: float(t['last_price']) for t in tickers if isinstance(t, dict)}
            
            # 1. CHECK PRICE ALERTS
            for sym, alert_data in list(price_alerts.items()):
                if sym in price_map:
                    curr_price = price_map[sym]
                    target = alert_data['price']
                    alert_type = alert_data['type']
                    
                    if (alert_type == 'above' and curr_price >= target) or (alert_type == 'below' and curr_price <= target):
                        clean = sym.replace("B-", "").replace("I-", "").replace("_", "")
                        send_telegram(f"🚨 *PRICE ALERT TRIGGERED!*\n\n🪙 *Coin:* {clean}\n💰 *Target:* {target}\n📈 *Current Price:* {curr_price}\n\n_Alert has been removed._")
                        del price_alerts[sym]

            # 2. MONITOR ACTIVE TRADES
            for sym, trade in list(active_trades.items()):
                if sym not in price_map: continue
                curr_price = price_map[sym]
                signal, entry = trade['type'], trade['entry']
                sl, tp1, tp2, tp3 = trade['sl'], trade['tp1'], trade['tp2'], trade['tp3']
                clean_sym = sym.replace("B-", "").replace("I-", "").replace("_", "")

                if signal == "BUY":
                    if curr_price <= sl:
                        send_telegram(f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {curr_price:.4f}")
                        del active_trades[sym]
                    elif curr_price >= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry 
                        send_telegram(f"✅ *{clean_sym} Hit TP1*\nSL moved to Entry (Risk-Free).")
                        trade['status'] = "TP1_HIT"
                    elif curr_price >= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1 
                        send_telegram(f"🔥 *{clean_sym} Hit TP2*\nSL moved to TP1.")
                        trade['status'] = "TP2_HIT"
                    elif curr_price >= tp3:
                        send_telegram(f"🚀 *{clean_sym} Hit TP3!*\nTrade Complete.")
                        del active_trades[sym]

                elif signal == "SELL":
                    if curr_price >= sl:
                        send_telegram(f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {curr_price:.4f}")
                        del active_trades[sym]
                    elif curr_price <= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry 
                        send_telegram(f"✅ *{clean_sym} Hit TP1*\nSL moved to Entry (Risk-Free).")
                        trade['status'] = "TP1_HIT"
                    elif curr_price <= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1 
                        send_telegram(f"🔥 *{clean_sym} Hit TP2*\nSL moved to TP1.")
                        trade['status'] = "TP2_HIT"
                    elif curr_price <= tp3:
                        send_telegram(f"🚀 *{clean_sym} Hit TP3!*\nTrade Complete.")
                        del active_trades[sym]
        except Exception as e: 
            print("Monitor Error:", e)
        time.sleep(15)

# ---------------- TELEGRAM COMMANDS ----------------
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
                        text = update["callback_query"]["data"]
                        chat_id = update["callback_query"]["message"]["chat"]["id"]
                    else:
                        text = update.get("message", {}).get("text", "")
                        chat_id = update.get("message", {}).get("chat", {}).get("id")
                    
                    if str(chat_id) == str(TG_CHAT_ID):
                        # --- MENU ---
                        if text in ["/start", "/menu"]:
                            markup = {"inline_keyboard": [
                                [{"text": "📊 Status", "callback_data": "/status"}, {"text": "🏆 Top Gainers", "callback_data": "/top"}],
                                [{"text": "📉 Top Losers", "callback_data": "/bottom"}, {"text": "📈 Active Trades", "callback_data": "/trades"}],
                                [{"text": "🔍 Search Coin", "callback_data": "/search BTC"}, {"text": "🔬 Deep Analysis", "callback_data": "/analysis BTC"}]
                            ]}
                            send_telegram("👋 *Welcome to God-Tier Bot!*\nSelect an option or type commands:", reply_markup=markup)
                        
                        # --- STATUS ---
                        elif text == "/status":
                            send_telegram(f"🤖 *Bot Running*\nActive Trades: {len(active_trades)}\nActive Alerts: {len(price_alerts)}")
                        
                        # --- ACTIVE TRADES ---
                        elif text == "/trades":
                            if not active_trades: send_telegram("💤 *No active trades.*")
                            else:
                                t_text = "📈 *Active Trades:*\n\n"
                                for s, t in active_trades.items():
                                    t_text += f"🪙 *{s.replace('B-','').replace('I-','').replace('_','')}* ({t['type']})\nEntry: {t['entry']:.4f} | SL: {t['sl']:.4f}\n\n"
                                send_telegram(t_text)
                        
                        # --- TOP GAINERS ---
                        elif text == "/top":
                            send_telegram("⏳ Fetching top movers...")
                            try:
                                data = get_ticker_data()
                                valid = [{'m': str(c.get('market')), 'c': float(c.get('change24hour', 0)), 'p': float(c.get('last_price', 0)), 'v': float(c.get('volume', 0))} for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market')) or 'INR' in str(c.get('market')))]
                                top = sorted(valid, key=lambda x: x['c'], reverse=True)[:5]
                                msg = "🏆 <b>Top 5 Gainers (24h)</b>\n\n"
                                for i, c in enumerate(top): 
                                    msg += f"{i+1}. <b>{c['m'].replace('B-','').replace('I-','').replace('_','')}</b>\n📈 +{c['c']:.2f}% | 💰 {c['p']}\n📊 Vol: {c['v']:,.0f}\n\n"
                                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"})
                            except: send_telegram("❌ API Error.")

                        # --- TOP LOSERS (NEW) ---
                        elif text == "/bottom":
                            send_telegram("⏳ Fetching top losers...")
                            try:
                                data = get_ticker_data()
                                valid = [{'m': str(c.get('market')), 'c': float(c.get('change24hour', 0)), 'p': float(c.get('last_price', 0)), 'v': float(c.get('volume', 0))} for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market')) or 'INR' in str(c.get('market')))]
                                bottom = sorted(valid, key=lambda x: x['c'], reverse=False)[:5]
                                msg = "📉 <b>Top 5 Losers (24h)</b>\n\n"
                                for i, c in enumerate(bottom): 
                                    msg += f"{i+1}. <b>{c['m'].replace('B-','').replace('I-','').replace('_','')}</b>\n📉 {c['c']:.2f}% | 💰 {c['p']}\n📊 Vol: {c['v']:,.0f}\n\n"
                                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"})
                            except: send_telegram("❌ API Error.")

                        # --- SET PRICE ALERT (NEW) ---
                        elif text.startswith("/alert"):
                            parts = text.split()
                            if len(parts) == 3:
                                target_coin = parts[1].upper()
                                try:
                                    target_price = float(parts[2])
                                    data = get_ticker_data()
                                    found = False
                                    for c in data:
                                        if isinstance(c, dict):
                                            m = str(c.get('market'))
                                            m_clean = m.replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "").replace("USDT", "").replace("INR", "")
                                            if m_clean == target_coin:
                                                curr_p = float(c.get('last_price', 0))
                                                alert_type = 'above' if target_price > curr_p else 'below'
                                                price_alerts[m] = {'price': target_price, 'type': alert_type}
                                                send_telegram(f"✅ Alert set for {target_coin} at {target_price} (Current: {curr_p})")
                                                found = True
                                                break
                                    if not found: send_telegram("❌ Coin not found.")
                                except: send_telegram("❌ Invalid price format.")
                            else: send_telegram("⚠️ Format: `/alert BTC 65000`")

                        # --- DEEP ANALYSIS (NEW) ---
                        elif text.startswith("/analysis"):
                            parts = text.split()
                            if len(parts) > 1:
                                target = parts[1].upper()
                                send_telegram(f"⏳ Running deep analysis for *{target}*...")
                                try:
                                    data = get_ticker_data()
                                    matched = None
                                    for c in data:
                                        if isinstance(c, dict):
                                            m = str(c.get('market'))
                                            m_clean = m.replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "").replace("USDT", "").replace("INR", "")
                                            if m_clean == target:
                                                matched = m
                                                if 'USDT' in m: break
                                    if not matched: 
                                        send_telegram("❌ Coin not found.")
                                        continue
                                    
                                    c_sym = matched
                                    if '_' not in c_sym and 'USDT' in c_sym: c_sym = 'B-' + c_sym.replace('USDT', '_USDT')
                                    elif '_' not in c_sym and 'INR' in c_sym: c_sym = 'I-' + c_sym.replace('INR', '_INR')
                                    
                                    msg = f"🔬 <b>Deep Analysis: {target}</b>\n\n"
                                    for tf in ['15m', '1h', '4h']:
                                        res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval={tf}&limit=200", headers=headers, timeout=5).json()
                                        if isinstance(res, list) and len(res) >= 50:
                                            res.reverse()
                                            closes = [float(c['close']) for c in res]
                                            ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().iloc[-1]
                                            trend = "🟢 BULLISH" if closes[-1] > ema50 else "🔴 BEARISH"
                                            
                                            # Simple RSI calc
                                            s = pd.Series(closes)
                                            delta = s.diff()
                                            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                                            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                                            rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
                                            
                                            msg += f"⏱️ <b>{tf} Trend:</b> {trend}\n📊 RSI: {rsi:.2f}\n\n"
                                    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"})
                                except Exception as e: send_telegram("❌ Analysis Error.")
                            else: send_telegram("⚠️ Format: `/analysis BTC`")
        except: pass
        time.sleep(2)

# ---------------- INDICATORS (WITH ADX) ----------------
def calculate_indicators(df):
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    # ADX Calculation (To avoid sideways markets)
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
    return df

# ---------------- MARKET SCANNER ----------------
def scan_market():
    try:
        data = get_ticker_data()
        if not data: return
        all_coins = [str(c.get('market', '')) for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market', '')) or 'INR' in str(c.get('market', ''))) and float(c.get('volume', 0)) > 50000]
        
        for sym in all_coins:
            if sym in active_trades: continue
            
            # 4-Hour Cooldown Check
            now_time = time.time()
            if sym in last_signal_time and (now_time - last_signal_time[sym] < 4 * 3600):
                continue

            try:
                c_sym = sym
                if '_' not in c_sym and 'USDT' in c_sym: c_sym = 'B-' + c_sym.replace('USDT', '_USDT')
                elif '_' not in c_sym and 'INR' in c_sym: c_sym = 'I-' + c_sym.replace('INR', '_INR')

                k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval=15m&limit=200", headers=headers, timeout=5).json()
                if not isinstance(k_res, list) or len(k_res) < 200: continue
                k_res.reverse() 
                df = pd.DataFrame(k_res)
                for col in ['close', 'high', 'low', 'volume', 'open']: df[col] = df[col].astype(float)
                df = calculate_indicators(df)
                
                last, prev = df.iloc[-1], df.iloc[-2]
                current_price, ema200, rsi, atr, adx = last['close'], last['ema200'], last['rsi'], last['atr'], last['adx']
                
                macd_up = (prev['macd'] < prev['macd_signal']) and (last['macd'] > last['macd_signal'])
                macd_down = (prev['macd'] > prev['macd_signal']) and (last['macd'] < last['macd_signal'])
                vol_spike = last['volume'] > (df['volume'].tail(20).mean() * 1.5)

                signal = None
                # STRICT: ADX must be > 25 to confirm trend (No sideways market)
                if adx > 25 and vol_spike:
                    if macd_up and current_price > ema200 and rsi > 50:
                        h4 = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval=4h&limit=100", headers=headers, timeout=5).json()
                        if isinstance(h4, list) and len(h4) >= 50:
                            h4.reverse()
                            h4_ema50 = pd.Series([float(c['close']) for c in h4]).ewm(span=50, adjust=False).mean().iloc[-1]
                            if current_price > h4_ema50: signal = "BUY"
                            
                    elif macd_down and current_price < ema200 and rsi < 50:
                        h4 = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval=4h&limit=100", headers=headers, timeout=5).json()
                        if isinstance(h4, list) and len(h4) >= 50:
                            h4.reverse()
                            h4_ema50 = pd.Series([float(c['close']) for c in h4]).ewm(span=50, adjust=False).mean().iloc[-1]
                            if current_price < h4_ema50: signal = "SELL"

                if signal:
                    entry = current_price
                    risk = atr * 2.5 
                    if signal == "BUY": 
                        sl = entry - risk
                        tp1, tp2, tp3 = entry + (risk * 1.5), entry + (risk * 3.0), entry + (risk * 4.5)
                    else: 
                        sl = entry + risk
                        tp1, tp2, tp3 = entry - (risk * 1.5), entry - (risk * 3.0), entry - (risk * 4.5)

                    active_trades[sym] = {'type': signal, 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3, 'status': 'OPEN'}
                    last_signal_time[sym] = time.time() 
                    
                    clean_sym = sym.replace("B-", "").replace("I-", "").replace("_", "")
                    dcx_link = f"https://coindcx.com/trade/{clean_sym}"
                    
                    text = (f"🎯 *SNIPER {signal} SIGNAL*\n\n"
                            f"🪙 *Coin:* {clean_sym}\n"
                            f"💰 *Entry:* {entry:.4f}\n🛑 *SL:* {sl:.4f}\n"
                            f"🎯 *TP1:* {tp1:.4f}\n🎯 *TP2:* {tp2:.4f}\n🎯 *TP3:* {tp3:.4f}\n"
                            f"📊 *ADX:* {adx:.1f} (Strong Trend)\n"
                            f"⏱️ *TF:* 15m\n\n"
                            f"💡 _Trailing SL Active._")
                    
                    markup = {"inline_keyboard": [[{"text": f"📋 Copy '{clean_sym}'", "copy_text": {"text": clean_sym}}], [{"text": "🌐 Open Web Chart", "url": dcx_link}]]}
                    send_telegram(text, reply_markup=markup)
            except: pass
            time.sleep(0.5)
    except: pass

if __name__ == "__main__":
    keep_alive()
    Thread(target=monitor_trades).start()
    Thread(target=telegram_commands).start()
    while True:
        scan_market()
        time.sleep(300)
