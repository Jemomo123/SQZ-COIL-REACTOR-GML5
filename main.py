import os
import time
import ccxt
import threading
from flask import Flask, jsonify
from engine import JeremiahEngine

app = Flask(__name__)
engine = JeremiahEngine()

# Cache to prevent API hammering
CACHE_TTL = 5
cache = {'data': None, 'timestamp': 0}

# Reduced to Top 5 Stable Exchanges to prevent hanging
# Removed weex/bingx as they often cause socket hangs
EXCHANGE_CONFIG = [
    ccxt.binance({'options': {'defaultType': 'spot'}, 'timeout': 2000, 'enableRateLimit': True}),
    ccxt.bybit({'options': {'defaultType': 'spot'}, 'timeout': 2000, 'enableRateLimit': True}),
    ccxt.okx({'options': {'defaultType': 'spot'}, 'timeout': 2000, 'enableRateLimit': True}),
    ccxt.mexc({'options': {'defaultType': 'spot'}, 'timeout': 2000, 'enableRateLimit': True}),
    ccxt.gate({'options': {'defaultType': 'spot'}, 'timeout': 2000, 'enableRateLimit': True}),
]

def fetch_data_failover(symbol):
    """
    Tries exchanges in order until one succeeds.
    Uses aggressive timeouts (2s) to prevent hanging.
    """
    pair = symbol + '/USDT'
    
    for ex in EXCHANGE_CONFIG:
        try:
            # Load markets (with aggressive error handling)
            if not ex.markets:
                try:
                    ex.load_markets()
                except Exception as e:
                    print(f"Market load fail {ex.name}: {e}")
                    continue

            # CRITICAL: Skip immediately if pair doesn't exist
            if pair not in ex.markets:
                continue 

            # Fetch required timeframes
            dfs = {}
            for tf in ['3m', '5m', '15m']:
                # Timeout is handled by the exchange config above (2000ms)
                bars = ex.fetch_ohlcv(pair, tf, limit=200)
                df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                dfs[tf] = df
            return dfs, ex.name
        except Exception as e:
            # Log but continue
            print(f"Fetch fail {ex.name} for {symbol}: {type(e).__name__}")
            continue
            
    return None, "OFFLINE"

def run_engine():
    """
    Core scanning loop.
    """
    global cache
    now = time.time()
    
    if cache['data'] and (now - cache['timestamp']) < CACHE_TTL:
        return cache['data']

    targets = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "PEPE", "SPX", "SPACE", "ZEC", "LINEA"]
    
    results = []
    active_exchange = "OFFLINE"
    scan_time = 0

    start = time.time()
    
    for sym in targets:
        try:
            dfs, ex_name = fetch_data_failover(sym)
            if dfs:
                active_exchange = ex_name
                
                # Run Engine
                master = engine.generate_master_signal(sym + "/USDT", dfs['3m'], dfs['5m'], dfs['15m'])
                
                if master:
                    d = master['data_15m']
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
                        "age": "0s",
                        "exchange": active_exchange
                    })
        except Exception as e:
            print(f"Error scanning {sym}: {e}")

    scan_time = round(time.time() - start, 3)
    
    output = {
        "signals": results,
        "exchange": active_exchange,
        "scan_time": f"{scan_time}s",
        "timestamp": pd.Timestamp.now().strftime("%H:%M:%S")
    }
    
    cache['data'] = output
    cache['timestamp'] = now
    return output

# DASHBOARD HTML (JEREMIAH STYLE)
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
        <div class="stats" id="status">INITIALIZING...</div>
    </div>

    <div id="grid">
        <!-- Table populated via JS -->
    </div>

    <script>
        async function update() {
            try {
                // Added 10 second timeout to prevent infinite "INITIALIZING"
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 10000);
                
                const res = await fetch('/api/data', { signal: controller.signal });
                clearTimeout(timeoutId);
                
                const json = await res.json();
                render(json);
            } catch (e) {
                document.getElementById('status').innerHTML = `CONNECTION ERROR OR TIMEOUT`;
            }
        }

        function render(data) {
            document.getElementById('status').innerHTML = 
                `EXCHANGE: ${data.exchange} | LATENCY: ${data.scan_time} | REFRESH: 5s`;

            const grid = document.getElementById('grid');
            
            const activeSignals = data.signals.filter(s => s.validity !== 'INVALID');

            if (activeSignals.length === 0) {
                grid.innerHTML = `<div class="empty-msg">NO ACTIVE STRUCTURES DETECTED</div>`;
                return;
            }

            let html = `<table><thead><tr>
                <th>SYM</th><th>DIR</th><th>SQZ TYPE</th><th>VALID</th><th>CROSS</th><th>EXP</th><th>RESPECT</th>
            </tr></thead><tbody>`;

            activeSignals.forEach(s => {
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
