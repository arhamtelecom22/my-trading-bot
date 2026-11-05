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
    return "CoinDCX Bot is Running!"

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
                        send_telegram(f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {curr_price:.4f}")
                        trade_history.append({'type': 'BUY', 'result': 'LOSS', 'date': datetime.datetime.now().strftime("%Y-%m-%d")})
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
                        trade_history.append({'type': 'BUY', 'result': 'WIN', 'date': datetime.datetime.now().strftime("%Y-%m-%d")})
                        del active_trades[sym]

                elif signal == "SELL":
                    if curr_price >= sl:
                        send_telegram(f"❌ *{clean_sym} Hit STOP LOSS*\nPrice: {curr_price:.4f}")
                        trade_history.append({'type': 'SELL', 'result': 'LOSS', 'date': datetime.datetime.now().strftime("%Y-%m-%d")})
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
                        trade_history.append({'type': 'SELL', 'result': 'WIN', 'date': datetime.datetime.now().strftime("%Y-%m-%d")})
                        del active_trades[sym]
        except: pass
        time.sleep(15)

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
                win_rate = (wins / (wins+losses) * 100) if (wins+losses) > 0 else 0
                send_telegram(f"📅 *Daily Report ({today})*\n\n🟢 Wins: {wins}\n🔴 Losses: {losses}\n📊 *Win Rate:* {win_rate:.1f}%")
        time.sleep(60)

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
                        if text in ["/start", "/menu"]:
                            markup = {"inline_keyboard": [[{"text": "📊 Status", "callback_data": "/status"}, {"text": "🏆 Top Coins", "callback_data": "/top"}], [{"text": "📈 Active Trades", "callback_data": "/trades"}, {"text": "📅 Report", "callback_data": "/report"}]]}
                            send_telegram("👋 *Welcome!*\nSelect an option:", reply_markup=markup)
                        
                        elif text == "/status":
                            send_telegram(f"🤖 *Bot Running*\nActive Trades: {len(active_trades)}")
                        
                        elif text == "/trades":
                            if not active_trades: send_telegram("💤 *No active trades.*")
                            else:
                                t_text = "📈 *Active Trades:*\n\n"
                                for s, t in active_trades.items():
                                    t_text += f"🪙 *{s.replace('B-','').replace('I-','').replace('_','')}* ({t['type']})\nEntry: {t['entry']:.4f} | SL: {t['sl']:.4f}\n\n"
                                send_telegram(t_text)
                        
                        elif text == "/report":
                            today = datetime.datetime.now().strftime("%Y-%m-%d")
                            today_t = [t for t in trade_history if t['date'] == today]
                            w = sum(1 for t in today_t if t['result'] == 'WIN')
                            l = sum(1 for t in today_t if t['result'] == 'LOSS')
                            send_telegram(f"📅 *Today:* Wins: {w} | Losses: {l}")
                        
                        elif text == "/top":
                            send_telegram("⏳ Fetching top movers with prices...")
                            try:
                                data = get_ticker_data()
                                valid = []
                                for c in data:
                                    if isinstance(c, dict):
                                        m = str(c.get('market'))
                                        if 'USDT' in m or 'INR' in m:
                                            ch = float(c.get('change24hour', 0))
                                            pr = float(c.get('last_price', 0))
                                            valid.append({'m': m, 'c': ch, 'p': pr})
                                
                                top = sorted(valid, key=lambda x: x['c'], reverse=True)[:5]
                                msg = "🏆 <b>Top 5 Gainers (24h)</b>\n\n"
                                
                                for i, c in enumerate(top): 
                                    clean_sym = c['m'].replace('B-','').replace('I-','').replace('_','')
                                    msg += f"{i+1}. <b>{clean_sym}</b>\n"
                                    msg += f"📈 Change: +{c['c']:.2f}%\n"
                                    msg += f"💰 Price: {c['p']}\n\n"
                                    
                                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"})
                            except: send_telegram("❌ API Error while fetching top coins.")
        except: pass
        time.sleep(2)

def calculate_indicators(df):
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['tr'] = pd.concat([df['high'] - df['low'], abs(df['high'] - df['close'].shift()), abs(df['low'] - df['close'].shift())], axis=1).max(axis=1)
    df['atr'] = df['tr'].rolling(window=14).mean()
    return df

def scan_market():
    try:
        data = get_ticker_data()
        if not data: return
        all_coins = [str(c.get('market', '')) for c in data if isinstance(c, dict) and ('USDT' in str(c.get('market', '')) or 'INR' in str(c.get('market', ''))) and float(c.get('volume', 0)) > 20000]
        
        for sym in all_coins:
            if sym in active_trades: continue
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
                current_price, ema200, rsi, macd, prev_macd, atr = last['close'], last['ema200'], last['rsi'], last['macd'], prev['macd'], last['atr']
                vol_spike = last['volume'] > (df['volume'].tail(20).mean() * 1.2)
                macd_up = (prev_macd < 0 and macd > 0) or (df.iloc[-3]['macd'] < 0 and prev_macd > 0)
                macd_down = (prev_macd > 0 and macd < 0) or (df.iloc[-3]['macd'] > 0 and prev_macd < 0)

                signal = None
                if (macd_up and vol_spike) or (macd_down and vol_spike):
                    h4 = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval=4h&limit=100", headers=headers, timeout=5).json()
                    if isinstance(h4, list) and len(h4) >= 50:
                        h4.reverse()
                        h4_ema50 = pd.Series([float(c['close']) for c in h4]).ewm(span=50, adjust=False).mean().iloc[-1]
                        if macd_up and vol_spike and current_price > ema200 and 35 < rsi < 75 and float(h4[-1]['close']) > h4_ema50: signal = "BUY"
                        elif macd_down and vol_spike and current_price < ema200 and 25 < rsi < 65 and float(h4[-1]['close']) < h4_ema50: signal = "SELL"

                if signal:
                    entry, risk = current_price, atr * 1.5 
                    if signal == "BUY": sl, tp1, tp2, tp3 = entry - risk, entry + (risk * 1.5), entry + (risk * 3.0), entry + (risk * 4.5)
                    else: sl, tp1, tp2, tp3 = entry + risk, entry - (risk * 1.5), entry - (risk * 3.0), entry - (risk * 4.5)

                    active_trades[sym] = {'type': signal, 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3, 'status': 'OPEN'}
                    clean_sym = sym.replace("B-", "").replace("I-", "").replace("_", "")
                    
                    text = (f"🎯 *SNIPER {signal} SIGNAL*\n\n🪙 *Coin:* [{clean_sym}](https://coindcx.com/trade/{clean_sym})\n"
                            f"💰 *Entry:* {entry:.4f}\n🛑 *SL:* {sl:.4f}\n"
                            f"🎯 *TP1:* {tp1:.4f}\n🎯 *TP2:* {tp2:.4f}\n🎯 *TP3:* {tp3:.4f}\n"
                            f"⏱️ *TF:* 15m\n\n💡 _Trailing SL Active._")
                    
                    send_telegram(text)
            except: pass
            time.sleep(0.5)
    except: pass

if __name__ == "__main__":
    keep_alive()
    Thread(target=monitor_trades).start()
    Thread(target=telegram_commands).start()
    Thread(target=daily_report_loop).start()
    while True:
        scan_market()
        time.sleep(300)
