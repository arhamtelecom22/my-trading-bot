import requests
import time
import pandas as pd
from flask import Flask
from threading import Thread

# ================= APNI DETAILS YAHAN DAALO =================
TG_TOKEN = "YOUR_BOT_TOKEN"   # Yahan apna Bot Token daalo
TG_CHAT_ID = "YOUR_CHAT_ID"   # Yahan apni Chat ID daalo
# ============================================================

app = Flask('')

@app.route('/')
def home():
    return "CoinDCX Pro Scanner (USDT + INR) is Running 24/7!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("TG Error:", e)

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

def scan_market():
    print("Scanning CoinDCX (USDT & INR)...")
    try:
        res = requests.get("https://api.coindcx.com/exchange/ticker", timeout=10)
        data = res.json()
        
        all_coins = []
        for c in data:
            # Yahan humne USDT aur INR dono add kar diye hain
            if c['market'].endswith("_USDT") or c['market'].endswith("_INR"):
                try:
                    if float(c.get('volume', 0)) > 20000:
                        all_coins.append(c['market'])
                except: pass
        
        print(f"Scanning {len(all_coins)} coins (INR + USDT)...")

        for sym in all_coins:
            try:
                k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={sym}&interval=15m&limit=200", timeout=10)
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
                vol_spike = last['volume'] > (avg_vol * 1.5)
                macd_cross_up = prev_macd < 0 and macd > 0
                macd_cross_down = prev_macd > 0 and macd < 0

                signal = None
                
                if macd_cross_up and vol_spike:
                    h1_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={sym}&interval=1h&limit=100", timeout=10)
                    h1_data = h1_res.json()
                    if isinstance(h1_data, list) and len(h1_data) > 50:
                        h1_data.reverse()
                        h1_closes = [float(c['close']) for c in h1_data]
                        h1_ema50 = pd.Series(h1_closes).ewm(span=50, adjust=False).mean().iloc[-1]
                        if current_price > ema200 and 40 < rsi < 70 and h1_closes[-1] > h1_ema50:
                            signal = "BUY"
                
                elif macd_cross_down and vol_spike:
                    h1_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={sym}&interval=1h&limit=100", timeout=10)
                    h1_data = h1_res.json()
                    if isinstance(h1_data, list) and len(h1_data) > 50:
                        h1_data.reverse()
                        h1_closes = [float(c['close']) for c in h1_data]
                        h1_ema50 = pd.Series(h1_closes).ewm(span=50, adjust=False).mean().iloc[-1]
                        if current_price < ema200 and 30 < rsi < 60 and h1_closes[-1] < h1_ema50:
                            signal = "SELL"

                if signal:
                    entry = current_price
                    risk = atr * 1.5 
                    
                    if signal == "BUY":
                        sl = entry - risk
                        tp1 = entry + (risk * 1.5)
                        tp2 = entry + (risk * 3.0)
                        tp3 = entry + (risk * 4.5)
                    else:
                        sl = entry + risk
                        tp1 = entry - (risk * 1.5)
                        tp2 = entry - (risk * 3.0)
                        tp3 = entry - (risk * 4.5)

                    # Yahan humne I- ko bhi replace kar diya INR ke liye
                    clean_sym = sym.replace("B-", "").replace("I-", "").replace("_", "")
                    dcx_link = f"https://coindcx.com/trade/{clean_sym}"
                    
                    market_type = "INR" if "_INR" in sym else "USDT"

                    text = (
                        f"🔥 *PRO {signal} SIGNAL ({market_type})* 🔥\n\n"
                        f"🪙 *Coin:* [{clean_sym}]({dcx_link})\n"
                        f"💰 *Entry:* {entry:.4f}\n"
                        f"🛑 *SL:* {sl:.4f}\n"
                        f"🎯 *TP1 (1:1.5):* {tp1:.4f}\n"
                        f"🎯 *TP2 (1:3):* {tp2:.4f}\n"
                        f"🎯 *TP3 (1:4.5):* {tp3:.4f}\n"
                        f"📊 *RSI:* {rsi:.2f} | *1H Trend:* Confirmed ✅\n"
                        f"⏱️ *TF:* 15m\n\n"
                        f"💡 _Strategy: Book 50% at TP1, Move SL to Entry. Book 25% at TP2, let 25% run to TP3._"
                    )
                    
                    send_telegram(text)
                    print(f"PRO Signal Sent: {clean_sym} {signal} ({market_type})")
                    
            except Exception as e:
                pass
            
            time.sleep(0.5) 
            
    except Exception as e:
        print("Scan Error:", e)

if __name__ == "__main__":
    keep_alive()
    print("Pro Bot Started!")
    while True:
        scan_market()
        time.sleep(300) 
