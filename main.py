import os
import requests
import time
import pandas as pd
import numpy as np
from flask import Flask
from threading import Thread
import json

# ================= KEYS =================
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT_ID = "762295473"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY") 
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") 
# ========================================

app = Flask('')
active_trades = {}
SCAN_TIMEFRAME = "15m"
last_ticker_data = []
last_ticker_time = 0

def fmt(p):
    try: return f"{float(p):.4f}"
    except: return str(p)

# ---------------- BINANCE DATA ----------------
def get_binance_ticker():
    global last_ticker_data, last_ticker_time
    now = time.time()
    if last_ticker_data and (now - last_ticker_time < 60):
        return last_ticker_data
    try:
        res = requests.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10)
        if res.status_code == 200:
            data = res.json()
            # Filter USDT pairs and format
            filtered = [c for c in data if c['symbol'].endswith('USDT')]
            last_ticker_data = filtered
            last_ticker_time = now
            return filtered
    except: pass
    return last_ticker_data if last_ticker_data else []

def get_binance_kline(sym, interval="15m", limit=200):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={sym}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=10).json()
        if not isinstance(res, list): return None
        
        df = pd.DataFrame(res, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'tbbav', 'tbqav', 'ignore'])
        for col in ['open', 'high', 'low', 'close', 'volume']: df[col] = df[col].astype(float)
        return df
    except: pass
    return None

# ---------------- INDICATORS ----------------
def calculate_pro_indicators(df):
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['sma20'] = df['close'].rolling(window=20).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    df['rsi_min'] = df['rsi'].rolling(14).min()
    df['rsi_max'] = df['rsi'].rolling(14).max()
    df['stoch_rsi'] = (df['rsi'] - df['rsi_min']) / (df['rsi_max'] - df['rsi_min'])
    
    df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    df['ha_open'] = (df['open'].shift(1) + df['close'].shift(1)) / 2
    df['ha_bullish'] = df['ha_close'] > df['ha_open']
    
    df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
    df['obv_ema'] = df['obv'].ewm(span=20, adjust=False).mean()
    return df

# ---------------- TELEGRAM ----------------
def send_msg(text, markup=None):
    if not TG_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    if markup: payload["reply_markup"] = markup
    try: requests.post(url, json=payload, timeout=10)
    except: pass

def send_photo(img, caption, markup=None):
    if not TG_TOKEN or not img: 
        return send_msg(caption, markup)
    try:
        data = {"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
        if markup: data["reply_markup"] = json.dumps(markup)
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto", files={'photo': ('c.png', img, 'image/png')}, data=data, timeout=15)
    except: 
        send_msg(caption, markup)

# ---------------- SCANNER ----------------
def scan_market(is_manual=False):
    print("Scanning Binance...")
    data = get_binance_ticker()
    if not data: 
        if is_manual: send_msg("❌ Failed to fetch data from Binance.")
        return
    
    # Get top 30 by volume
    valid = [c for c in data if float(c.get('quoteVolume', 0)) > 10000000]
    valid = sorted(valid, key=lambda x: float(x.get('quoteVolume', 0)), reverse=True)[:30]
    
    found = 0
    for c in valid:
        sym = c['symbol']
        if sym in active_trades: continue
        
        try:
            df = get_binance_kline(sym, "15m", 200)
            if df is None or len(df) < 200: continue
            
            df = calculate_pro_indicators(df)
            last = df.iloc[-1]
            
            buy_score, sell_score = 0, 0
            if last['close'] > last['ema200']: buy_score += 1
            if last['close'] < last['ema200']: sell_score += 1
            if last['close'] > last['kijun']: buy_score += 1
            if last['close'] < last['kijun']: sell_score += 1
            if last['ha_bullish']: buy_score += 1
            else: sell_score += 1
            if last['macd'] > last['macd_signal']: buy_score += 1
            if last['macd'] < last['macd_signal']: sell_score += 1
            if last['rsi'] > 50 and last['stoch_rsi'] > 0.5: buy_score += 1
            if last['rsi'] < 50 and last['stoch_rsi'] < 0.5: sell_score += 1
            if last['close'] > last['sma20']: buy_score += 1
            if last['close'] < last['sma20']: sell_score += 1
            if last['obv'] > last['obv_ema']: buy_score += 1
            if last['obv'] < last['obv_ema']: sell_score += 1
            
            sig, score = None, 0
            if buy_score >= 6 and last['close'] > last['open']: 
                sig, score = "BUY", buy_score
            elif sell_score >= 6 and last['close'] < last['open']: 
                sig, score = "SELL", sell_score
                
            if sig:
                entry = last['close']
                risk = (last['high'] - last['low']) * 1.5
                if sig == "BUY":
                    sl, tp1, tp2, tp3 = entry - risk, entry + (risk*2), entry + (risk*3), entry + (risk*4)
                else:
                    sl, tp1, tp2, tp3 = entry + risk, entry - (risk*2), entry - (risk*3), entry - (risk*4)
                    
                clean_sym = sym.replace("USDT", "")
                
                text = (
                    f"<b>🔥 #{clean_sym} {sig} (PRO)</b>\n\n"
                    f"Entry: {fmt(entry)}\nSL: {fmt(sl)}\nTP1: {fmt(tp1)}\nTP2: {fmt(tp2)}\nTP3: {fmt(tp3)}\n\n"
                    f"📊 <b>Confluence:</b> {score}/7\n"
                    f"⏱ TF: 15m"
                )
                
                markup = {"inline_keyboard": [[{"text": f"📋 Copy", "copy_text": {"text": clean_sym}}], [{"text": "📈 Open Binance", "url": f"https://www.binance.com/en/trade/{clean_sym}_USDT?type=spot"}], [{"text": "❌ Close", "callback_data": f"close_{sym}"}]]}
                
                # Send text FIRST
                send_msg(text, markup)
                
                # Try Chart
                try:
                    df_chart = df.tail(30)
                    c_data = [{"x": str(i), "o": float(r.open), "h": float(r.high), "l": float(r.low), "c": float(r.close)} for i, r in enumerate(df_chart.itertuples())]
                    max_x = len(c_data) - 1
                    if max_x > 1:
                        ann = {"entry": {"type": "line", "yMin": entry, "yMax": entry, "borderColor": "#4a9eff", "borderWidth": 3}}
                        if sig == "BUY":
                            ann['profit'] = {"type": "box", "yMin": entry, "yMax": tp1, "backgroundColor": "rgba(0,200,100,0.05)", "borderColor": "rgba(0,200,100,0.4)", "xMin": 0, "xMax": max_x}
                            ann['loss'] = {"type": "box", "yMin": sl, "yMax": entry, "backgroundColor": "rgba(255,60,60,0.05)", "borderColor": "rgba(255,60,60,0.4)", "xMin": 0, "xMax": max_x}
                        else:
                            ann['profit'] = {"type": "box", "yMin": tp1, "yMax": entry, "backgroundColor": "rgba(0,200,100,0.05)", "borderColor": "rgba(0,200,100,0.4)", "xMin": 0, "xMax": max_x}
                            ann['loss'] = {"type": "box", "yMin": entry, "yMax": sl, "backgroundColor": "rgba(255,60,60,0.05)", "borderColor": "rgba(255,60,60,0.4)", "xMin": 0, "xMax": max_x}
                        cfg = {"type": "candlestick", "data": {"datasets": [{"data": c_data, "color": {"up": "#00c864", "down": "#ff3c3c"}}]}, "options": {"scales": {"x": {"display": False}, "y": {"position": "right", "ticks": {"color": "#fff"}}}, "plugins": {"legend": {"display": False}, "annotation": {"annotations": ann}}}}
                        q_res = requests.post("https://quickchart.io/chart", json={"chart": cfg, "width": 800, "height": 450, "backgroundColor": "#131722", "version": "3"}, timeout=10)
                        if q_res.status_code == 200:
                            send_photo(q_res.content, f"📈 <b>{clean_sym} Chart</b>")
                except: pass
                
                active_trades[sym] = {'type': sig, 'entry': entry, 'sl': sl, 'tp1': tp1}
                found += 1
                time.sleep(2)
                
        except Exception as e:
            print(f"Scan error on {sym}:", e)
            time.sleep(1)
            
    if is_manual:
        send_msg(f"✅ Scan Complete. Found {found} signals.")

def bot_loop():
    while True:
        scan_market(False)
        time.sleep(300)

# ---------------- MONITOR ----------------
def monitor():
    while True:
        try:
            data = get_binance_ticker()
            prices = {t['symbol']: float(t['lastPrice']) for t in data}
            for sym, t in list(active_trades.items()):
                if sym in prices:
                    p = prices[sym]
                    if (t['type'] == "BUY" and p <= t['sl']) or (t['type'] == "SELL" and p >= t['sl']):
                        send_msg(f"❌ <b>{sym.replace('USDT','')} Hit STOP LOSS</b>\nPrice: {fmt(p)}")
                        del active_trades[sym]
                    elif (t['type'] == "BUY" and p >= t['tp1']) or (t['type'] == "SELL" and p <= t['tp1']):
                        send_msg(f"✅ <b>{sym.replace('USDT','')} Hit TP1</b>\nPrice: {fmt(p)}")
                        del active_trades[sym]
        except: pass
        time.sleep(20)

# ---------------- COMMANDS ----------------
def commands():
    offset = 0
    while True:
        try:
            res = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates?offset={offset}&timeout=30", timeout=35).json()
            if res.get("ok") and res["result"]:
                for u in res["result"]:
                    offset = u["update_id"] + 1
                    
                    if "callback_query" in u:
                        cb_id = u["callback_query"]["id"]
                        txt = u["callback_query"]["data"]
                        cid = u["callback_query"]["message"]["chat"]["id"]
                        
                        if str(cid) == str(TG_CHAT_ID):
                            if txt.startswith("close_"):
                                sym = txt.replace("close_", "")
                                if sym in active_trades: del active_trades[sym]
                                send_msg(f"🛑 Trade Manually Closed.")
                            elif txt == "scan":
                                send_msg("⏳ Manual scan on Binance starting...")
                                Thread(target=scan_market, args=(True,)).start()
                            elif txt == "trades":
                                if not active_trades: send_msg("💤 No active trades.")
                                else:
                                    for s, t in active_trades.items():
                                        send_msg(f"🪙 <b>{s.replace('USDT','')}</b> ({t['type']})\nEntry: {fmt(t['entry'])}", {"inline_keyboard": [[{"text": "❌ Close", "callback_data": f"close_{s}"}]]})
                                        time.sleep(0.5)
                        
                        requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/answerCallbackQuery?callback_query_id={cb_id}")
                        continue
                    
                    txt = u.get("message", {}).get("text", "")
                    cid = u.get("message", {}).get("chat", {}).get("id")
                    
                    if str(cid) == str(TG_CHAT_ID):
                        if txt in ["/start", "/menu"]:
                            markup = {"inline_keyboard": [[{"text": "🚀 SCAN NOW (Binance)", "callback_data": "scan"}], [{"text": "📊 Active Trades", "callback_data": "trades"}]]}
                            send_msg("👋 <b>Welcome to V56 (Binance Data)!</b>\nBot is scanning the best Binance pairs.", markup)
                        elif txt == "/top":
                            data = get_binance_ticker()
                            valid = [{'m': c['symbol'], 'c': float(c.get('priceChangePercent', 0))} for c in data]
                            top = sorted(valid, key=lambda x: x['c'], reverse=True)[:5]
                            msg = "🏆 <b>Top Gainers</b>\n\n"
                            for i, c in enumerate(top): msg += f"{i+1}. {c['m'].replace('USDT','')}: {c['c']:+.2f}%\n"
                            send_msg(msg)
                        elif txt == "/bottom":
                            data = get_binance_ticker()
                            valid = [{'m': c['symbol'], 'c': float(c.get('priceChangePercent', 0))} for c in data]
                            bot = sorted(valid, key=lambda x: x['c'], reverse=False)[:5]
                            msg = "📉 <b>Top Losers</b>\n\n"
                            for i, c in enumerate(bot): msg += f"{i+1}. {c['m'].replace('USDT','')}: {c['c']:+.2f}%\n"
                            send_msg(msg)
        except: pass
        time.sleep(2)

if __name__ == "__main__":
    keep_alive = lambda: Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    keep_alive()
    Thread(target=monitor).start()
    Thread(target=commands).start()
    Thread(target=bot_loop).start()
