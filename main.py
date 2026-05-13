import os
import time
import ccxt
import threading
import pandas as pd
from flask import Flask, jsonify
from engine import SimpleSQZEngine  # UPDATED IMPORT

app = Flask(__name__)
engine = SimpleSQZEngine() # UPDATED CLASS NAME

# --- SHARED STATE ---
current_data = {
    "signals": [], 
    "exchange": "STARTING...", 
    "scan_time": "0s", 
    "timestamp": "00:00:00"
}

# --- DEBUG STATS ---
stats = {
    "api_errors": 0,
    "symbols_scanned": 0,
    "reconnects": 0,
    "sqz_detections": 0,
    "exp_detections": 0,
    "near_sqz_count": 0
}

# --- EXCHANGE CONFIG (SPOT MODE) ---
EXCHANGE_CONFIG = [
    ccxt.binance({'options': {'defaultType': 'spot'}, 'timeout': 15000}),
    ccxt.okx({'options': {'defaultType': 'spot'}, 'timeout': 15000}),
    ccxt.mexc({'options': {'defaultType': 'spot'}, 'timeout': 15000}),
    ccxt.gate({'options': {'defaultType': 'spot'}, 'timeout': 15000})
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
            stats['api_errors'] += 1
            stats['reconnects'] += 1
            continue
    return None, "OFFLINE"

def scanner_loop():
    targets = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "PEPE", "SPX", "SPACE", "ZEC", "LINEA"]
    timeframes = ['3m', '5m', '15m']
    
    while True:
        start_time = time.time()
        results = []
        verification = []
        active_ex = "OFFLINE"
        current_sqz = 0
        current_exp = 0
        near_count = 0
        scanned_count = 0
        
        for sym in targets:
            try:
                dfs, ex_name = fetch_data_failover(sym)
                if dfs:
                    active_ex = ex_name
                    scanned_count += 1
                    
                    for tf in timeframes:
                        master = engine.scan_timeframe(dfs[tf], tf)
                        
                        if master:
                            s = master
                            
                            if s['sqz_type'] != "NONE": current_sqz += 1
                            if s['expansion_status'] == "FIRED": current_exp += 1
                            
                            # Near-SQZ Logic
                            spread = s['spread_pct']
                            near_status = "NONE"
                            if spread <= 0.1:
                                near_status = "VALID"
                            elif spread <= 0.2:
                                near_status = "NEAR"
                                near_count += 1

                            verification.append({
                                "symbol": sym,
                                "tf": tf,
                                "price": float(dfs[tf].iloc[-1]['close']),
                                "spread": s['spread_pct'],
                                "near_status": near_status,
                                "sqz_type": s['sqz_type'],
                                "cluster_cnt": 0 # Simplified
                            })

                            if s['valid']:
                                results.append({
                                    "symbol": sym,
                                    "exchange": active_ex,
                                    "timeframe": tf,
                                    "sqz_type": s['sqz_type'],
                                    "direction": s['direction'],
                                    "compression": f"{s['spread_pct']}%",
                                    "elephant": "YES" if s['expansion_type'] == "ELEPHANT" else "NO",
                                    "expansion": s['expansion_type'],
                                    "time": pd.Timestamp.now().strftime("%H:%M:%S")
                                })
            except Exception as e:
                pass

        scan_time = round(time.time() - start_time, 2)
        
        stats['symbols_scanned'] = scanned_count
        stats['sqz_detections'] = current_sqz
        stats['exp_detections'] = current_exp
        stats['near_sqz_count'] = near_count
        
        current
