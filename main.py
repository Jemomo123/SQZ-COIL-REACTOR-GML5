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

# --- NETWORK FIX ---
socket.setdefaulttimeout(5)

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
    ccxt.binance({'options': {'defaultType': 'spot'}}),
    ccxt.okx({'options': {'defaultType': 'spot'}}),
    ccxt.mexc({'options': {'defaultType': 'spot'}}),
    ccxt.gate({'options': {'defaultType': 'spot'}})
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
                            
                            # Near-SQZ Logic (0.1% - 0.2%)
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
                                "dist_20": s['debug_dist_20'],
                                "dist_100": s['debug_dist_100'],
                                "dist_200": s['debug_dist_200'],
                                "spread": s['spread_pct'],
                                "near_status": near_status,
                                "sqz_type": s['sqz_type'],
                                "cluster_cnt": s['debug_cluster_count']
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
        
        current_data['signals'] = results
        current_data['verification'] = verification
        current_data['exchange'] = active_ex
        current_data['scan_time'] = f"{scan_time}s"
        current_data['timestamp'] = pd.Timestamp.now().strftime("%H:%M:%S")
        
        time.sleep(6)

# --- GLOBAL THREAD ---
t = None

def start_thread():
    global t
    if t is None or not t.is_alive():
        t = threading.Thread(target=scanner_loop, daemon=True)
        t.start()
        print("Scanner Thread Started")

start_thread()

# --- HTML DASHBOARD ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JEREMIAH // EXECUTION</title>
    <style>
        body { background-color: #000; color: #00ff00; font-family: 'Courier New', monospace; padding: 10px; font-size: 11px; }
        .header { border-bottom: 2px solid #00ff00; padding-bottom: 10px; margin-bottom: 15px; text-align: center; }
        .title { font-size: 1.2rem; font-weight: bold; letter-spacing: 2px; }
        .stats { font-size: 0.7rem; color: #888; margin-top: 5px; }
        
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.6rem; }
        th { text-align: left; border-bottom: 1px solid #333; padding: 2px; color: #00ff00; font-weight: bold; }
        td { padding: 2px; border-bottom: 1px solid #111; }
        
        .debug-section { margin-top: 20px; border-top: 1px dashed #444; padding-top: 10px; }
        .debug-title { color: #00ff00; font-size: 0.7rem; margin-bottom: 5px; }
        .debug-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.6rem; color: #888; }
        
        .verify-section { margin-top: 20px; border-top: 1px dashed #ffaa00; padding-top: 10px; }
        .verify-title { color: #ffaa00; font-size: 0.7rem; margin-bottom: 5px; }
        .verify-table { width: 100%; font-size: 0.5rem; }
        .verify-table th { color: #ffaa00; }
        
        .status-valid { color: #00ff00; font-weight: bold; }
        .status-near { color: #ffaa00; font-weight: bold; }
        .status-none { color: #444; }
        
        .row-valid { background-color: #112200; }
        .row-near { background-color: #221100; }
        
        .long { color: #00ff00; }
        .short { color: #ff0000; }
        .mega { color: #d4af37; font-weight: bold; }
        .empty-msg { text-align: center; color: #333; padding: 20px; font-size: 0.8rem; }
    </style>
</head>
<body>
    <div class="header">
        <div class="title">JEREMIAH // EXECUTION</div>
        <div class="stats" id="header-status">INITIALIZING...</div>
    </div>

    <div id="grid"></div>

    <div class="debug-section">
        <div class="debug-title">PROFESSIONAL DEBUG PANEL</div>
        <div class="debug-grid" id="debug-content"></div>
    </div>

    <div class="verify-section">
        <div class="verify-title">NEAR-SQZ VISIBILITY (0.1% THRESHOLD)</div>
        <div style="overflow-x:auto;">
            <table class="verify-table">
                <thead>
                    <tr>
                        <th>SYM</th><th>TF</th><th>PRICE</th><th>SPREAD%</th><th>STATUS</th><th>SQZ</th><th>CLUS</th>
                    </tr>
                </thead>
                <tbody id="verify-body"></tbody>
            </table>
        </div>
    </div>

    <script>
        async function update() {
            try {
                const res = await fetch('/api/data');
                const json = await res.json();
                render(json);
            } catch (e) {
                document.getElementById('header-status').innerText = "CONNECTION ERROR";
            }
        }

        function render(data) {
            document.getElementById('header-status').innerHTML = 
                'EXCHANGE: ' + data.exchange.toUpperCase() + ' | LATENCY: ' + data.scan_time + ' | ' + data.timestamp;

            const grid = document.getElementById('grid');
            if (data.signals.length === 0) {
                grid.innerHTML = '<div class="empty-msg">NO EXPLOSIVE RELEASE DETECTED</div>';
            } else {
                let html = '<table><thead><tr><th>SYM</th><th>EXC</th><th>TF</th><th>SQZ TYPE</th><th>DIR</th><th>CMP%</th><th>ELEPHANT</th><th>EXP</th><th>TIME</th></tr></thead><tbody>';
                data.signals.forEach(s => {
                    const dirClass = s.direction.toLowerCase();
                    const isMega = s.sqz_type.includes('MEGA');
                    let sqzColor = '#fff';
                    if(isMega) sqzColor = '#d4af37';
                    html += '<tr>' +
                        '<td>' + s.symbol + '</td>' +
                        '<td>' + s.exchange.substring(0,3) + '</td>' +
                        '<td>' + s.timeframe + '</td>' +
                        '<td style="color:' + sqzColor + '">' + s.sqz_type + '</td>' +
                        '<td class="' + dirClass + '">' + s.direction + '</td>' +
                        '<td>' + s.compression + '</td>' +
                        '<td style="color:' + (s.elephant==='YES'?'#00ff00':'#555') + '">' + s.elephant + '</td>' +
                        '<td>' + s.expansion + '</td>' +
                        '<td>' + s.time + '</td>' +
                    '</tr>';
                });
                html += '</tbody></table>';
                grid.innerHTML = html;
            }

            const dbg = document.getElementById('debug-content');
            dbg.innerHTML = 
                '<div class="debug-item">API ERRORS: ' + data.debug.api_errors + '</div>' +
                '<div class="debug-item">RECONNECTS: ' + data.debug.reconnects + '</div>' +
                '<div class="debug-item">SYMBOLS SCANNED: ' + data.debug.symbols_scanned + '</div>' +
                '<div class="debug-item">NEAR-SQZ DETECTED: ' + data.debug.near_sqz_count + '</div>' + 
                '<div class="debug-item">SQZ STRUCTURES: ' + data.debug.sqz_detections + '</div>' +
                '<div class="debug-item">EXPANSIONS: ' + data.debug.exp_detections + '</div>';

            const vBody = document.getElementById('verify-body');
            let vHtml = "";
            const sortedV = data.verification.sort((a,b) => a.spread - b.spread);
            
            sortedV.forEach(s => {
                let rowClass = "";
                let statusText = "NONE";
                let statusClass = "status-none";
                
                if (s.near_status === "VALID") {
                    statusText = "VALID";
                    statusClass = "status-valid";
                    rowClass = "row-valid";
                } else if (s.near_status === "NEAR") {
                    statusText = "NEAR";
                    statusClass = "status-near";
                    rowClass = "row-near";
                }

                vHtml += '<tr class="' + rowClass + '">' +
                    '<td>' + s.symbol + '</td>' +
                    '<td>' + s.tf + '</td>' +
                    '<td>' + s.price + '</td>' +
                    '<td>' + s.spread + '%</td>' +
                    '<td class="' + statusClass + '">' + statusText + '</td>' +
                    '<td>' + s.sqz_type + '</td>' +
                    '<td>' + s.cluster_cnt + '</td>' +
                '</tr>';
            });
            vBody.innerHTML = vHtml;
        }

        setInterval(update, 5000);
        update();
    </script>
</body>
</html>
"""

@app.route("/")
def home():
    return DASHBOARD_HTML

@app.route("/api/data")
def api():
    if t is None or not t.is_alive():
        start_thread()
    return jsonify({
        "signals": current_data['signals'],
        "verification": current_data['verification'],
        "exchange": current_data['exchange'],
        "scan_time": current_data['scan_time'],
        "timestamp": current_data['timestamp'],
        "debug": stats
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
