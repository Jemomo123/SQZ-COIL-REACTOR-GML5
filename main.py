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

# --- EXCHANGE CONFIG (UPDATED TO PERP) ---
# Changed 'spot' to 'swap' (Perpetual) to match your chart
EXCHANGE_CONFIG = [
    ccxt.binance({'options': {'defaultType': 'future'}}), # Binance Futures
    ccxt.okx({'options': {'defaultType': 'swap'}})      # OKX Perpetual
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
                                "timeframe": d['timeframe'],
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
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.7rem; }
        th { text-align: left; border-bottom: 1px solid #333; padding: 5px; color: #00ff00; }
        td { padding: 5px; border-bottom: 1px solid #111; }
        .log-section { margin-top: 20px; border-top: 1px dashed #333; padding-top: 10px; }
        .log-title { color: #666; font-size: 0.6rem; margin-bottom: 5px; }
        .log-table { width: 100%; font-size: 0.6rem; color: #666; }
        .active { color: #00ff00; font-weight: bold; }
        .wait { color: #ffaa00; }
        .bull { color: #00ff00; }
        .bear { color: #ff0000; }
        .log-success { color: #444; }
        .log-fail { color: #aa0000; }
    </style>
</head>
<body>
    <div class="header">
        <div class="title">JEREMIAH // EXECUTION</div>
        <div class="stats" id="status">INITIALIZING...</div>
    </div>

    <div id="grid"></div>

    <div class="log-section">
        <div class="log-title">SCANNER CALL LOG (LAST 20)</div>
        <table class="log-table">
            <thead>
                <tr>
                    <th>TIME</th><th>STATUS</th><th>SIGS</th><th>TOP COIN</th><th>LATENCY</th>
                </tr>
            </thead>
            <tbody id="log-body"></tbody>
        </table>
    </div>

    <script>
        async function update() {
            try {
                const res = await fetch('/api/data');
                const json = await res.json();
                render(json);
            } catch (e) {
                document.getElementById('status').innerText = "SERVER ERROR";
            }
        }

        function render(data) {
            document.getElementById('status').innerHTML = 
                'EXCHANGE: ' + data.exchange + ' | LATENCY: ' + data.scan_time + ' | ' + data.timestamp;

            const grid = document.getElementById('grid');
            if (data.signals.length === 0) {
                grid.innerHTML = '<div style="text-align:center; color:#444; padding:20px;">NO ACTIVE STRUCTURES DETECTED</div>';
            } else {
                let html = '<table><thead><tr><th>SYM</th><th>TF</th><th>DIR</th><th>SQZ TYPE</th><th>VALID</th><th>CROSS</th><th>EXP</th><th>RESPECT</th></tr></thead><tbody>';
                data.signals.forEach(s => {
                    let vc = s.validity.toLowerCase();
                    let dc = s.direction.toLowerCase();
                    let rowStyle = s.validity === 'ACTIVE' ? 'background:#111' : '';
                    html += '<tr style="' + rowStyle + '">' +
                        '<td>' + s.symbol + '</td>' +
                        '<td>' + s.timeframe + '</td>' +
                        '<td class="' + dc + '">' + s.direction + '</td>' +
                        '<td>' + s.sqz_type + '</td>' +
                        '<td class="' + vc + '">' + s.validity + '</td>' +
                        '<td>' + s.crossover + '</td>' +
                        '<td>' + s.expansion + '</td>' +
                        '<td>' + s.sma_respect + '</td>' +
                    '</tr>';
                });
                html += '</tbody></table>';
                grid.innerHTML = html;
            }

            const logBody = document.getElementById('log-body');
            let logHtml = "";
            data.log.forEach(l => {
                let statusClass = l.status === 'SUCCESS' ? 'log-success' : 'log-fail';
                logHtml += '<tr>' +
                    '<td>' + l.time + '</td>' +
                    '<td class="' + statusClass + '">' + l.status + '</td>' +
                    '<td>' + l.count + '</td>' +
                    '<td>' + l.active_coin + '</td>' +
                    '<td>' + l.latency + '</td>' +
                '</tr>';
            });
            logBody.innerHTML = logHtml;
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
        "exchange": current_data['exchange'],
        "scan_time": current_data['scan_time'],
        "timestamp": current_data['timestamp'],
        "log": call_log
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
