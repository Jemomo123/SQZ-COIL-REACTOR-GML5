import os
import time
import ccxt
import threading
import socket
import pandas as pd
from flask import Flask, jsonify
from engine import JeremiahEngine

app = Flask(__name__)
engine = JeremiahEngine()

# --- CRITICAL NETWORK FIX ---
socket.setdefaulttimeout(5)

# --- SHARED STATE ---
current_data = {
    "signals": [],
    "exchange": "STARTING...",
    "scan_time": "0s",
    "timestamp": "00:00:00"
}

# --- CALL LOG (HISTORY) ---
call_log = []

# --- EXCHANGE CONFIG ---
EXCHANGE_CONFIG = [
    ccxt.binance({'options': {'defaultType': 'spot'}}),
    ccxt.okx({'options': {'defaultType': 'spot'}})
]

def fetch_data_failover(symbol):
    pair = symbol + '/USDT'
    for ex in EXCHANGE_CONFIG:
        try:
            if not ex.markets: ex.load_markets()
            if pair not in ex.markets: continue 

            dfs = {}
            for tf in ['3m', '5m', '15m']:
                bars = ex.fetch_ohlcv(pair, tf, limit=200)
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                dfs[tf] = df
            return dfs, ex.name
        except Exception as e:
            continue
    return None, "FAIL"

def scanner_loop():
    """
    Runs continuously in background.
    """
    targets = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "PEPE", "SPX", "SPACE", "ZEC", "LINEA"]
    
    while True:
        start_time = time.time()
        results = []
        active_ex = "OFFLINE"
        
        for sym in targets:
            try:
                dfs, ex_name = fetch_data_failover(sym)
                if dfs:
                    active_ex = ex_name
                    master = engine.generate_master_signal(sym + "/USDT", dfs['3m'], dfs['5m'], dfs['15m'])
                    if master:
                        d = master['data_15m']
                        if d['validity'] in ['ACTIVE', 'WAIT']:
                            results.append({
                                "symbol": sym,
                                "direction": d['expansion_dir'],
                                "sqz_type": d['sqz_type'],
                                "validity": d['validity'],
                                "crossover": d['crossover'],
                                "expansion": d['expansion_type'],
                                "elephant": d['elephant_detected'],
                                "tail": d['tail_detected'],
                                "sma_respect": d['sma_status'],
                                "timeframe": d['timeframe'], # Passing timeframe
                                "exchange": active_ex
                            })
            except Exception as e:
                pass

        scan_time = round(time.time() - start_time, 2)
        
        # Update Cache
        current_data['signals'] = results
        current_data['exchange'] = active_ex
        current_data['scan_time'] = f"{scan_time}s"
        current_data['timestamp'] = pd.Timestamp.now().strftime("%H:%M:%S")
        
        # Update Call Log
        log_entry = {
            "time": current_data['timestamp'],
            "count": len(results),
            "active_coin": results[0]['symbol'] if results else "-",
            "status": "SUCCESS" if active_ex != "OFFLINE" else "FAIL",
            "latency": f"{scan_time}s"
        }
        call_log.insert(0, log_entry)
        if len(call_log) > 20: call_log.pop()
        
        time.sleep(6)

# --- GLOBAL THREAD OBJECT ---
t = None

def start_thread():
    global t
    if t is None or not t.is_alive():
        t = threading.Thread(target=scanner_loop, daemon=True)
        t.start()
        print("Scanner Thread Started")

# Start thread on import
start_thread()

# --- HTML DASHBOARD ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JEREMIAH EXECUTION ENGINE</title>
    <style>
        body { background-color: #000; color: #00ff00; font-family: 'Courier New', monospace; padding: 10px; font-size: 12px; }
        .header { border-bottom: 2px solid #00ff00; padding-bottom: 10px; margin-bottom: 10px; text-align: center; }
        .title { font-size: 1.2rem; font-weight: bold; letter-spacing: 2px; }
        .stats { font-size: 0.7rem; color: #888; margin-top: 5px; }
        
        /* Main Table */
        table { width: 100%; border-collapse: collapse; margin-top: 10px;
