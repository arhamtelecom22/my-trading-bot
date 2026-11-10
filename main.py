import os
import requests
import time
import pandas as pd
import numpy as np
from flask import Flask
from threading import Thread
import json

# ================= TOKEN =================
TG_TOKEN = os.environ.get("TG_TOKEN", "").strip()
TG_CHAT_ID = "762295473"
# ========================================

app = Flask('')

@app.route('/')
def home():
    return "All-in-One Master Bot is Running 24/7!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ================= GLOBAL VARIABLES =================
active_trades = {}
last_ticker_data = []
last_ticker_time = 0

# Lists for different markets
COINBASE_TOP = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "AVAX-USD", "LINK-USD"]
STOCK_TOP = {"^NSEI": "NIFTY 50", "^BSESN": "SENSEX", "RELIANCE.NS": "RELIANCE", "TCS.NS": "TCS", "HDFCBANK.NS": "HDFC BANK", "AAPL": "APPLE", "MSFT": "MICROSOFT", "NVDA": "NVIDIA"}
COMMODITY_TOP = {"GC=F": "GOLD", "SI=F": "SILVER", "CL=F": "CRUDE OIL", "HG=F": "COPPER"}

def fmt(p):
    try: return f"{float(p):.4f}"
    except: return str(p)

# ================= DATA FETCHERS =================
def get_coindcx_ticker():
    global last_ticker_data, last_ticker_time
    now = time.time()
    if last_ticker_data and (now - last_ticker_time < 60):
        return last_ticker_data
    
    try:
        res = requests.get("https://api.coindcx.com/exchange/ticker", timeout=10)
        if res.status_code == 200:
            filtered = [c for c in res.json() if 'USDT' in str(c.get('market'))]
            last_ticker_data = filtered
            last_ticker_time = now
            return filtered
    except: pass
    return last_ticker_data if last_ticker_data else []

def get_kline(sym, market_type):
    try:
        if market_type == "coindcx":
            c_sym = sym if '_' in sym else 'B-' + sym.replace('USDT', '_USDT')
            url = f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval=15m&limit=200"
            res = requests.get(url, timeout=10).json()
            if isinstance(res, list):
                res.reverse()
                df = pd.DataFrame(res)
                for col in ['open', 'high', 'low', 'close', 'volume']: df[col] = df[col].astype(float)
                return df
                
        elif market_type == "coinbase":
            url = f"https://api.exchange.coinbase.com/products/{sym}/candles?granularity=900"
            res = requests.get(url, timeout=10).json()
            if isinstance(res, list):
                df = pd.DataFrame(res, columns=['time', 'low', 'high', 'open', 'close', 'volume'])
                df = df.iloc[::-1].reset_index(drop=True)
                for col in ['open', 'high', 'low', 'close', 'volume']: df[col] = df[col].astype(float)
                return df.tail(200)
                
        elif market_type in ["stocks", "commodities"]:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=15m&range=5d"
            res = requests.get(url, timeout=10).json()
            result = res['chart']['result'][0]
            timestamps = result['timestamp']
            closes = result['indicators']['quote'][0]['close']
            opens = result['indicators']['quote'][0]['open']
            highs = result['indicators']['quote'][0]['high']
            lows = result['indicators']['quote'][0]['low']
            volumes = result['indicators']['quote'][0]['volume']
            
            data = []
            for i in range(len(timestamps)):
                if closes[i] is not None and opens[i] is not None and highs[i] is not None and lows[i] is not None:
                    data.append({'open': opens[i], 'high': highs[i], 'low': lows[i], 'close': closes[i], 'volume': volumes[i] or 0})
            
            df = pd.DataFrame(data)
            return df if len(df) >= 200 else None
    except: pass
    return None

# ================= INDICATORS =================
def calculate_indicators(df):
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = df['ema12'] - df['ema26']
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    df['atr'] = (df['high'] - df['low']).rolling(window=14).mean()
    return df

# ================= TELEGRAM =================
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

# ================= SCANNER =================
def scan_market(market_type, is_manual=False, manual_chat_id=None):
    print(f"[{time.strftime('%H:%M:%S')}] Scanning {market_type.upper()}...")
    
    symbols_to_scan = []
    if market_type == "coindcx":
        data = get_coindcx_ticker()
        if data:
            valid = [c for c in data if float(c.get('volume', 0)) > 50000]
            valid = sorted(valid, key=lambda x: float(x.get('volume', 0)), reverse=True)[:20]
            symbols_to_scan = [c['market'] for c in valid]
    elif market_type == "coinbase":
        symbols_to_scan = COINBASE_TOP
    elif market_type == "stocks":
        symbols_to_scan = list(STOCK_TOP.keys())
    elif market_type == "commodities":
        symbols_to_scan = list(COMMODITY_TOP.keys())
    
    found = 0
    for sym in symbols_to_scan:
        if found >= 2: break # Max 2 signals per market per scan
        if sym in active_trades: continue
        
        try:
            df = get_kline(sym, market_type)
            if df is None or len(df) < 200: continue
            
            df = calculate_indicators(df)
            last = df.iloc[-1]
            
            ema_buy = last['close'] > last['ema200'] and last['ema50'] > last['ema200']
            ema_sell = last['close'] < last['ema200'] and last['ema50'] < last['ema200']
            macd_buy = last['macd'] > last['macd_signal']
            macd_sell = last['macd'] < last['macd_signal']
            rsi_buy = last['rsi'] > 50
            rsi_sell = last['rsi'] < 50
            vol_spike = last['volume'] > (df['volume'].tail(20).mean() * 1.1)
            
            sig = None
            if ema_buy and macd_buy and rsi_buy and vol_spike and last['close'] > last['open']:
                sig = "BUY"
            elif ema_sell and macd_sell and rsi_sell and vol_spike and last['close'] < last['open']:
                sig = "SELL"
                
            if sig:
                entry = last['close']
                risk = last['atr'] * 1.5
                if sig == "BUY":
                    sl, tp1, tp2, tp3 = entry - risk, entry + (risk*2), entry + (risk*3), entry + (risk*4)
                else:
                    sl, tp2, tp3, tp1 = entry + risk, entry - (risk*2), entry - (risk*3), entry - (risk*4)
                    tp1, tp2, tp3 = tp1, tp2, tp3
                    
                if market_type == "coindcx":
                    clean_sym = sym.replace("B-", "").replace("_", "")
                    link = f"coindcx://trade/{clean_sym}"
                elif market_type == "coinbase":
                    clean_sym = sym.replace("-USD", "")
                    link = f"https://www.coinbase.com/advanced-trade/spot/{sym}"
                elif market_type == "stocks":
                    clean_sym = STOCK_TOP.get(sym, sym)
                    link = f"https://finance.yahoo.com/quote/{sym}"
                else:
                    clean_sym = COMMODITY_TOP.get(sym, sym)
                    link = f"https://finance.yahoo.com/quote/{sym}"
                
                # FULL DETAILS MESSAGE
                text = (
                    f"<b>🔥 {clean_sym} {sig} ({market_type.upper()})</b>\n\n"
                    f"💰 <b>Entry:</b> {fmt(entry)}\n"
                    f"🛑 <b>SL:</b> {fmt(sl)}\n"
                    f"🎯 <b>TP1:</b> {fmt(tp1)}\n"
                    f"🎯 <b>TP2:</b> {fmt(tp2)}\n"
                    f"🎯 <b>TP3:</b> {fmt(tp3)}\n\n"
                    f"📊 <b>RSI:</b> {last['rsi']:.1f}\n"
                    f"⏱ TF: 15m"
                )
                
                markup = {"inline_keyboard": [[{"text": f"📋 Copy", "copy_text": {"text": clean_sym}}], [{"text": "📈 Open Chart", "url": link}], [{"text": "❌ Close", "callback_data": f"close_{sym}"}]]}
                
                if is_manual and manual_chat_id:
                    # For manual scan, reply directly to the chat
                    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                    requests.post(url, json={"chat_id": manual_chat_id, "text": text, "parse_mode": "HTML", "reply_markup": markup})
                else:
                    # For auto scan, send to default chat
                    send_msg(text, markup)
                
                # Chart Generation
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
                            if is_manual and manual_chat_id:
                                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
                                files = {'photo': ('c.png', q_res.content, 'image/png')}
                                requests.post(url, files=files, data={"chat_id": manual_chat_id, "caption": f"📈 <b>{clean_sym} Chart</b>", "parse_mode": "HTML"}, timeout=15)
                            else:
                                send_photo(q_res.content, f"📈 <b>{clean_sym} Chart</b>")
                except: pass
                
                active_trades[sym] = {'type': sig, 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3, 'market': market_type}
                found += 1
                time.sleep(3) # Gap between signals
                
        except Exception as e:
            time.sleep(1)
            
    if is_manual and manual_chat_id:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={"chat_id": manual_chat_id, "text": f"✅ Scan Complete on {market_type.upper()}. Found {found} signals.", "parse_mode": "HTML"})

def bot_loop():
    while True:
        # Auto-scan ALL markets
        scan_market("coindcx", False)
        scan_market("coinbase", False)
        scan_market("stocks", False)
        scan_market("commodities", False)
        
        print("All Markets Scanned. Sleeping for 5 mins...")
        time.sleep(300) 

# ================= MONITOR =================
def monitor():
    while True:
        try:
            data = get_coindcx_ticker()
            prices = {t['market']: float(t['last_price']) for t in data}
            for sym, t in list(active_trades.items()):
                if t.get('market') == 'coindcx' and sym in prices:
                    p = prices[sym]
                    if (t['type'] == "BUY" and p <= t['sl']) or (t['type'] == "SELL" and p >= t['sl']):
                        send_msg(f"❌ <b>{sym.replace('B-','').replace('_','')} Hit STOP LOSS</b>\nPrice: {fmt(p)}")
                        del active_trades[sym]
                    elif (t['type'] == "BUY" and p >= t['tp1']) or (t['type'] == "SELL" and p <= t['tp1']):
                        send_msg(f"✅ <b>{sym.replace('B-','').replace('_','')} Hit TP1</b>\nPrice: {fmt(p)}")
                        del active_trades[sym]
        except: pass
        time.sleep(20)

# ================= COMMANDS =================
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
                                if sym in active_trades: 
                                    del active_trades[sym]
                                    send_msg(f"🛑 Trade Manually Closed.")
                            elif txt.startswith("scan_"):
                                mkt = txt.replace("scan_", "")
                                send_msg(f"⏳ Manual scan on {mkt.upper()} starting...")
                                Thread(target=scan_market, args=(mkt, True, cid)).start()
                            elif txt == "trades":
                                if not active_trades: 
                                    send_msg("💤 No active trades.")
                                else:
                                    for s, t in active_trades.items():
                                        mkt = t.get('market', 'coindcx').upper()
                                        msg = (
                                            f"🪙 <b>{s}</b> ({t['type']}) - {mkt}\n"
                                            f"💰 Entry: {fmt(t['entry'])}\n"
                                            f"🛑 SL: {fmt(t['sl'])}\n"
                                            f"🎯 TP1: {fmt(t['tp1'])}\n"
                                            f"🎯 TP2: {fmt(t['tp2'])}\n"
                                            f"🎯 TP3: {fmt(t['tp3'])}"
                                        )
                                        send_msg(msg, {"inline_keyboard": [[{"text": "❌ Close", "callback_data": f"close_{s}"}]]})
                                        time.sleep(0.5)
                            elif txt == "clearall":
                                active_trades.clear()
                                send_msg("✅ <b>All active trades cleared!</b> Bot will now find fresh signals.")
                        
                        requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/answerCallbackQuery?callback_query_id={cb_id}")
                        continue
                    
                    txt = u.get("message", {}).get("text", "")
                    cid = u.get("message", {}).get("chat", {}).get("id")
                    
                    if str(cid) == str(TG_CHAT_ID):
                        if txt in ["/start", "/menu"]:
                            markup = {"inline_keyboard": [
                                [{"text": "🪙 Scan CoinDCX", "callback_data": "scan_coindcx"}, {"text": "🪙 Scan Coinbase", "callback_data": "scan_coinbase"}],
                                [{"text": "📈 Scan Stocks", "callback_data": "scan_stocks"}, {"text": "🛢️ Scan Commodities", "callback_data": "scan_commodities"}],
                                [{"text": "📊 Active Trades", "callback_data": "trades"}],
                                [{"text": "🧹 Clear All Trades", "callback_data": "clearall"}]
                            ]}
                            send_msg("👋 <b>All-in-One Master Bot</b>\n\n✅ Auto-Scan is ON for all markets (Every 5 Mins)\n\nSelect a market to manually scan right now:", markup)
        except: pass
        time.sleep(2)

# ================= MAIN =================
if __name__ == "__main__":
    keep_alive()
    Thread(target=monitor).start()
    Thread(target=commands).start()
    Thread(target=bot_loop).start()
