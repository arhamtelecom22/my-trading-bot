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

def fmt(p):
    try: return f"{float(p):.4f}"
    except: return str(p)

# ---------------- INDICATORS ----------------
def calculate_pro_indicators(df):
    # 1. EMA 200
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # 2. MACD
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    # 3. Bollinger Bands
    df['sma20'] = df['close'].rolling(window=20).mean()
    df['std20'] = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['sma20'] + (df['std20'] * 2)
    df['bb_lower'] = df['sma20'] - (df['std20'] * 2)
    
    # 4. RSI & Stoch RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    df['rsi_min'] = df['rsi'].rolling(14).min()
    df['rsi_max'] = df['rsi'].rolling(14).max()
    df['stoch_rsi'] = (df['rsi'] - df['rsi_min']) / (df['rsi_max'] - df['rsi_min'])
    
    # 5. Heiken Ashi
    df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    df['ha_open'] = (df['open'].shift(1) + df['close'].shift(1)) / 2
    df['ha_bullish'] = df['ha_close'] > df['ha_open']
    
    # 6. Ichimoku Cloud (Basic Tenkan & Kijun)
    df['tenkan'] = (df['high'].rolling(9).max() + df['low'].rolling(9).min()) / 2
    df['kijun'] = (df['high'].rolling(26).max() + df['low'].rolling(26).min()) / 2
    
    # 7. OBV (On Balance Volume)
    df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
    df['obv_ema'] = df['obv'].ewm(span=20, adjust=False).mean()
    
    return df

# ---------------- CHART ----------------
def gen_chart(df, symbol, signal, entry, sl, tp1, tp2, tp3):
    try:
        df = df.tail(30)
        data = [{"x": str(i), "o": float(r.open), "h": float(r.high), "l": float(r.low), "c": float(r.close)} for i, r in enumerate(df.itertuples()) if not pd.isna(r.open)]
        max_x = len(data) - 1
        if max_x < 1: return None
        
        ann = {"entry": {"type": "line", "yMin": entry, "yMax": entry, "borderColor": "#4a9eff", "borderWidth": 3}}
        if signal == "BUY":
            ann['profit'] = {"type": "box", "yMin": entry, "yMax": tp1, "backgroundColor": "rgba(0,200,100,0.05)", "borderColor": "rgba(0,200,100,0.4)", "xMin": 0, "xMax": max_x}
            ann['loss'] = {"type": "box", "yMin": sl, "yMax": entry, "backgroundColor": "rgba(255,60,60,0.05)", "borderColor": "rgba(255,60,60,0.4)", "xMin": 0, "xMax": max_x}
        else:
            ann['profit'] = {"type": "box", "yMin": tp1, "yMax": entry, "backgroundColor": "rgba(0,200,100,0.05)", "borderColor": "rgba(0,200,100,0.4)", "xMin": 0, "xMax": max_x}
            ann['loss'] = {"type": "box", "yMin": entry, "yMax": sl, "backgroundColor": "rgba(255,60,60,0.05)", "borderColor": "rgba(255,60,60,0.4)", "xMin": 0, "xMax": max_x}

        cfg = {"type": "candlestick", "data": {"datasets": [{"data": data, "color": {"up": "#00c864", "down": "#ff3c3c"}}]}, 
               "options": {"scales": {"x": {"display": False}, "y": {"position": "right", "ticks": {"color": "#fff"}}}, "plugins": {"legend": {"display": False}, "annotation": {"annotations": ann}}}}
        
        res = requests.post("https://quickchart.io/chart", json={"chart": cfg, "width": 800, "height": 450, "backgroundColor": "#131722", "version": "3"}, timeout=10)
        if res.status_code == 200: return res.content
    except: pass
    return None

# ---------------- TELEGRAM ----------------
def send_msg(text, markup=None):
    if not TG_TOKEN: return
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    if markup: payload["reply_markup"] = markup
    try: requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json=payload, timeout=10)
    except: pass

def send_photo(img, caption, markup=None):
    if not TG_TOKEN or not img: return send_msg(caption, markup)
    try:
        data = {"chat_id": TG_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
        if markup: data["reply_markup"] = json.dumps(markup)
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto", files={'photo': ('c.png', img, 'image/png')}, data=data, timeout=15)
    except: send_msg(caption, markup)

headers = {'User-Agent': 'Mozilla/5.0'}

# ---------------- DATA ----------------
def get_ticker():
    try:
        res = requests.get("https://api.coindcx.com/exchange/ticker", headers=headers, timeout=10)
        return res.json() if res.status_code == 200 else []
    except: return []

def get_kline(sym, tf, lim=200):
    try:
        c = sym if '_' in sym else 'B-' + sym.replace('USDT', '_USDT')
        res = requests.get(f"https://public.coindcx.com/market_data/candles?pair={c}&interval={tf}&limit={lim}", headers=headers, timeout=10).json()
        if isinstance(res, list): res.reverse(); return res
    except: pass
    return []

# ---------------- AI ANALYSIS ----------------
def get_ai_verdict(symbol, signal, score):
    prompt = f"Stock: {symbol}, Signal: {signal}, Confluence Score: {score}/7 (Trend, Momentum, Volume all aligned). Reply in ONE sentence with a strong verdict."
    try:
        if GROQ_API_KEY:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            data = {"model": "llama3-8b-8192", "messages": [{"role": "user", "content": prompt}], "max_tokens": 50}
            res = requests.post(url, headers=headers, json=data, timeout=10).json()
            return res['choices'][0]['message']['content'].strip()
        elif GEMINI_API_KEY:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
            data = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(url, json=data, timeout=10).json()
            return res['candidates'][0]['content']['parts'][0]['text'].strip()
    except: pass
    return "AI analysis unavailable."

# ---------------- SCANNER (MULTI-INDICATOR LOGIC) ----------------
def scan_market():
    print("Scanning CoinDCX with Pro Strategy...")
    data = get_ticker()
    if not data: return
    
    valid = [c for c in data if isinstance(c, dict) and 'USDT' in str(c.get('market')) and float(c.get('volume', 0)) > 100000]
    valid = sorted(valid, key=lambda x: float(x.get('volume', 0)), reverse=True)[:40] # Top 40 volume
    
    for c in valid:
        sym = c['market']
        if sym in active_trades: continue
        
        kl = get_kline(sym, "15m", 200)
        if not kl or len(kl) < 200: continue
        
        df = pd.DataFrame(kl)
        for col in ['close', 'open', 'high', 'low', 'volume']: df[col] = df[col].astype(float)
        df = calculate_pro_indicators(df)
        
        last = df.iloc[-1]
        
        # --- SCORING SYSTEM (Out of 7) ---
        buy_score = 0
        sell_score = 0
        
        # 1. Trend (EMA200)
        if last['close'] > last['ema200']: buy_score += 1
        if last['close'] < last['ema200']: sell_score += 1
        
        # 2. Ichimoku (Above Kijun)
        if last['close'] > last['kijun']: buy_score += 1
        if last['close'] < last['kijun']: sell_score += 1
        
        # 3. Heiken Ashi
        if last['ha_bullish']: buy_score += 1
        else: sell_score += 1
        
        # 4. MACD
        if last['macd'] > last['macd_signal']: buy_score += 1
        if last['macd'] < last['macd_signal']: sell_score += 1
        
        # 5. RSI/StochRSI
        if last['rsi'] > 50 and last['stoch_rsi'] > 0.5: buy_score += 1
        if last['rsi'] < 50 and last['stoch_rsi'] < 0.5: sell_score += 1
        
        # 6. Bollinger Bands (Price above middle or broke upper)
        if last['close'] > last['sma20']: buy_score += 1
        if last['close'] < last['sma20']: sell_score += 1
        
        # 7. OBV (Smart Money)
        if last['obv'] > last['obv_ema']: buy_score += 1
        if last['obv'] < last['obv_ema']: sell_score += 1
        
        # ULTRA STRICT ENTRY (Need at least 6 out of 7 alignments)
        sig = None
        score = 0
        if buy_score >= 6 and last['close'] > last['open']: 
            sig = "BUY"
            score = buy_score
        elif sell_score >= 6 and last['close'] < last['open']: 
            sig = "SELL"
            score = sell_score
            
        if sig:
            entry = last['close']
            risk = (last['high'] - last['low']) * 1.5
            if sig == "BUY":
                sl, tp1, tp2, tp3 = entry - risk, entry + (risk*2), entry + (risk*3), entry + (risk*4)
            else:
                sl, tp1, tp2, tp3 = entry + risk, entry - (risk*2), entry - (risk*3), entry - (risk*4)
                
            clean_sym = sym.replace("B-", "").replace("_", "")
            ai_text = get_ai_verdict(clean_sym, sig, score)
            
            text = (
                f"<b>🔥 #{clean_sym} {sig} (PRO)</b>\n\n"
                f"Entry: {fmt(entry)}\n"
                f"SL: {fmt(sl)}\n"
                f"TP1: {fmt(tp1)}\n"
                f"TP2: {fmt(tp2)}\n"
                f"TP3: {fmt(tp3)}\n\n"
                f"📊 <b>Confluence:</b> {score}/7 Indicators Aligned\n"
                f"🤖 <b>AI:</b> <i>{ai_text}</i>\n"
                f"⏱ TF: 15m"
            )
            
            markup = {"inline_keyboard": [[{"text": f"📋 Copy", "copy_text": {"text": clean_sym}}], [{"text": "📈 Open CoinDCX", "url": f"coindcx://trade/{clean_sym}"}], [{"text": "❌ Close", "callback_data": f"close_{sym}"}]]}
            
            img = gen_chart(df, clean_sym, sig, entry, sl, tp1, tp2, tp3)
            send_photo(img, text, markup)
            
            active_trades[sym] = {'type': sig, 'entry': entry, 'sl': sl, 'tp1': tp1}
            print(f"PRO Signal Sent: {clean_sym} {sig} (Score: {score})")
            time.sleep(5) # Gap to avoid Telegram limit

# ---------------- BOT LOOP ----------------
def bot_loop():
    while True:
        scan_market()
        time.sleep(300) # Scan every 5 mins

# ---------------- MONITOR ----------------
def monitor():
    while True:
        try:
            data = get_ticker()
            prices = {t['market']: float(t['last_price']) for t in data if isinstance(t, dict)}
            for sym, t in list(active_trades.items()):
                if sym in prices:
                    p = prices[sym]
                    if (t['type'] == "BUY" and p <= t['sl']) or (t['type'] == "SELL" and p >= t['sl']):
                        send_msg(f"❌ <b>{sym.replace('B-','').replace('_','')} Hit STOP LOSS</b>\nPrice: {fmt(p)}")
                        del active_trades[sym]
                    elif (t['type'] == "BUY" and p >= t['tp1']) or (t['type'] == "SELL" and p <= t['tp1']):
                        send_msg(f"✅ <b>{sym.replace('B-','').replace('_','')} Hit TP1</b>\nPrice: {fmt(p)}")
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
                        if txt.startswith("close_"):
                            sym = txt.replace("close_", "")
                            if sym in active_trades: del active_trades[sym]
                            send_msg(f"🛑 Trade Manually Closed.")
                        requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/answerCallbackQuery?callback_query_id={cb_id}")
                        continue
                    
                    txt = u.get("message", {}).get("text", "")
                    cid = u.get("message", {}).get("chat", {}).get("id")
                    
                    if str(cid) == str(TG_CHAT_ID):
                        if txt in ["/start", "/menu"]:
                            markup = {"inline_keyboard": [[{"text": "🚀 SCAN NOW", "callback_data": "scan"}], [{"text": "📊 Active Trades", "callback_data": "trades"}]]}
                            send_msg("👋 <b>Welcome to V53 (PRO Strategy)!</b>\nBot is using 7+ Indicators with AI.", markup)
                        elif txt == "scan":
                            send_msg("⏳ Manual PRO scan starting...")
                            Thread(target=scan_market).start()
                        elif txt == "trades":
                            if not active_trades: send_msg("No active trades.")
                            else:
                                for s, t in active_trades.items():
                                    send_msg(f"🪙 {s.replace('B-','').replace('_','')} ({t['type']})\nEntry: {fmt(t['entry'])}", {"inline_keyboard": [[{"text": "❌ Close", "callback_data": f"close_{s}"}]]})
                                    time.sleep(0.5)
                        elif txt == "/top":
                            data = get_ticker()
                            valid = [{'m': c['market'], 'c': float(c.get('change24hour', 0))} for c in data if isinstance(c, dict) and 'USDT' in str(c.get('market'))]
                            top = sorted(valid, key=lambda x: x['c'], reverse=True)[:5]
                            msg = "🏆 <b>Top Gainers</b>\n\n"
                            for i, c in enumerate(top): msg += f"{i+1}. {c['m'].replace('B-','').replace('_','')}: {c['c']:+.2f}%\n"
                            send_msg(msg)
                        elif txt == "/bottom":
                            data = get_ticker()
                            valid = [{'m': c['market'], 'c': float(c.get('change24hour', 0))} for c in data if isinstance(c, dict) and 'USDT' in str(c.get('market'))]
                            bot = sorted(valid, key=lambda x: x['c'], reverse=False)[:5]
                            msg = "📉 <b>Top Losers</b>\n\n"
                            for i, c in enumerate(bot): msg += f"{i+1}. {c['m'].replace('B-','').replace('_','')}: {c['c']:+.2f}%\n"
                            send_msg(msg)
        except: pass
        time.sleep(2)

if __name__ == "__main__":
    keep_alive = lambda: Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()
    keep_alive()
    Thread(target=monitor).start()
    Thread(target=commands).start()
    Thread(target=bot_loop).start()
