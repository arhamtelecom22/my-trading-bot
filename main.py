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
CURRENT_MARKET = "coindcx"  # Options: coindcx, coinbase, stocks, commodities
last_ticker_data = []
last_ticker_time = 0

# Lists for different markets
COINBASE_TOP = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "AVAX-USD", "LINK-USD", "DOT-USD", "DOGE-USD", "SHIB-USD", "LTC-USD", "BCH-USD", "MATIC-USD", "UNI-USD", "ATOM-USD"]
STOCK_TOP = {"^NSEI": "NIFTY 50", "^BSESN": "SENSEX", "RELIANCE.NS": "RELIANCE", "TCS.NS": "TCS", "HDFCBANK.NS": "HDFC BANK", "AAPL": "APPLE", "MSFT": "MICROSOFT", "GOOGL": "GOOGLE", "NVDA": "NVIDIA", "TSLA": "TESLA"}
COMMODITY_TOP = {"GC=F": "GOLD", "SI=F": "SILVER", "CL=F": "CRUDE OIL", "HG=F": "COPPER", "NG=F": "NATURAL GAS"}

def fmt(p):
    try: return f"{float(p):.4f}"
    except: return str(p)

# ================= DATA FETCHERS =================
def get_ticker():
    global last_ticker_data, last_ticker_time
    now = time.time()
    if last_ticker_data and (now - last_ticker_time < 60):
        return last_ticker_data
    
    try:
        if CURRENT_MARKET == "coindcx":
            res = requests.get("https://api.coindcx.com/exchange/ticker", timeout=10)
            if res.status_code == 200:
                filtered = [c for c in res.json() if 'USDT' in str(c.get('market'))]
                last_ticker_data = filtered
                last_ticker_time = now
                return filtered
        elif CURRENT_MARKET == "coinbase":
            return [{'symbol': s, 'volume': 50000000, 'change24hour': 0, 'lastPrice': 0} for s in COINBASE_TOP]
    except: pass
    return last_ticker_data if last_ticker_data else []

def get_kline(sym):
    try:
        if CURRENT_MARKET == "coindcx":
            c_sym = sym if '_' in sym else 'B-' + sym.replace('USDT', '_USDT')
            url = f"https://public.coindcx.com/market_data/candles?pair={c_sym}&interval=15m&limit=200"
            res = requests.get(url, timeout=10).json()
            if isinstance(res, list):
                res.reverse()
                df = pd.DataFrame(res)
                for col in ['open', 'high', 'low', 'close', 'volume']: df[col] = df[col].astype(float)
                return df
                
        elif CURRENT_MARKET == "coinbase":
            granularity = 900
            url = f"https://api.exchange.coinbase.com/products/{sym}/candles?granularity={granularity}"
            res = requests.get(url, timeout=10).json()
            if isinstance(res, list):
                df = pd.DataFrame(res, columns=['time', 'low', 'high', 'open', 'close', 'volume'])
                df = df.iloc[::-1].reset_index(drop=True)
                for col in ['open', 'high', 'low', 'close', 'volume']: df[col] = df[col].astype(float)
                return df.tail(200)
                
        elif CURRENT_MARKET in ["stocks", "commodities"]:
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
def scan_market(is_manual=False):
    global CURRENT_MARKET
    print(f"[{time.strftime('%H:%M:%S')}] Scanning {CURRENT_MARKET.upper()}...")
    
    symbols_to_scan = []
    if CURRENT_MARKET == "coindcx":
        data = get_ticker()
        if not data: 
            if is_manual: send_msg("❌ Failed to fetch CoinDCX data.")
            return
        valid = [c for c in data if float(c.get('volume', 0)) > 50000]
        valid = sorted(valid, key=lambda x: float(x.get('volume', 0)), reverse=True)[:20]
        symbols_to_scan = [c['market'] for c in valid]
        
    elif CURRENT_MARKET == "coinbase":
        symbols_to_scan = COINBASE_TOP
    elif CURRENT_MARKET == "stocks":
        symbols_to_scan = list(STOCK_TOP.keys())
    elif CURRENT_MARKET == "commodities":
        symbols_to_scan = list(COMMODITY_TOP.keys())
    
    found = 0
    for sym in symbols_to_scan:
        if found >= 3: break
        if sym in active_trades: continue
        
        try:
            df = get_kline(sym)
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
                    sl, tp1, tp2, tp3 = entry + risk, entry - (risk*2), entry - (risk*3), entry - (risk*4)
                    
                if CURRENT_MARKET == "coindcx":
                    clean_sym = sym.replace("B-", "").replace("_", "")
                    link = f"coindcx://trade/{clean_sym}"
                elif CURRENT_MARKET == "coinbase":
                    clean_sym = sym.replace("-USD", "")
                    link = f"https://www.coinbase.com/advanced-trade/spot/{sym}"
                elif CURRENT_MARKET == "stocks":
                    clean_sym = STOCK_TOP.get(sym, sym)
                    link = f"https://finance.yahoo.com/quote/{sym}"
                else:
                    clean_sym = COMMODITY_TOP.get(sym, sym)
                    link = f"https://finance.yahoo.com/quote/{sym}"
                
                text = (
                    f"<b>🔥 {clean_sym} {sig} ({CURRENT_MARKET.upper()})</b>\n\n"
                    f"Entry: {fmt(entry)}\nSL: {fmt(sl)}\nTP1: {fmt(tp1)}\nTP2: {fmt(tp2)}\nTP3: {fmt(tp3)}\n\n"
                    f"📊 <b>RSI:</b> {last['rsi']:.1f}\n"
                    f"⏱ TF: 15m"
                )
                
                markup = {"inline_keyboard": [[{"text": f"📋 Copy", "copy_text": {"text": clean_sym}}], [{"text": "📈 Open Chart", "url": link}], [{"text": "❌ Close", "callback_data": f"close_{sym}"}]]}
                
                send_msg(text, markup)
                
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
                
                active_trades[sym] = {'type': sig, 'entry': entry, 'sl': sl, 'tp1': tp1, 'market': CURRENT_MARKET}
                found += 1
                time.sleep(3)
                
        except Exception as e:
            time.sleep(1)
            
    if is_manual:
        send_msg(f"✅ Scan Complete on {CURRENT_MARKET.upper()}. Found {found} signals.")

def bot_loop():
    while True:
        scan_market(False)
        time.sleep(300) 

# ================= MONITOR =================
def monitor():
    while True:
        try:
            if CURRENT_MARKET in ["coindcx", "coinbase"]:
                if CURRENT_MARKET == "coindcx":
                    data = get_ticker()
                    prices = {t['market']: float(t['last_price']) for t in data}
                else:
                    # Simplified for Coinbase (skip active monitoring to save API limits)
                    prices = {}
                
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

# ================= COMMANDS & MENU =================
def commands():
    global CURRENT_MARKET
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
                                send_msg(f"⏳ Manual scan on {CURRENT_MARKET.upper()} starting...")
                                Thread(target=scan_market, args=(True,)).start()
                            elif txt == "trades":
                                if not active_trades: send_msg("💤 No active trades.")
                                else:
                                    for s, t in active_trades.items():
                                        mkt = t.get('market', 'coindcx').upper()
                                        send_msg(f"🪙 <b>{s}</b> ({t['type']}) - {mkt}\nEntry: {fmt(t['entry'])}", {"inline_keyboard": [[{"text": "❌ Close", "callback_data": f"close_{s}"}]]})
                                        time.sleep(0.5)
                            elif txt == "clearall":
                                active_trades.clear()
                                send_msg("✅ <b>All active trades cleared!</b> Bot will now find fresh signals.")
                            elif txt in ["coindcx", "coinbase", "stocks", "commodities"]:
                                CURRENT_MARKET = txt
                                market_names = {"coindcx": "CoinDCX (Crypto)", "coinbase": "Coinbase (Crypto)", "stocks": "Stocks", "commodities": "Commodities"}
                                send_msg(f"✅ <b>Market Switched to {market_names[CURRENT_MARKET]}</b>")
                                show_menu(cid)
                        
                        requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/answerCallbackQuery?callback_query_id={cb_id}")
                        continue
                    
                    txt = u.get("message", {}).get("text", "")
                    cid = u.get("message", {}).get("chat", {}).get("id")
                    
                    if str(cid) == str(TG_CHAT_ID):
                        if txt in ["/start", "/menu"]:
                            show_menu(cid)
        except: pass
        time.sleep(2)

def show_menu(cid):
    markup = {"inline_keyboard": [
        [{"text": "🪙 CoinDCX", "callback_data": "coindcx"}, {"text": "🪙 Coinbase", "callback_data": "coinbase"}],
        [{"text": "📈 Stocks", "callback_data": "stocks"}, {"text": "🛢️ Commodities", "callback_data": "commodities"}],
        [{"text": "🚀 SCAN NOW", "callback_data": "scan"}, {"text": "📊 Active Trades", "callback_data": "trades"}],
        [{"text": "🧹 Clear All Trades", "callback_data": "clearall"}]
    ]}
    
    mkt_name = {"coindcx": "CoinDCX (Crypto)", "coinbase": "Coinbase (Crypto)", "stocks": "Stocks", "commodities": "Commodities"}[CURRENT_MARKET]
    
    send_msg(f"👋 <b>All-in-One Master Bot</b>\n\nCurrent Market: <b>{mkt_name}</b>\n✅ Auto-Scan is ON (Every 5 Mins)\n\nSelect a market or scan now:", markup)

# ================= MAIN =================
if __name__ == "__main__":
    keep_alive()
    Thread(target=monitor).start()
    Thread(target=commands).start()
    Thread(target=bot_loop).start()
