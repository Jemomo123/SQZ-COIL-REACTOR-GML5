import os
import time
import ccxt
import threading
from flask import Flask, jsonify
from engine import JeremiahEngine

app = Flask(__name__)
engine = JeremiahEngine()

# --- SHARED CACHE ---
current_data = {
    "signals": [],
    "exchange": "STARTING...",
    "scan_time": "0s",
    "timestamp": "00:00:00",
    "status": "INITIALIZING"
}

# --- EXCHANGE CONFIG (UPDATED) ---
# Removed Bybit per request. Kept OKX and MEXC for best free data.
EXCHANGE_CONFIG = [
    ccxt.binance({'options': {'defaultType': 'spot'}, 'timeout': 3000}),
    ccxt.gate({'options': {'defaultType': 'spot'}, 'timeout': 3000}),
    ccxt.okx({'options': {'defaultType': 'spot'}, 'timeout': 3000}),
    ccxt.mexc({'options': {'defaultType': 'spot'}, 'timeout': 3000})
]

def fetch_data_failover(symbol):
    """
    Tries exchanges. Returns data or None.
    """
    pair = symbol + '/USDT'
    
    for ex in EXCHANGE_CONFIG:
        try:
            if not ex.markets: ex.load_markets()
            if pair not in ex.markets: continue 

            dfs = {}
            # Fetch required timeframes
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
    Runs in a separate background thread.
    Never blocks the website.
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
                        # Only store if Valid or Wait
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
                                "whipsaw": "YES" if "WHIPSAW" in d['sma_status'] else "NO",
                                "timeframe": "15m",
                                "exchange": active_ex
                            })
            except Exception as e:
                pass

        # Update Global Cache
        scan_duration = round(time.time() - start_time, 3)
        current_data['signals'] = results
        current_data['exchange'] = active_ex
        current_data['scan_time'] = f"{scan_duration}s"
        current_data['timestamp'] = pd.Timestamp.now().strftime("%H:%M:%S")
        current_data['status'] = "ONLINE"
        
        time.sleep(6)

# --- START BACKGROUND THREAD ---
t = threading.Thread(target=scanner_loop, daemon=True)
t.start()

# --- HTML DASHBOARD ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JEREMIAH EXECUTION ENGINE</title>
    <style>
        body { background-color: #000; color: #00ff00; font-family: 'Courier New', monospace; padding: 10px; }
        .header { border-bottom: 2px solid #00ff00; padding-bottom: 10px; margin-bottom: 15px; text-align: center; }
        .title { font-size: 1.2rem; font-weight: bold; letter-spacing: 2px; }
        .stats { font-size: 0.7rem; color: #888; margin-top: 5px; }
        
        table { width: 100%; border-collapse: collapse; font-size: 0.7rem; margin-top: 10px; }
        th { text-align: left; border-bottom: 1px solid #333; padding: 5px; color: #00ff00; }
        td { padding: 5px; border-bottom: 1px solid #111; }
        
        .active { color: #00ff00; font-weight: bold; }
        .wait { color: #ffaa00; }
        .invalid { color: #ff0000; }
        .bull { color: #00ff00; }
        .bear { color: #ff0000; }
        
        .empty-msg { text-align: center; color: #444; margin-top: 20px; font-size: 0.8rem; }
    </style>
</head>
<body>
    <div class="header">
        <div class="title">JEREMIAH // EXECUTION</div>
        <div class="stats" id="status">CONNECTING...</div>
    </div>

    <div id="grid"></div>

    <script>
        async function update() {
            try {
                const res = await fetch('/api/data');
                const json = await res.json();
                render(json);
            } catch (e) {
                document.getElementById('status').innerText = "CONNECTION ERROR";
            }
        }

        function render(data) {
            document.getElementById('status').innerHTML = 
                `EXCHANGE: ${data.exchange} | LATENCY: ${data.scan_time} | ${data.timestamp}`;

            const grid = document.getElementById('grid');
            
            if (data.signals.length === 0) {
                grid.innerHTML = `<div class="empty-msg">NO ACTIVE STRUCTURES DETECTED</div>`;
                return;
            }

            let html = `<table><thead><tr>
                <th>SYM</th><th>DIR</th><th>SQZ TYPE</th><th>VALID</th><th>CROSS</th><th>EXP</th><th>RESPECT</th>
            </tr></thead><tbody>`;

            data.signals.forEach(s => {
                let validClass = s.validity.toLowerCase();
                let dirClass = s.direction.toLowerCase();
                
                if(s.validity === 'ACTIVE') html += `<tr style="background:#111;">`;
                else html += `<tr>`;

                html += `
                    <td>${s.symbol}</td>
                    <td class="${dirClass}">${s.direction}</td>
                    <td>${s.sqz_type}</td>
                    <td class="${validClass}">${s.validity}</td>
                    <td>${s.crossover}</td>
                    <td>${s.expansion} <br> <small>El:${s.elephant} / Tl:${s.tail}</small></td>
                    <td>${s.sma_respect}</td>
                </tr>`;
            });
            html += `</tbody></table>`;
            grid.innerHTML = html;
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
    return jsonify(current_data)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
