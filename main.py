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
current_data = {"signals": [], "exchange": "STARTING...", "scan_time": "0s", "timestamp": "00:00:00"}
call_log = []

# --- EXCHANGE CONFIG (ORDERED PRIORITY) ---
EXCHANGE_CONFIG = [
    ccxt.binance({'options': {'defaultType': 'future'}}),  # 1. Binance
    ccxt.okx({'options': {'defaultType': 'swap'}}),       # 2. OKX
    ccxt.mexc({'options': {'defaultType': 'swap'}}),      # 3. MEXC
    ccxt.gate({'options': {'defaultType': 'future'}})      # 4. Gate.io
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
            print(f"Failover {ex.name}: {e}")
            continue
    return None, "OFFLINE"

def scanner_loop():
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
                        # Main Data
                        s15 = master['status_15m']
                        
                        # Determine Overall Status based on strict rules
                        # Must be VALID SQZ + COMP + EXPANSION
                        overall_status = "INVALID"
                        
                        if s15['status'] == "ACTIVE":
                            overall_status = "ACTIVE"
                        elif s15['status'] == "WAIT":
                            overall_status = "WAIT"
                        
                        # Only add if there is some activity (Wait or Active)
                        if s15['status'] != "INVALID":
                            results.append({
                                "symbol": sym,
                                "price": master['price'],
                                "sqz_type": s15['sqz_type'],
                                "s3": master['status_3m']['status'], # 3m status
                                "s5": master['status_5m']['status'], # 5m status
                                "s15": s15['status'],            # 15m status
                                "compression": s15['comp_status'],
                                "expansion": s15['exp_type'],
                                "direction": s15['exp_dir'],
                                "reason": s15['reason'],
                                "signal": overall_status,
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
        
        # Update Log
        log_entry = {
            "time": current_data['timestamp'],
            "active_coin": results[0]['symbol'] if results else "-",
            "latency": f"{scan_time}s"
        }
        call_log.insert(0, log_entry)
        if len(call_log) > 10: call_log.pop()
        
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
    <title>JEREMIAH EXECUTION ENGINE</title>
    <style>
        body { background-color: #000; color: #00ff00; font-family: 'Courier New', monospace; padding: 10px; font-size: 11px; }
        .header { border-bottom: 2px solid #00ff00; padding-bottom: 10px; margin-bottom: 10px; text-align: center; }
        .title { font-size: 1.2rem; font-weight: bold; letter-spacing: 2px; }
        .stats { font-size: 0.7rem; color: #888; margin-top: 5px; }
        
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.65rem; }
        th { text-align: left; border-bottom: 1px solid #333; padding: 4px; color: #00ff00; }
        td { padding: 4px; border-bottom: 1px solid #111; }
        
        .debug-section { margin-top: 20px; border-top: 1px dashed #444; padding-top: 10px; }
        .debug-title { color: #00ff00; font-size: 0.7rem; margin-bottom: 5px; }
        .debug-item { color: #666; font-size: 0.6rem; margin-bottom: 2px; }
        
        .active { color: #00ff00; font-weight: bold; }
        .wait { color: #ffaa00; }
        .log-success { color: #444; }
    </style>
</head>
<body>
    <div class="header">
        <div class="title">JEREMIAH // EXECUTION</div>
        <div class="stats" id="status">INITIALIZING...</div>
    </div>

    <div id="grid"></div>

    <div class="debug-section">
        <div class="debug-title">DEBUG PANEL (LAST SCAN)</div>
        <div id="debug-content"></div>
    </div>

    <div class="debug-section">
        <div class="debug-title">SCANNER LOG</div>
        <div id="log-content"></div>
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
            // Header
            document.getElementById('status').innerHTML = 
                'EXCHANGE: ' + data.exchange + ' | LATENCY: ' + data.scan_time + ' | ' + data.timestamp;

            // Table
            const grid = document.getElementById('grid');
            if (data.signals.length === 0) {
                grid.innerHTML = '<div style="text-align:center; color:#333; padding:20px;">NO ACTIVE STRUCTURES (WAITING FOR 0.2% SQZ)</div>';
            } else {
                let html = '<table><thead><tr><th>SYM</th><th>PRC</th><th>SQZ</th><th>3m</th><th>5m</th><th>15m</th><th>CMP</th><th>EXP</th><th>DIR</th><th>SIG</th></tr></thead><tbody>';
                data.signals.forEach(s => {
                    let vc = s.signal.toLowerCase();
                    let dc = s.direction.toLowerCase();
                    let bg = s.signal === 'ACTIVE' ? 'background:#111' : '';
                    
                    html += '<tr style="' + bg + '">' +
                        '<td>' + s.symbol + '</td>' +
                        '<td>' + s.price + '</td>' +
                        '<td>' + s.sqz_type + '</td>' +
                        '<td style="color:' + (s.s3==='ACTIVE'?'#00ff00':'#555') + '">' + s.s3 + '</td>' +
                        '<td style="color:' + (s.s5==='ACTIVE'?'#00ff00':'#555') + '">' + s.s5 + '</td>' +
                        '<td style="color:' + (s.s15==='ACTIVE'?'#00ff00':'#555') + '">' + s.s15 + '</td>' +
                        '<td>' + s.compression + '</td>' +
                        '<td>' + s.expansion + '</td>' +
                        '<td class="' + dc + '">' + s.direction + '</td>' +
                        '<td class="' + vc + '">' + s.signal + '</td>' +
                    '</tr>';
                });
                html += '</tbody></table>';
                grid.innerHTML = html;
            }

            // Debug Panel (Latest Coin)
            const dbg = document.getElementById('debug-content');
            if (data.signals.length > 0) {
                let s = data.signals[0];
                dbg.innerHTML = 
                    '<div class="debug-item">SYM: ' + s.symbol + ' | REASON: ' + s.reason + '</div>' +
                    '<div class="debug-item">SQZ: ' + s.sqz_type + ' | COMPRESS: ' + s.compression + '</div>' +
                    '<div class="debug-item">EXPANSION: ' + s.expansion + ' (' + s.direction + ')</div>';
            } else {
                dbg.innerHTML = '<div class="debug-item">No Signal Data Available</div>';
            }

            // Logs
            const logs = document.getElementById('log-content');
            let lHtml = "";
            data.log.forEach(l => {
                lHtml += '<span style="margin-right:15px;">[' + l.time + '] ' + l.active_coin + ' (' + l.latency + ')</span>';
            });
            logs.innerHTML = lHtml;
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
