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
    return "CoinDCX Market Scanner is Running 24/7!"

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
    return df

def scan_market():
    print("Fetching active coins from CoinDCX...")
    try:
        res = requests.get("https://api.coindcx.com/exchange/ticker", timeout=10)
        data = res.json()
        
        all_coins = []
        for c in data:
            if c['market'].endswith("_USDT"):
                try:
                    vol = float(c.get('volume', 0))
                    if vol > 10000:
                        all_coins.append(c['market'])
                except:
                    all_coins.append(c['market'])
        
        print(f"Total {len(all_coins)} CoinDCX coins to scan.")

        for sym in all_coins:
            try:
                k_res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={sym}&interval=15m&limit=200", timeout=10)
                k_data = k_res.json()
                
                if not isinstance(k_data, list) or len(k_data) < 200: 
                    time.sleep(0.2)
                    continue
                
                k_data.reverse()
                
                df = pd.DataFrame(k_data)
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
                    entry = current_price
                    if signal == "BUY":
                        sl = entry * 0.99      
                        tp1 = entry * 1.01     
                        tp2 = entry * 1.02     
                        tp3 = entry * 1.03     
                    else:
                        sl = entry * 1.01      
                        tp1 = entry * 0.99     
                        tp2 = entry * 0.98     
                        tp3 = entry * 0.97     
                    
                    # COINDCX DIRECT LINK
                    clean_sym = sym.replace("B-", "").replace("_", "")
                    dcx_link = f"https://coindcx.com/trade/{clean_sym}"

                    # TELEGRAM MESSAGE
                    text = (
                        f"🚨 *STRONG {signal} (CoinDCX)* 🚨\n\n"
                        f"🪙 *Coin:* [{clean_sym}]({dcx_link})\n"
                        f"💰 *Entry:* {entry:.4f}\n"
                        f"🛑 *SL:* {sl:.4f}\n"
                        f"🎯 *TP1:* {tp1:.4f}\n"
                        f"🎯 *TP2:* {tp2:.4f}\n"
                        f"🎯 *TP3:* {tp3:.4f}\n"
                        f"📊 *RSI:* {rsi:.2f}\n"
                        f"⏱️ *TF:* 15m\n\n"
                        f"_Click the coin name to open CoinDCX chart_"
                    )
                    
                    send_telegram(text)
                    print(f"Signal Sent: {clean_sym} {signal}")
                    
            except Exception as e:
                print(f"Error on {sym}: {e}")
            
            time.sleep(0.4) 
            
    except Exception as e:
        print("Scan Error:", e)

if __name__ == "__main__":
    keep_alive()
    print("Bot Started!")
    while True:
        scan_market()
        print("Full CoinDCX scan complete. Waiting 2 minutes...")
        time.sleep(120)
