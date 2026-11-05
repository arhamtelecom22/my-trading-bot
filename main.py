import os
import requests
import time
import pandas as pd
import mplfinance as mpf
import io
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
    return "CoinDCX Ultimate V4 Bot is Running 24/7!"

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
    except Exception as e:
        print("TG Error:", e)

def send_telegram_photo(image_bytes, caption):
    if not TG_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    files = {'photo': ('chart.png', image_bytes, 'image/png')}
    data = {"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "Markdown"}
    try:
        requests.post(url, files=files, data=data)
    except Exception as e:
        print("TG Photo Error:", e)

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# ---------------- SMART CACHE ----------------
last_ticker_data = []
last_ticker_time = 0

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

# ---------------- TRADE TRACKER & STATS ----------------
active_trades = {}
trade_history = []

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
                signal, entry = trade['type'], trade['entry']
                sl, tp1, tp2, tp3 = trade['sl'], trade['tp1'], trade['tp2'], trade['tp3']
                clean_sym = sym.replace("B-", "").replace("I-", "").replace("_", "")

                if signal == "BUY":
                    if curr_price <= sl:
                        send_telegram(f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {curr_price:.4f}\nTrade Closed.")
                        trade_history.append({'type': 'BUY', 'result': 'LOSS', 'date': datetime.datetime.now().strftime("%Y-%m-%d")})
                        del active_trades[sym]
                    elif curr_price >= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry 
                        send_telegram(f"✅ *{clean_sym} Hit TP1*\nPrice: {curr_price:.4f}\n_Book 50% profit. SL moved to Entry (Risk-Free)._")
                        trade['status'] = "TP1_HIT"
                    elif curr_price >= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1 
                        send_telegram(f"🔥 *{clean_sym} Hit TP2*\nPrice: {curr_price:.4f}\n_Book 25% more. SL moved to TP1._")
                        trade['status'] = "TP2_HIT"
                    elif curr_price >= tp3:
                        send_telegram(f"🚀 *{clean_sym} Hit TP3!*\nPrice: {curr_price:.4f}\n_Trade Complete._")
                        trade_history.append({'type': 'BUY', 'result': 'WIN', 'date': datetime.datetime.now().strftime("%Y-%m-%d")})
                        del active_trades[sym]

                elif signal == "SELL":
                    if curr_price >= sl:
                        send_telegram(f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {curr_price:.4f}\nTrade Closed.")
                        trade_history.append({'type': 'SELL', 'result': 'LOSS', 'date': datetime.datetime.now().strftime("%Y-%m-%d")})
                        del active_trades[sym]
                    elif curr_price <= tp1 and trade['status'] == "OPEN":
                        trade['sl'] = entry 
                        send_telegram(f"✅ *{clean_sym} Hit TP1*\nPrice: {curr_price:.4f}\n_Book 50% profit. SL moved to Entry (Risk-Free)._")
                        trade['status'] = "TP1_HIT"
                    elif curr_price <= tp2 and trade['status'] == "TP1_HIT":
                        trade['sl'] = tp1 
                        send_telegram(f"🔥 *{clean_sym} Hit TP2*\nPrice: {curr_price:.4f}\n_Book 25% more. SL moved to TP1._")
                        trade['status'] = "TP2_HIT"
                    elif curr_price <= tp3:
                        send_telegram(f"🚀 *{clean_sym} Hit TP3!*\nPrice: {curr_price:.4f}\n_Trade Complete._")
                        trade_history.append({'type': 'SELL', 'result': 'WIN', 'date': datetime.datetime.now().strftime("%Y-%m-%d")})
                        del active_trades[sym]
        except Exception as e: pass
        time.sleep(15)

# ---------------- DAILY REPORT LOOP ----------------
def daily_report_loop():
    global trade_history
    last_report_date = ""
    while True:
        now = datetime.datetime.now()
        if now.hour == 21 and now.minute == 0 and last_report_date != now.strftime("%Y-%m-%d"):
            last_report_date = now.strftime("%Y-%m-%d")
            today = now.strftime("%Y-%m-%d")
            todays_trades = [t for t in trade_history if t['date'] == today]
            
            if not todays_trades:
                send_telegram(f"📅 *Daily Report ({today})*\n\nAaj koi trade close nahi hui.")
            else:
                wins = sum(1 for t in todays_trades if t['result'] == 'WIN')
                losses = sum(1 for t in todays_trades if t['result'] == 'LOSS')
                total = wins + losses
                win_rate = (wins / total * 100) if total > 0 else 0
                
                msg = (f"📅 *Daily Report ({today})*\n\n"
                       f"🟢 Wins (TP Hits): {wins}\n"
                       f"🔴 Losses (SL Hits): {losses}\n"
                       f"📊 *Win Rate:* {win_rate:.1f}%\n\n"
                       f"Keep trading smart! 🚀")
                send_telegram(msg)
        time.sleep(60)

# ---------------- CHART GENERATOR (CANDLESTICK) ----------------
def generate_chart_image(df, entry, sl, tp1, tp2, tp3, clean_sym, signal):
    try:
        df_plot = df.tail(50).copy()
        
        # Time format theek karo
        df_plot['time'] = pd.to_datetime(df_plot['time'], unit='ms')
        df_plot.set_index('time', inplace=True)
        
        # Rename columns for mplfinance
        df_plot.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
        
        # Horizontal lines (Entry, SL, TP)
        hlines = dict(hlines=[entry, sl, tp1, tp2, tp3],
                      colors=['blue', 'red', 'green', 'green', 'green'],
                      linestyle='--',
                      linewidths=1.5)
        
        buf = io.BytesIO()
        mpf.plot(df_plot, type='candle', style='yahoo', title=f"{clean_sym} - {signal}",
                 hlines=hlines, volume=True, savefig=buf, figsize=(10, 6))
        buf.seek(0)
        return buf
    except Exception as e:
        print("Chart Error:", e)
        return None

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
                        callback_data = update["callback_query"]["data"]
                        text = callback_data 
                        chat_id = update["callback_query"]["message"]["chat"]["id"]
                    else:
                        msg = update.get("message", {})
                        text = msg.get("text", "")
                        chat_id = msg.get("chat", {}).get("id")
                    
                    if str(chat_id) == str(TG_CHAT_ID):
                        if text == "/start" or text == "/menu":
                            markup = {
                                "inline_keyboard": [
                                    [{"text": "📊 Status", "callback_data": "/status"}, {"text": "🏆 Top Coins", "callback_data": "/top"}],
                                    [{"text": "📈 Active Trades", "callback_data": "/trades"}, {"text": "📅 Today's Report", "callback_data": "/report"}]
                                ]
                            }
                            send_telegram("👋 *Welcome to Ultimate Bot!*\nSelect an option below:", reply_markup=markup)
                            
                        elif text == "/status":
                            send_telegram(f"🤖 *Bot Status: RUNNING*\nActive Trades: {len(active_trades)}")
                            
                        elif text == "/trades":
                            if not active_trades:
                                send_telegram("💤 *No active trades right now.*")
                            else:
                                t_text = "📈 *Active Trades:*\n\n"
                                for s, t in active_trades.items():
                                    c_s = s.replace("B-", "").replace("I-", "").replace("_", "")
                                    t_text += f"🪙 *{c_s}* ({t['type']})\nEntry: {t['entry']:.4f} | SL: {t['sl']:.4f}\nStatus: {t['status']}\n\n"
                                send_telegram(t_text)
                        
                        elif text == "/report":
                            today = datetime.datetime.now().strftime("%Y-%m-%d")
                            todays = [t for t in trade_history if t['date'] == today]
                            wins = sum(1 for t in todays if t['result'] == 'WIN')
                            losses = sum(1 for t in todays if t['result'] == 'LOSS')
                            send_telegram(f"📅 *Today's Report*\nWins: {wins} | Losses: {losses}")
                            
                        elif text == "/top":
                            send_telegram("⏳ Fetching top movers...")
                            try:
                                data = get_ticker_data()
                                valid_coins = [{'market': str(c.get('market')), 'change': float(c.get('change24hour', 0))} 
                                               for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market')) or 'INR' in str(c.get('market')))]
                                top = sorted(valid_coins, key=lambda x: x['change'], reverse=True)[:5]
                                t_text = "🏆 <b>Top 5 Gainers (24h)</b>\n\n"
                                for idx, c in enumerate(top):
                                    sym = c['market'].replace("B-", "").replace("I-", "").replace("_", "")
                                    t_text += f"{idx+1}. <b>{sym}</b>: {c['change']:.2f}%\n"
                                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                                requests.post(url, json={"chat_id": TG_CHAT_ID, "text": t_text, "parse_mode": "HTML"})
                            except: send_telegram("❌ API Error")
        except Exception as e: pass
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
    print("Scanning Market...")
    try:
        data = get_ticker_data()
        if not data: return

        all_coins = []
        for c in data:
            if not isinstance(c, dict): continue
            m = str(c.get('market', ''))
            if 'USDT' in m or 'INR' in m:
                try:
                    if float(c.get('volume', 0)) > 20000 and m not in active_trades:
                        all_coins.append(m)
                except: pass

        for sym in all_coins:
            try:
                candle_sym = sym
                if '_' not in candle_sym and 'USDT' in candle_sym:
                    candle_sym = candle_sym.replace('USDT', '_USDT')
                    if not candle_sym.startswith('B-'): candle_sym = 'B-' + candle_sym
                elif '_' not in candle_sym and 'INR' in candle_sym:
                    candle_sym = candle_sym.replace('INR', '_INR')
                    if not candle_sym.startswith('I-'): candle_sym = 'I-' + candle_sym

                k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={candle_sym}&interval=15m&limit=200", headers=headers, timeout=10)
                k_data = k_res.json()
                if not isinstance(k_data, list) or len(k_data) < 200: continue
                k_data.reverse() 
                df_15m = pd.DataFrame(k_data)
                
                for col in ['close', 'high', 'low', 'volume', 'open']: df_15m[col] = df_15m[col].astype(float)
                df_15m = calculate_indicators(df_15m)
                
                last, prev = df_15m.iloc[-1], df_15m.iloc[-2]
                current_price, ema200, rsi, macd, prev_macd, atr = last['close'], last['ema200'], last['rsi'], last['macd'], prev['macd'], last['atr']

                vol_spike = last['volume'] > (df_15m['volume'].tail(20).mean() * 1.2)
                macd_cross_up = (prev_macd < 0 and macd > 0) or (df_15m.iloc[-3]['macd'] < 0 and prev_macd > 0)
                macd_cross_down = (prev_macd > 0 and macd < 0) or (df_15m.iloc[-3]['macd'] > 0 and prev_macd < 0)

                signal = None
                if (macd_cross_up and vol_spike) or (macd_cross_down and vol_spike):
                    h4_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={candle_sym}&interval=4h&limit=100", headers=headers, timeout=10).json()
                    if not isinstance(h4_res, list) or len(h4_res) < 50: continue
                    h4_res.reverse()
                    h4_closes = [float(c['close']) for c in h4_res]
                    h4_ema50 = pd.Series(h4_closes).ewm(span=50, adjust=False).mean().iloc[-1]
                    
                    if macd_cross_up and vol_spike and current_price > ema200 and 35 < rsi < 75 and h4_closes[-1] > h4_ema50:
                        signal = "BUY"
                    elif macd_cross_down and vol_spike and current_price < ema200 and 25 < rsi < 65 and h4_closes[-1] < h4_ema50:
                        signal = "SELL"

                if signal:
                    entry, risk = current_price, atr * 1.5 
                    if signal == "BUY": sl, tp1, tp2, tp3 = entry - risk, entry + (risk * 1.5), entry + (risk * 3.0), entry + (risk * 4.5)
                    else: sl, tp1, tp2, tp3 = entry + risk, entry - (risk * 1.5), entry - (risk * 3.0), entry - (risk * 4.5)

                    active_trades[sym] = {'type': signal, 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3, 'status': 'OPEN'}

                    clean_sym = sym.replace("B-", "").replace("I-", "").replace("_", "")
                    market_type = "INR" if "INR" in sym else "USDT"

                    text = (f"🎯 *SNIPER {signal} SIGNAL ({market_type})* 🎯\n\n"
                            f"🪙 *Coin:* [{clean_sym}](https://coindcx.com/trade/{clean_sym})\n"
                            f"💰 *Entry:* {entry:.4f}\n🛑 *SL:* {sl:.4f}\n"
                            f"🎯 *TP1 (1:1.5):* {tp1:.4f}\n🎯 *TP2 (1:3):* {tp2:.4f}\n🎯 *TP3 (1:4.5):* {tp3:.4f}\n"
                            f"📊 *RSI:* {rsi:.2f} | *4H Trend:* ✅\n⏱️ *TF:* 15m\n\n"
                            f"💡 _Trailing SL Active. Chart below:_")
                    
                    send_telegram(text)
                    
                    chart_buf = generate_chart_image(df_15m, entry, sl, tp1, tp2, tp3, clean_sym, signal)
                    if chart_buf: send_telegram_photo(chart_buf, f"{clean_sym} {signal} Setup")

            except Exception as e: pass
            time.sleep(0.5) 
    except Exception as e: print("Scan Error:", e)

if __name__ == "__main__":
    keep_alive()
    print("Ultimate Bot V4 Started!")
    
    Thread(target=monitor_trades).start()
    Thread(target=telegram_commands).start()
    Thread(target=daily_report_loop).start()
    
    while True:
        scan_market()
        time.sleep(300)
