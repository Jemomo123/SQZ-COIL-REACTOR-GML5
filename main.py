import os
import ccxt
import pandas as pd
from fastapi import FastAPI, HTTPException
from engine import SQZEngine

app = FastAPI(title="SQZ Expansion Scanner")
engine = SQZEngine()

# Helper to fetch data (Purely structural data)
def fetch_ohlcv(symbol, timeframe, limit=200):
    # Using Binance as default public source
    exchange = ccxt.binance() 
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        return pd.DataFrame()

@app.get("/")
def read_root():
    return {"status": "SQZ Scanner Online", "mode": "Strict Rule-Based"}

@app.get("/scan/{symbol}")
def scan_market(symbol: str):
    """
    Triggers a scan for the given symbol (e.g. BTC).
    Analyzes 3m, 5m, and 15m timeframes.
    """
    formatted_symbol = symbol.upper() + "/USDT"
    
    # Fetch Data
    df_3m = fetch_ohlcv(formatted_symbol, '3m')
    df_5m = fetch_ohlcv(formatted_symbol, '5m')
    df_15m = fetch_ohlcv(formatted_symbol, '15m')
    
    if df_3m.empty or df_5m.empty or df_15m.empty:
        raise HTTPException(status_code=400, detail="Could not fetch market data")

    # Run Engine
    result = engine.generate_signal(formatted_symbol, df_3m, df_5m, df_15m)
    
    return result

# For running via Cron Job on Render
@app.get("/cron")
def run_cron():
    """
    Endpoint specifically for Render Cron Jobs to hit.
    Scans a predefined list.
    """
    # Example: Scan BTC and ETH
    targets = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    results = []
    for target in targets:
        symbol_base = target.split('/')[0]
        try:
            res = scan_market(symbol_base)
            # Only save valid signals to save space/log clutter
            if res.get("final_status") == "VALID SIGNAL":
                results.append(res) 
        except Exception as e:
            # Log error but continue scanning other symbols
            print(f"Failed to scan {target}: {e}")
            pass
            
    return {"executed": True, "valid_signals_found": len(results), "data": results}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
