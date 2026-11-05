import os
import requests
import time
import pandas as pd
from flask import Flask
from threading import Thread

# ================= TOKEN RENDER SE AAYEGA =================
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = "762295473"
# ============================================================

app = Flask('')

@app.route('/')
def home():
    return "CoinDCX Ultimate Bot is Running 24/7!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

def send_telegram(text):
    if not TG_TOKEN: 
        print("ERROR: Token not found!")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("TG Error:", e)

# API Block na ho isliye Headers
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# ---------------- SMART CACHE FOR SCANNER ----------------
last_ticker_data = []
last_ticker_time = 0

def get_ticker_data():
    global last_ticker_data, last_ticker_time
    now = time.time()
    if last_ticker_data and (now - last_ticker_time < 60):
        return last_ticker_data
        
    try:
        res = requests.get("https://api.coindcx.com/exchange/ticker", headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list):
                last_ticker_data = data
                last_ticker_time = now
                return data
    except:
        pass
    return last_ticker_data if last_ticker_data else []

# ---------------- ACTIVE TRADES TRACKER ----------------
active_trades = {}

def monitor_trades():
    while True:
        if not active_trades:
            time.sleep(30)
            continue
        
        try:
            tickers = get_ticker_data()
            price_map = {t['market']: float(t['last_price']) for t in tickers if isinstance(t, dict)}
            
            for sym, trade in list(active_trades.items()):
                if sym not in price_map: continue
                curr_price = price_map[sym]
                
                signal = trade['type']
                entry = trade['entry']
                sl, tp1, tp2, tp3 = trade['sl'], trade['tp1'], trade['tp2'], trade['tp3']
                clean_sym = sym.replace("B-", "").replace("I-", "").replace("_", "")

                if signal == "BUY":
                    if curr_price <= sl:
                        send_telegram(f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {curr_price:.4f}\nTrade Closed.")
                        del active_trades[sym]
                    elif curr_price >= tp1 and trade['status'] == "OPEN":
                        send_telegram(f"✅ *{clean_sym} Hit TP1*\nPrice: {curr_price:.4f}\n_Book 50% profit. Move SL to Entry._")
                        trade['status'] = "TP1_HIT"
                    elif curr_price >= tp2 and trade['status'] in ["OPEN", "TP1_HIT"]:
                        send_telegram(f"🔥 *{clean_sym} Hit TP2*\nPrice: {curr_price:.4f}\n_Book 25% more profit._")
                        trade['status'] = "TP2_HIT"
                    elif curr_price >= tp3:
                        send_telegram(f"🚀 *{clean_sym} Hit TP3!*\nPrice: {curr_price:.4f}\n_Trade Complete. Book remaining 25%._")
                        del active_trades[sym]

                elif signal == "SELL":
                    if curr_price >= sl:
                        send_telegram(f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {curr_price:.4f}\nTrade Closed.")
                        del active_trades[sym]
                    elif curr_price <= tp1 and trade['status'] == "OPEN":
                        send_telegram(f"✅ *{clean_sym} Hit TP1*\nPrice: {curr_price:.4f}\n_Book 50% profit. Move SL to Entry._")
                        trade['status'] = "TP1_HIT"
                    elif curr_price <= tp2 and trade['status'] in ["OPEN", "TP1_HIT"]:
                        send_telegram(f"🔥 *{clean_sym} Hit TP2*\nPrice: {curr_price:.4f}\n_Book 25% more profit._")
                        trade['status'] = "TP2_HIT"
                    elif curr_price <= tp3:
                        send_telegram(f"🚀 *{clean_sym} Hit TP3!*\nPrice: {curr_price:.4f}\n_Trade Complete. Book remaining 25%._")
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
                    msg = update.get("message", {})
                    text = msg.get("text", "")
                    chat_id = msg.get("chat", {}).get("id")
                    
                    if str(chat_id) == str(TG_CHAT_ID):
                        if text == "/status":
                            send_telegram(f"🤖 *Bot Status: RUNNING*\nActive Trades: {len(active_trades)}")
                        
                        elif text == "/top":
                            send_telegram("⏳ Fetching top movers from CoinDCX...")
                            try:
                                # Direct fetch for /top without cache to ensure fresh data
                                res = requests.get("https://api.coindcx.com/exchange/ticker", headers=headers, timeout=15)
                                if res.status_code != 200:
                                    send_telegram(f"❌ API Error: Status {res.status_code}")
                                    continue
                                
                                data = res.json()
                                if not isinstance(data, list) or len(data) == 0:
                                    send_telegram("❌ API returned no data. Try again in 1 min.")
                                    continue

                                valid_coins = []
                                for c in data:
                                    if not isinstance(c, dict): continue
                                    m = str(c.get('market', ''))
                                    # FIX: Check if USDT or INR is anywhere in the name (handles both B-BTC_USDT and BTCUSDT)
                                    if 'USDT' in m or 'INR' in m:
                                        raw_ch = c.get('change24hour', 0)
                                        try:
                                            ch = float(raw_ch)
                                        except:
                                            ch = 0.0
                                        valid_coins.append({'market': m, 'change': ch})
                                
                                if not valid_coins:
                                    send_telegram(f"⚠️ No USDT/INR pairs found in {len(data)} coins.")
                                    continue
                                
                                top = sorted(valid_coins, key=lambda x: x['change'], reverse=True)[:5]
                                t_text = "🏆 <b>Top 5 Gainers (24h)</b>\n\n"
                                for idx, c in enumerate(top):
                                    sym = c['market'].replace("B-", "").replace("I-", "").replace("_", "")
                                    t_text += f"{idx+1}. <b>{sym}</b>: {c['change']:.2f}%\n"
                                
                                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                                payload = {"chat_id": TG_CHAT_ID, "text": t_text, "parse_mode": "HTML"}
                                requests.post(url, json=payload, timeout=10)
                                
                            except Exception as e:
                                send_telegram(f"❌ Error: {str(e)[:100]}")

                        elif text.startswith("/trend"):
                            parts = text.split()
                            if len(parts) > 1:
                                target_sym = parts[1].upper()
                                send_telegram(f"⏳ Checking trend for {target_sym}...")
                                try:
                                    res_c = requests.get(f"https://public.coindcx.com/market_data/candles?pair=B-{target_sym}_USDT&interval=1h&limit=200", headers=headers).json()
                                    if isinstance(res_c, list) and len(res_c) > 50:
                                        res_c.reverse()
                                        closes = [float(c['close']) for c in res_c]
                                        ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().iloc[-1]
                                        trend = "BULLISH 🟢" if closes[-1] > ema50 else "BEARISH 🔴"
                                        send_telegram(f"📊 *{target_sym} 1H Trend:*\n{trend}\nCurrent Price: {closes[-1]}")
                                    else:
                                        send_telegram("❌ Could not fetch data. Check symbol format (e.g., /trend BTC).")
                                except:
                                    send_telegram("❌ Error fetching data.")
                            else:
                                send_telegram("⚠️ Please use format: /trend BTC")
        except Exception as e:
            pass
        time.sleep(2)

# ---------------- INDICATORS ----------------
def calculate_indicators(df):
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['tr'] = pd.concat([df['high'] - df['low'], abs(df['high'] - df['close'].shift()), abs(df['low'] - df['close'].shift())], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(window=14).mean()
    return df

# ---------------- MARKET SCANNER ----------------
def scan_market():
    print("Scanning CoinDCX (Ultimate Mode)...")
    try:
        data = get_ticker_data()
        if not data:
            print("No data from CoinDCX, waiting...")
            return

        all_coins = []
        for c in data:
            if not isinstance(c, dict): continue
            market = str(c.get('market', ''))
            # FIX: Check if USDT or INR is anywhere in the name
            if 'USDT' in market or 'INR' in market:
                try:
                    if float(c.get('volume', 0)) > 20000 and market not in active_trades:
                        all_coins.append(market)
                except: pass
        
        print(f"Scanning {len(all_coins)} coins...")

        for sym in all_coins:
            try:
                # Agar sym mein underscore nahi hai, toh candle fetch ke liye format theek karo
                candle_sym = sym
                if '_' not in candle_sym and 'USDT' in candle_sym:
                    candle_sym = candle_sym.replace('USDT', '_USDT')
                    if not candle_sym.startswith('B-') and not candle_sym.startswith('I-'):
                        candle_sym = 'B-' + candle_sym
                elif '_' not in candle_sym and 'INR' in candle_sym:
                    candle_sym = candle_sym.replace('INR', '_INR')
                    if not candle_sym.startswith('B-') and not candle_sym.startswith('I-'):
                        candle_sym = 'I-' + candle_sym

                k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={candle_sym}&interval=15m&limit=200", headers=headers, timeout=10)
                k_data = k_res.json()
                if not isinstance(k_data, list) or len(k_data) < 200: continue
                k_data.reverse() 
                df_15m = pd.DataFrame(k_data)
                
                for col in ['close', 'high', 'low', 'volume']: 
                    df_15m[col] = df_15m[col].astype(float)
                
                df_15m = calculate_indicators(df_15m)
                last = df_15m.iloc[-1]
                prev = df_15m.iloc[-2]
                
                current_price = last['close']
                ema200 = last['ema200']
                rsi = last['rsi']
                macd = last['macd']
                prev_macd = prev['macd']
                atr = last['atr']

                avg_vol = df_15m['volume'].tail(20).mean()
                vol_spike = last['volume'] > (avg_vol * 1.2)
                macd_cross_up = (prev_macd < 0 and macd > 0) or (df_15m.iloc[-3]['macd'] < 0 and prev_macd > 0)
                macd_cross_down = (prev_macd > 0 and macd < 0) or (df_15m.iloc[-3]['macd'] > 0 and prev_macd < 0)

                signal = None
                
                if (macd_cross_up and vol_spike) or (macd_cross_down and vol_spike):
                    h4_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={candle_sym}&interval=4h&limit=100", headers=headers, timeout=10)
                    h4_data = h4_res.json()
                    if not isinstance(h4_data, list) or len(h4_data) < 50: continue
                    h4_data.reverse()
                    h4_closes = [float(c['close']) for c in h4_data]
                    h4_ema50 = pd.Series(h4_closes).ewm(span=50, adjust=False).mean().iloc[-1]
                    
                    if macd_cross_up and vol_spike:
                        if current_price > ema200 and 35 < rsi < 75 and h4_closes[-1] > h4_ema50:
                            signal = "BUY"
                    elif macd_cross_down and vol_spike:
                        if current_price < ema200 and 25 < rsi < 65 and h4_closes[-1] < h4_ema50:
                            signal = "SELL"

                if signal:
                    entry = current_price
                    risk = atr * 1.5 
                    
                    if signal == "BUY":
                        sl, tp1, tp2, tp3 = entry - risk, entry + (risk * 1.5), entry + (risk * 3.0), entry + (risk * 4.5)
                    else:
                        sl, tp1, tp2, tp3 = entry + risk, entry - (risk * 1.5), entry - (risk * 3.0), entry - (risk * 4.5)

                    active_trades[sym] = {
                        'type': signal, 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3, 'status': 'OPEN'
                    }

                    clean_sym = sym.replace("B-", "").replace("I-", "").replace("_", "")
                    dcx_link = f"https://coindcx.com/trade/{clean_sym}"
                    market_type = "INR" if "INR" in sym else "USDT"

                    text = (
                        f"🎯 *SNIPER {signal} SIGNAL ({market_type})* 🎯\n\n"
                        f"🪙 *Coin:* [{clean_sym}]({dcx_link})\n"
                        f"💰 *Entry:* {entry:.4f}\n"
                        f"🛑 *SL:* {sl:.4f}\n"
                        f"🎯 *TP1 (1:1.5):* {tp1:.4f}\n"
                        f"🎯 *TP2 (1:3):* {tp2:.4f}\n"
                        f"🎯 *TP3 (1:4.5):* {tp3:.4f}\n"
                        f"📊 *RSI:* {rsi:.2f} | *4H Trend:* Confirmed ✅\n"
                        f"⏱️ *TF:* 15m\n\n"
                        f"💡 _Bot is now tracking this trade. You will get alerts for TP/SL hits._"
                    )
                    
                    send_telegram(text)
                    print(f"Sniper Signal Sent: {clean_sym} {signal}")
                    
            except Exception as e:
                pass
            
            time.sleep(0.5) 
            
    except Exception as e:
        print("Scan Error:", e)

if __name__ == "__main__":
    keep_alive()
    print("Ultimate Bot Started!")
    
    Thread(target=monitor_trades).start()
    Thread(target=telegram_commands).start()
    
    while True:
        scan_market()
        time.sleep(300)
