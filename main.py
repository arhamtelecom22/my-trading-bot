import requests
import time
import pandas as pd
from flask import Flask
from threading import Thread

# ================= APNI DETAILS YAHAN DAALO =================
TG_TOKEN = "9084884390:AAER1W7o63uWPGu3d5T-NrTZTOIN-In6oPs"   # Yahan apna Bot Token daalo
TG_CHAT_ID = "762295473"   # Yahan apni Chat ID daalo
# ============================================================

app = Flask('')

@app.route('/')
def home():
    return "Market Scanner is Running 24/7!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}
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
    return df

def scan_market():
    print("Fetching ALL active coins from Binance...")
    try:
        res = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=10)
        data = res.json()
        
        # POORA MARKET: Jinka volume $1 Million se zyada hai (taaki dead coins skip ho)
        all_coins = [c['symbol'] for c in data if c['symbol'].endswith("USDT") and float(c['quoteVolume']) > 1000000]
        
        print(f"Total {len(all_coins)} coins to scan.")

        for sym in all_coins:
            try:
                k_res = requests.get(f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=15m&limit=200", timeout=10)
                k_data = k_res.json()
                
                if len(k_data) < 200: 
                    time.sleep(0.2)
                    continue
                
                df = pd.DataFrame(k_data, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'tbbav', 'tbqav', 'ignore'])
                df['close'] = df['close'].astype(float)
                df['volume'] = df['volume'].astype(float)
                
                df = calculate_indicators(df)
                
                last = df.iloc[-1]
                prev = df.iloc[-2]
                
                current_price = last['close']
                ema200 = last['ema200']
                rsi = last['rsi']
                macd = last['macd']
                prev_macd = prev['macd']
                
                avg_vol = df['volume'].tail(20).mean()
                vol_spike = last['volume'] > (avg_vol * 1.5)
                
                macd_cross_up = prev_macd < 0 and macd > 0
                macd_cross_down = prev_macd > 0 and macd < 0
                
                signal = None
                
                if current_price > ema200 and 40 < rsi < 70 and macd_cross_up and vol_spike:
                    signal = "BUY"
                elif current_price < ema200 and 30 < rsi < 60 and macd_cross_down and vol_spike:
                    signal = "SELL"
                    
                if signal:
                    text = f"🚨 *STRONG {signal}* 🚨\n\n🪙 *Coin:* {sym}\n💰 *Price:* {current_price:.4f}\n📊 *RSI:* {rsi:.2f}\n⏱️ *TF:* 15m\n\n_Cloud Bot Signal_"
                    send_telegram(text)
                    print(f"Signal Sent: {sym} {signal}")
                    
            except Exception as e:
                print(f"Error on {sym}: {e}")
            
            # API Ban se bachne ke liye 0.3 second ka break
            time.sleep(0.3) 
            
    except Exception as e:
        print("Scan Error:", e)

if __name__ == "__main__":
    keep_alive()
    print("Bot Started!")
    while True:
        scan_market()
        print("Full market scan complete. Waiting 2 minutes for next round...")
        time.sleep(120) # Poora market scan hone ke baad 2 minute rest
