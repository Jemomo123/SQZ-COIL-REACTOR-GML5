import os
import time
import ccxt
import threading
from flask import Flask, jsonify
from engine import JeremiahEngine

app = Flask(__name__)
engine = JeremiahEngine()

# --- EXCHANGE CONFIG (OPTIMIZED FOR SPEED) ---
# Only OKX and MEXC with aggressive 1.5s timeouts
EXCHANGE_CONFIG = [
    ccxt.okx({'options': {'defaultType': 'spot'}, 'timeout': 1500}),
    ccxt.mexc({'options': {'defaultType': 'spot'}, 'timeout': 1500})
]

def fetch_data_failover(symbol):
    """
    Tries OKX then MEXC. Skips instantly if missing.
    """
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

def run_engine():
    """
    Core scanning loop. Runs live on request.
    """
    targets = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "PEPE", "SPX", "SPACE", "ZEC", "LINEA"]
    
    results = []
    active_exchange = "OFFLINE"
    scan_time = 0
    start_time = time.time()
    
    for sym in targets:
        try:
            dfs, ex_name = fetch_data_failover(sym)
            if dfs:
                active_exchange = ex_name
                master = engine.generate_master_signal(sym + "/USDT", dfs['3m'], dfs['5m'], dfs['15m'])
                
                if master:
                    d = master['data_15m']
                    # Only show Valid or Wait
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
                            "exchange": active_exchange
                        })
        except Exception as e:
            pass

    scan_time = round(time.time() - start_time, 2)
    
    return {
        "signals": results,
        "exchange": active_exchange,
        "scan_time": f"{scan_time}s",
        "timestamp": pd.Timestamp.now().strftime("%H:%M:%S")
    }

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
        
        .blink { animation: blinker 1s linear infinite; }
        @keyframes blinker { 50% { opacity: 0; } }
        
        .empty-msg { text-align: center; color: #444; margin-top: 20px; font-size: 0.8rem; }
    </style>
</head>
<body>
    <div class="header">
        <div class="title">JEREMIAH // EXECUTION</div>
        <div class="stats" id="status">SCANNING MARKET...</div>
    </div>

    <div id="grid"></div>

    <script>
        async function update() {
            const res = await fetch('/api/data');
            const json = await res.json();
            render(json);
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
    return jsonify(run_engine())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, threaded=True)
