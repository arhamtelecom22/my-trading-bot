import os
import requests
import time
import pandas as pd
import numpy as np
from flask import Flask
from threading import Thread
import json
import concurrent.futures

# ================= TOKEN =================
TG_TOKEN = os.environ.get("TG_TOKEN", "").strip()
TG_CHAT_ID = "762295473"
# ========================================

app = Flask('')

@app.route('/')
def home():
    return "SMC Scoring Bot is Running 24/7!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ================= GLOBAL VARIABLES =================
active_trades = {}
ALL_SYMBOLS = [] 
COMMODITIES = ["GC=F", "SI=F", "CL=F", "HG=F"] # Gold, Silver, Oil, Copper

def fmt(p):
    try:
        p = float(p)
        if p > 1000: return f"{p:.2f}"
        if p > 10: return f"{p:.3f}"
        if p > 1: return f"{p:.4f}"
        return f"{p:.6f}"
    except: return str(p)

# ================= FETCH ALL COINBASE PAIRS =================
def load_coinbase_pairs():
    global ALL_SYMBOLS
    print("Fetching Coinbase Pairs...")
    try:
        res = requests.get("https://api.exchange.coinbase.com/products", timeout=10)
        if res.status_code == 200:
            products = res.json()
            pairs = [p['id'] for p in products if p['quote_currency'] == 'USD' and p['status'] == 'online']
            ALL_SYMBOLS = pairs
            print(f"Loaded {len(ALL_SYMBOLS)} Coinbase Pairs.")
    except Exception as e:
        print("Error fetching pairs:", e)
        ALL_SYMBOLS = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "AVAX-USD", "LINK-USD"]

# ================= DATA FETCHERS =================
def get_kline(sym, interval="15m", limit=200):
    try:
        if sym in COMMODITIES:
            y_range = "5d" if interval == "15m" else "1mo"
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={interval}&range={y_range}"
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
        else:
            gran = 900 if interval == "15m" else 3600
            url = f"https://api.exchange.coinbase.com/products/{sym}/candles?granularity={gran}"
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    df = pd.DataFrame(data, columns=['time', 'low', 'high', 'open', 'close', 'volume'])
                    df = df.iloc[::-1].reset_index(drop=True)
                    for col in ['open', 'high', 'low', 'close', 'volume']: 
                        df[col] = df[col].astype(float)
                    return df.tail(limit)
    except: pass
    return None

# ================= SMC INDICATORS =================
def calculate_indicators(df):
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['atr'] = (df['high'] - df['low']).rolling(window=14).mean()
    df['atr'] = df['atr'].fillna(df['close'] * 0.002) 
    return df

def calculate_smc(df):
    df['swing_high'] = df['high'].rolling(5).max().shift(1)
    df['swing_low'] = df['low'].rolling(5).min().shift(1)

    df['sweep_bull'] = (df['low'] < df['swing_low']) & (df['close'] > df['swing_low'])
    df['sweep_bear'] = (df['high'] > df['swing_high']) & (df['close'] < df['swing_high'])

    df['fvg_bull_top'] = df['low']
    df['fvg_bull_bot'] = df['high'].shift(2)
    df['is_fvg_bull'] = df['fvg_bull_top'] > df['fvg_bull_bot']
    
    df['fvg_bear_bot'] = df['high']
    df['fvg_bear_top'] = df['low'].shift(2)
    df['is_fvg_bear'] = df['fvg_bear_bot'] < df['fvg_bear_top']

    df['bos_bull'] = df['close'] > df['swing_high']
    df['bos_bear'] = df['close'] < df['swing_low']
    
    df['ob_bull_top'] = np.nan
    df['ob_bull_bot'] = np.nan
    df['ob_bear_top'] = np.nan
    df['ob_bear_bot'] = np.nan
    
    for i in range(1, len(df)-1):
        if df['bos_bull'].iloc[i]:
            for j in range(i-1, max(i-5, 0), -1):
                if df['close'].iloc[j] < df['open'].iloc[j]:
                    df.loc[df.index[i], 'ob_bull_top'] = df['high'].iloc[j]
                    df.loc[df.index[i], 'ob_bull_bot'] = df['low'].iloc[j]
                    break
        elif df['bos_bear'].iloc[i]:
            for j in range(i-1, max(i-5, 0), -1):
                if df['close'].iloc[j] > df['open'].iloc[j]:
                    df.loc[df.index[i], 'ob_bear_top'] = df['high'].iloc[j]
                    df.loc[df.index[i], 'ob_bear_bot'] = df['low'].iloc[j]
                    break
    return df

def get_mtf_trend(sym):
    try:
        df_1h = get_kline(sym, interval="1h", limit=200)
        if df_1h is not None and len(df_1h) >= 200:
            ema200 = df_1h['close'].ewm(span=200).mean().iloc[-1]
            close = df_1h['close'].iloc[-1]
            return "BUY" if close > ema200 else "SELL"
    except: pass
    return None

# ================= TELEGRAM =================
def send_msg(text, markup=None, chat_id=TG_CHAT_ID):
    if not TG_TOKEN: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if markup: payload["reply_markup"] = markup
    try: requests.post(url, json=payload, timeout=10)
    except: pass

def send_photo(img, caption, markup=None, chat_id=TG_CHAT_ID):
    if not TG_TOKEN or not img: 
        return send_msg(caption, markup, chat_id)
    try:
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        if markup: data["reply_markup"] = json.dumps(markup)
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto", files={'photo': ('c.png', img, 'image/png')}, data=data, timeout=15)
    except: 
        send_msg(caption, markup, chat_id)

# ================= SCANNER =================
def analyze_symbol(sym):
    if sym in active_trades: return None
    try:
        df = get_kline(sym, "15m", 200)
        if df is None or len(df) < 200: return None
        
        df = calculate_indicators(df)
        df = calculate_smc(df)
        last = df.iloc[-1]
        
        # --- BULLISH SCORING ---
        bull_score = 0
        # 1. Sweep (within last 15 candles)
        if df['sweep_bull'].iloc[-15:].any(): bull_score += 1
        # 2. BOS (within last 10 candles)
        bos_bull_indices = df.index[df['bos_bull'] == True].tolist()
        recent_bos_bull = len(bos_bull_indices) > 0 and (len(df) - bos_bull_indices[-1] <= 10)
        if recent_bos_bull: bull_score += 1
        # 3. FVG/OB Retest (Check last 3 candles)
        in_zone_bull = False
        if recent_bos_bull:
            last_bos_idx = bos_bull_indices[-1]
            for i in range(last_bos_idx, len(df)):
                if df.iloc[i]['is_fvg_bull'] and df['low'].iloc[-3:].min() <= df.iloc[i]['fvg_bull_top']:
                    in_zone_bull = True; break
                if not pd.isna(df.iloc[i]['ob_bull_top']) and df['low'].iloc[-3:].min() <= df.iloc[i]['ob_bull_top']:
                    in_zone_bull = True; break
        if in_zone_bull: bull_score += 1
        
        # --- BEARISH SCORING ---
        bear_score = 0
        if df['sweep_bear'].iloc[-15:].any(): bear_score += 1
        bos_bear_indices = df.index[df['bos_bear'] == True].tolist()
        recent_bos_bear = len(bos_bear_indices) > 0 and (len(df) - bos_bear_indices[-1] <= 10)
        if recent_bos_bear: bear_score += 1
        in_zone_bear = False
        if recent_bos_bear:
            last_bos_bear_idx = bos_bear_indices[-1]
            for i in range(last_bos_bear_idx, len(df)):
                if df.iloc[i]['is_fvg_bear'] and df['high'].iloc[-3:].max() >= df.iloc[i]['fvg_bear_bot']:
                    in_zone_bear = True; break
                if not pd.isna(df.iloc[i]['ob_bear_top']) and df['high'].iloc[-3:].max() >= df.iloc[i]['ob_bear_bot']:
                    in_zone_bear = True; break
        if in_zone_bear: bear_score += 1

        sig = None
        # MTF is the 4th check. If 3 out of 4 match, we take it.
        if bull_score >= 2 and last['close'] > last['open']: # Need at least 2/3 base points + MTF
            if get_mtf_trend(sym) == "BUY": sig = "BUY"
        elif bear_score >= 2 and last['close'] < last['open']:
            if get_mtf_trend(sym) == "SELL": sig = "SELL"
            
        return (sig, df, last) if sig else None
    except: return None

def scan_market(is_manual=False, manual_chat_id=None):
    print(f"[{time.strftime('%H:%M:%S')}] Scanning Full Market SMC Scoring...")
    found = 0
    all_to_scan = ALL_SYMBOLS + COMMODITIES
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(analyze_symbol, all_to_scan))
        
    for i, res in enumerate(results):
        if res is None: continue
        if found >= 3: break
        
        sig, df, last = res
        sym = all_to_scan[i]
        
        entry = float(last['close'])
        risk = float(last['atr'] * 1.5)
        if risk == 0: risk = entry * 0.01
        
        if sig == "BUY": 
            sl = entry - risk
            tp1, tp2, tp3 = entry + (risk*2), entry + (risk*3), entry + (risk*4)
        else: 
            sl = entry + risk
            tp1, tp2, tp3 = entry - (risk*2), entry - (risk*3), entry - (risk*4)
            
        clean_sym = sym.replace("-USD", "").replace("=F", "")
        link = f"https://www.coinbase.com/advanced-trade/spot/{sym}" if sym not in COMMODITIES else f"https://finance.yahoo.com/quote/{sym}"
        
        text = (
            f"<b>🧠 SMC: {clean_sym} {sig}</b>\n\n"
            f"💰 <b>Entry:</b> {fmt(entry)}\n"
            f"🛑 <b>SL:</b> {fmt(sl)}\n"
            f"🎯 <b>TP1:</b> {fmt(tp1)}\n"
            f"🎯 <b>TP2:</b> {fmt(tp2)}\n"
            f"🎯 <b>TP3:</b> {fmt(tp3)}\n\n"
            f"⚡️ <b>Setup:</b> Sweep + BOS + FVG/OB\n"
            f"✅ <b>1H Trend:</b> Aligned"
        )
        
        markup = {"inline_keyboard": [[{"text": f"📋 Copy", "copy_text": {"text": clean_sym}}], [{"text": "📈 Open Chart", "url": link}], [{"text": "❌ Close", "callback_data": f"close_{sym}"}]]}
        
        chat = manual_chat_id if is_manual else TG_CHAT_ID
        send_msg(text, markup, chat)
        
        try:
            df_chart = df.tail(25)
            c_data = [{"x": str(i), "o": float(r.open), "h": float(r.high), "l": float(r.low), "c": float(r.close)} for i, r in enumerate(df_chart.itertuples())]
            max_x = len(c_data) - 1
            if max_x > 1:
                ann = {"entry": {"type": "line", "yMin": entry, "yMax": entry, "borderColor": "#4a9eff", "borderWidth": 3, "borderDash": [5, 5]}}
                if sig == "BUY":
                    ann['tp'] = {"type": "line", "yMin": tp1, "yMax": tp1, "borderColor": "#00c864", "borderWidth": 2}
                    ann['sl'] = {"type": "line", "yMin": sl, "yMax": sl, "borderColor": "#ff3c3c", "borderWidth": 2}
                else:
                    ann['tp'] = {"type": "line", "yMin": tp1, "yMax": tp1, "borderColor": "#00c864", "borderWidth": 2}
                    ann['sl'] = {"type": "line", "yMin": sl, "yMax": sl, "borderColor": "#ff3c3c", "borderWidth": 2}
                
                cfg = {"type": "candlestick", "data": {"datasets": [{"data": c_data, "color": {"up": "#00c864", "down": "#ff3c3c"}}]}, "options": {"scales": {"x": {"display": False}, "y": {"position": "right", "ticks": {"color": "#fff"}}}, "plugins": {"legend": {"display": False}, "annotation": {"annotations": ann}}}}
                q_res = requests.post("https://quickchart.io/chart", json={"chart": cfg, "width": 800, "height": 450, "backgroundColor": "#131722", "version": "3"}, timeout=10)
                if q_res.status_code == 200:
                    send_photo(q_res.content, f"📈 <b>{clean_sym} Chart</b>", chat_id=chat)
        except: pass
        
        active_trades[sym] = {'type': sig, 'entry': entry, 'sl': sl, 'tp1': tp1, 'tp2': tp2, 'tp3': tp3}
        found += 1
        time.sleep(3)
            
    if is_manual and manual_chat_id:
        send_msg(f"✅ Full SMC Scan Complete. Found {found} signals.", chat_id=manual_chat_id)

def bot_loop():
    while True:
        scan_market(False)
        time.sleep(600)

# ================= MONITOR =================
def monitor():
    while True:
        try:
            for sym, t in list(active_trades.items()):
                df = get_kline(sym, "1m", 2)
                if df is not None and len(df) > 0:
                    p = float(df.iloc[-1]['close'])
                    if (t['type'] == "BUY" and p <= t['sl']) or (t['type'] == "SELL" and p >= t['sl']):
                        send_msg(f"❌ <b>{sym} Hit STOP LOSS</b>\nPrice: {fmt(p)}\nEntry was: {fmt(t['entry'])}")
                        del active_trades[sym]
                    elif (t['type'] == "BUY" and p >= t['tp1']) or (t['type'] == "SELL" and p <= t['tp1']):
                        send_msg(f"✅ <b>{sym} Hit TP1</b>\nPrice: {fmt(p)}\nEntry was: {fmt(t['entry'])}")
                        del active_trades[sym]
        except: pass
        time.sleep(30)

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
                            elif txt == "scan":
                                send_msg("⏳ Full Market SMC Scoring Scan starting...")
                                Thread(target=scan_market, args=(True, cid)).start()
                            elif txt == "trades":
                                if not active_trades: 
                                    send_msg("💤 No active trades.")
                                else:
                                    for s, t in active_trades.items():
                                        msg = f"🪙 <b>{s}</b> ({t['type']})\n💰 Entry: {fmt(t['entry'])}\n🛑 SL: {fmt(t['sl'])}\n🎯 TP1: {fmt(t['tp1'])}\n🎯 TP2: {fmt(t['tp2'])}\n🎯 TP3: {fmt(t['tp3'])}"
                                        send_msg(msg, {"inline_keyboard": [[{"text": "❌ Close", "callback_data": f"close_{s}"}]]})
                                        time.sleep(0.5)
                            elif txt == "clearall":
                                active_trades.clear()
                                send_msg("✅ <b>All active trades cleared!</b>")
                        
                        requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/answerCallbackQuery?callback_query_id={cb_id}")
                        continue
                    
                    txt = u.get("message", {}).get("text", "")
                    cid = u.get("message", {}).get("chat", {}).get("id")
                    
                    if str(cid) == str(TG_CHAT_ID):
                        if txt in ["/start", "/menu"]:
                            markup = {"inline_keyboard": [
                                [{"text": "🚀 SCAN NOW (Full Market)", "callback_data": "scan"}],
                                [{"text": "📊 Active Trades", "callback_data": "trades"}],
                                [{"text": "🧹 Clear All Trades", "callback_data": "clearall"}]
                            ]}
                            send_msg(f"👋 <b>Full SMC Scoring Bot</b>\n\n✅ Total Coins: {len(ALL_SYMBOLS)}\n✅ Commodities: Gold, Silver, Oil, Copper\n\nClick 'Scan Now':", markup)
        except: pass
        time.sleep(2)

# ================= MAIN =================
if __name__ == "__main__":
    load_coinbase_pairs()
    keep_alive()
    Thread(target=monitor).start()
    Thread(target=commands).start()
    Thread(target=bot_loop).start()
