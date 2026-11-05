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

@app.route('/')
def home():
    return "CoinDCX Ultimate V7 Bot is Running!"

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
SCAN_TIMEFRAME = "15m" # Default

# ---------------- TRADE JOURNAL (JSON) ----------------
def save_to_journal(trade_data):
    try:
        journal = []
        if os.path.exists("journal.json"):
            with open("journal.json", "r") as f:
                journal = json.load(f)
        journal.append(trade_data)
        with open("journal.json", "w") as f:
            json.dump(journal, f)
    except: pass

def get_journal():
    try:
        if os.path.exists("journal.json"):
            with open("journal.json", "r") as f:
                return json.load(f)
    except: pass
    return []

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
            
            for sym, alert_data in list(price_alerts.items()):
                if sym in price_map:
                    curr_price = price_map[sym]
                    target = alert_data['price']
                    alert_type = alert_data['type']
                    if (alert_type == 'above' and curr_price >= target) or (alert_type == 'below' and curr_price <= target):
                        clean = sym.replace("B-", "").replace("I-", "").replace("_", "")
                        send_telegram(f"🚨 *PRICE ALERT!*\n\n🪙 *Coin:* {clean}\n💰 *Target:* {target}\n📈 *Current:* {curr_price}\n\n_Alert removed._")
                        del price_alerts[sym]

            for sym, trade in list(active_trades.items()):
                if sym not in price_map: continue
                curr_price = price_map[sym]
                signal, entry = trade['type'], trade['entry']
                sl, tp1, tp2, tp3 = trade['sl'], trade['tp1'], trade['tp2'], trade['tp3']
                clean_sym = sym.replace("B-", "").replace("I-", "").replace("_", "")
                res_text = None

                if signal == "BUY":
                    if curr_price <= sl:
                        res_text = f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {curr_price:.4f}"
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'BUY', 'result': 'LOSS'})
                        del active_trades[sym]
                    elif curr_price >= tp3:
                        res_text = f"🚀 *{clean_sym} Hit TP3!*\nTrade Complete."
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'BUY', 'result': 'WIN'})
                        del active_trades[sym]
                    elif curr_price >= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1 
                        res_text = f"🔥 *{clean_sym} Hit TP2*\nSL moved to TP1."
                        trade['status'] = "TP2_HIT"
                    elif curr_price >= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry 
                        res_text = f"✅ *{clean_sym} Hit TP1*\nSL moved to Entry (Risk-Free)."
                        trade['status'] = "TP1_HIT"

                elif signal == "SELL":
                    if curr_price >= sl:
                        res_text = f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {curr_price:.4f}"
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'SELL', 'result': 'LOSS'})
                        del active_trades[sym]
                    elif curr_price <= tp3:
                        res_text = f"🚀 *{clean_sym} Hit TP3!*\nTrade Complete."
                        save_to_journal({'date': str(datetime.datetime.now()), 'coin': clean_sym, 'type': 'SELL', 'result': 'WIN'})
                        del active_trades[sym]
                    elif curr_price <= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1 
                        res_text = f"🔥 *{clean_sym} Hit TP2*\nSL moved to TP1."
                        trade['status'] = "TP2_HIT"
                    elif curr_price <= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry 
                        res_text = f"✅ *{clean_sym} Hit TP1*\nSL moved to Entry (Risk-Free)."
                        trade['status'] = "TP1_HIT"
                
                if res_text:
                    send_telegram(res_text)
        except: pass
        time.sleep(15)

# ---------------- BACKTESTING ENGINE ----------------
def run_backtest(coin, tf):
    send_telegram(f"⏳ Running Backtest for *{coin}* on {tf}... (Please wait)")
    try:
        c_sym = f"B-{coin}_USDT"
        res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval={tf}&limit=500", headers=headers, timeout=10).json()
        if not isinstance(res, list) or len(res) < 200:
            send_telegram("❌ Not enough data for backtest.")
            return
        
        res.reverse()
        df = pd.DataFrame(res)
        for col in ['close', 'high', 'low', 'volume', 'open']: df[col] = df[col].astype(float)
        df = calculate_indicators(df)
        
        wins, losses = 0, 0
        
        # Simple loop backtest
        for i in range(200, len(df)-10):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            
            macd_up = (prev['macd'] < prev['macd_signal']) and (row['macd'] > row['macd_signal'])
            macd_down = (prev['macd'] > prev['macd_signal']) and (row['macd'] < row['macd_signal'])
            vol_spike = row['volume'] > (df['volume'].iloc[i-20:i].mean() * 1.5)
            
            signal = None
            if row['adx'] > 25 and vol_spike:
                if macd_up and row['close'] > row['ema200'] and row['close'] > row['vwap']:
                    signal = "BUY"
                elif macd_down and row['close'] < row['ema200'] and row['close'] < row['vwap']:
                    signal = "SELL"
            
            if signal:
                entry = row['close']
                risk = row['atr'] * 2.5
                # Check future 10 candles for SL or TP1
                outcome = "OPEN"
                for j in range(i+1, min(i+11, len(df))):
                    future_high = df.iloc[j]['high']
                    future_low = df.iloc[j]['low']
                    
                    if signal == "BUY":
                        if future_low <= entry - risk: outcome = "LOSS"; break
                        if future_high >= entry + (risk * 1.5): outcome = "WIN"; break
                    else:
                        if future_high >= entry + risk: outcome = "LOSS"; break
                        if future_low <= entry - (risk * 1.5): outcome = "WIN"; break
                
                if outcome == "WIN": wins += 1
                elif outcome == "LOSS": losses += 1

        total = wins + losses
        wr = (wins/total*100) if total > 0 else 0
        send_telegram(f"📊 *Backtest Result: {coin} ({tf})*\n\n"
                      f"🟢 Wins: {wins}\n🔴 Losses: {losses}\n"
                      f"📈 *Win Rate:* {wr:.1f}%\n"
                      f"⏱️ Tested on last {total} signals.")
    except Exception as e:
        send_telegram("❌ Backtest failed. Check coin name.")

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
                    if "callback_query" in update:
                        text = update["callback_query"]["data"]
                        chat_id = update["callback_query"]["message"]["chat"]["id"]
                    else:
                        text = update.get("message", {}).get("text", "")
                        chat_id = update.get("message", {}).get("chat", {}).get("id")
                    
                    if str(chat_id) == str(TG_CHAT_ID):
                        if text in ["/start", "/menu"]:
                            markup = {"inline_keyboard": [
                                [{"text": "📊 Status", "callback_data": "/status"}, {"text": "🏆 Gainers", "callback_data": "/top"}],
                                [{"text": "📉 Losers", "callback_data": "/bottom"}, {"text": "📈 Trades", "callback_data": "/trades"}],
                                [{"text": "🔬 Analysis", "callback_data": "/analysis BTC"}, {"text": "📓 Journal", "callback_data": "/journal"}]
                            ]}
                            send_telegram(f"👋 *Welcome V7!*\nCurrent Scan TF: *{SCAN_TIMEFRAME}*\nUse `/scan 1h` to change.", reply_markup=markup)
                        
                        elif text == "/status":
                            send_telegram(f"🤖 *Bot Running*\nScanning: {SCAN_TIMEFRAME}\nActive Trades: {len(active_trades)}\nAlerts: {len(price_alerts)}")

                        elif text == "/journal":
                            j = get_journal()
                            if not j: send_telegram("📓 Journal is empty.")
                            else:
                                msg = "📓 *Trade Journal (Last 5)*\n\n"
                                for t in j[-5:]:
                                    msg += f"🪙 {t['coin']} ({t['type']})\nResult: {t['result']}\n\n"
                                send_telegram(msg)

                        elif text.startswith("/scan"):
                            parts = text.split()
                            if len(parts) > 1 and parts[1] in ['1m','5m','15m','1h','4h']:
                                SCAN_TIMEFRAME = parts[1]
                                send_telegram(f"✅ Scanner timeframe changed to *{SCAN_TIMEFRAME}*.")
                            else:
                                send_telegram("⚠️ Use: `/scan 15m` or `/scan 1h`")

                        elif text.startswith("/backtest"):
                            parts = text.split()
                            if len(parts) >= 3:
                                Thread(target=run_backtest, args=(parts[1].upper(), parts[2])).start()
                            else:
                                send_telegram("⚠️ Use: `/backtest BTC 15m`")

                        elif text.startswith("/analysis"):
                            parts = text.split()
                            if len(parts) > 1:
                                target = parts[1].upper()
                                send_telegram(f"⏳ Analyzing *{target}*...")
                                try:
                                    c_sym = f"B-{target}_USDT"
                                    msg = f"🔬 <b>Analysis: {target}</b>\n\n"
                                    for tf in ['15m', '1h', '4h']:
                                        res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval={tf}&limit=200", headers=headers, timeout=5).json()
                                        if isinstance(res, list) and len(res) >= 50:
                                            res.reverse()
                                            closes = [float(c['close']) for c in res]
                                            ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().iloc[-1]
                                            trend = "🟢 BULLISH" if closes[-1] > ema50 else "🔴 BEARISH"
                                            s = pd.Series(closes)
                                            delta = s.diff()
                                            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                                            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                                            rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
                                            msg += f"⏱️ <b>{tf} Trend:</b> {trend} (RSI: {rsi:.1f})\n"
                                    requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"})
                                except: send_telegram("❌ Error.")
        except: pass
        time.sleep(2)

# ---------------- INDICATORS (WITH VWAP) ----------------
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
    
    # VWAP Calculation
    df['vwap'] = (df['volume'] * (df['high'] + df['low'] + df['close']) / 3).cumsum() / df['volume'].cumsum()
    
    return df

# ---------------- SCANNER ----------------
def scan_market():
    global SCAN_TIMEFRAME
    try:
        data = get_ticker_data()
        if not data: return
        all_coins = [str(c.get('market', '')) for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market', ''))) and float(c.get('volume', 0)) > 50000]
        
        for sym in all_coins:
            if sym in active_trades: continue
            if sym in last_signal_time and (time.time() - last_signal_time[sym] < 4 * 3600): continue

            try:
                c_sym = sym
                if '_' not in c_sym: c_sym = 'B-' + c_sym.replace('USDT', '_USDT')

                k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval={SCAN_TIMEFRAME}&limit=200", headers=headers, timeout=5).json()
                if not isinstance(k_res, list) or len(k_res) < 200: continue
                k_res.reverse() 
                df = pd.DataFrame(k_res)
                for col in ['close', 'high', 'low', 'volume', 'open']: df[col] = df[col].astype(float)
                df = calculate_indicators(df)
                
                last, prev = df.iloc[-1], df.iloc[-2]
                current_price, ema200, rsi, atr, adx, vwap = last['close'], last['ema200'], last['rsi'], last['atr'], last['adx'], last['vwap']
                
                macd_up = (prev['macd'] < prev['macd_signal']) and (last['macd'] > last['macd_signal'])
                macd_down = (prev['macd'] > prev['macd_signal']) and (last['macd'] < last['macd_signal'])
                vol_spike = last['volume'] > (df['volume'].tail(20).mean() * 1.5)

                # Fibonacci Levels (Recent High/Low)
                recent_high = df['high'].tail(50).max()
                recent_low = df['low'].tail(50).min()
                fib_618 = recent_high - (recent_high - recent_low) * 0.618
                fib_50 = recent_high - (recent_high - recent_low) * 0.5

                signal = None
                # STRICT: ADX > 25, Price > VWAP (Bullish), Price near Fib level
                if adx > 25 and vol_spike:
                    if macd_up and current_price > ema200 and current_price > vwap and rsi > 50:
                        # Check if price is near 0.5 - 0.618 Fib zone
                        if fib_618 <= current_price <= fib_50 or (current_price > fib_50 and current_price < fib_50 * 1.01):
                            h4 = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval=4h&limit=100", headers=headers, timeout=5).json()
                            if isinstance(h4, list) and len(h4) >= 50:
                                h4.reverse()
                                h4_ema50 = pd.Series([float(c['close']) for c in h4]).ewm(span=50, adjust=False).mean().iloc[-1]
                                if current_price > h4_ema50: signal = "BUY"
                                
                    elif macd_down and current_price < ema200 and current_price < vwap and rsi < 50:
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
                    
                    clean_sym = sym.replace("B-", "").replace("_", "")
                    dcx_link = f"https://coindcx.com/trade/{clean_sym}"
                    
                    text = (f"🎯 *SNIPER {signal} ({SCAN_TIMEFRAME})*\n\n"
                            f"🪙 *Coin:* {clean_sym}\n"
                            f"💰 *Entry:* {entry:.4f}\n🛑 *SL:* {sl:.4f}\n"
                            f"🎯 *TP1:* {tp1:.4f}\n🎯 *TP2:* {tp2:.4f}\n🎯 *TP3:* {tp3:.4f}\n"
                            f"📊 *ADX:* {adx:.1f} | *VWAP:* ✅\n"
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
