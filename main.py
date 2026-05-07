import os
import time
import logging
import ccxt
from dotenv import load_dotenv
from engine import StructureEngine

# ──────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────
load_dotenv()

# Render Free Tier Optimization
SCANNER_INTERVAL = 10     # Sleep 10s between scans (Saves CPU)
WARMUP_SECONDS = 300      # 5min buffer after restart (Rule 9/14 Safety)
SYMBOLS = os.getenv("WATCHLIST", "BTC/USDT,ETH/USDT,SOL/USDT,DOGE/USDT").split(",")

# Rule #13: EXCHANGE FAILOVER PRIORITY
EXCHANGE_PRIORITY = ['binance', 'bybit', 'okx']

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)

# ──────────────────────────────────────────────────────────────────────────
# EXCHANGE MANAGER (FAILOVER SYSTEM - Rule #13)
# ──────────────────────────────────────────────────────────────────────────
class ExchangeManager:
    def __init__(self):
        self.exchanges = []
        self._init_exchanges()

    def _init_exchanges(self):
        """Initialize all exchanges in the priority list"""
        for name in EXCHANGE_PRIORITY:
            try:
                # Create exchange instance with rate limiting enabled (Free Tier friendly)
                ex_class = getattr(ccxt, name)
                ex = ex_class({'enableRateLimit': True})
                self.exchanges.append(ex)
                logging.info(f"✅ Loaded Exchange: {name}")
            except Exception as e:
                logging.error(f"❌ Failed to load {name}: {e}")

    def fetch_candles(self, symbol, timeframe):
        """
        Attempts to fetch data from exchanges in priority order.
        Returns: (DataFrame) or None
        """
        # Convert symbol format for CCXT if necessary (e.g., Binance uses /, others might differ)
        # CCXT handles most normalization, but we keep it standard.
        
        for ex in self.exchanges:
            try:
                # Fetch last 250 candles
                ohlcv = ex.fetch_ohlcv(symbol, timeframe, limit=250)
                
                if not ohlcv:
                    raise Exception("No data returned")

                # Convert to DataFrame
                import pandas as pd
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                return df, ex.id # Return data + which exchange succeeded

            except Exception as e:
                # Failover Trigger: Log the warning and try next exchange
                # We only log if it's a critical error to avoid spamming "Rate Limit" logs
                if "MarketNotOpen" not in str(e) and "ExchangeError" not in str(e):
                    pass # Silently switching
                else:
                    logging.warning(f"⚠️ {ex.id} failed ({symbol}): {str(e)[:30]}. Trying next...")
                continue
        
        # If all exchanges fail
        return None, None

# ──────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ──────────────────────────────────────────────────────────────────────────
def run():
    logging.info("🚀 SYSTEM INITIALIZING...")
    
    engine = StructureEngine()
    ex_manager = ExchangeManager()
    
    if not ex_manager.exchanges:
        logging.critical("💥 No exchanges loaded. Exiting.")
        return

    start_time = time.time()
    
    try:
        while True:
            # 1. WARMUP CHECK (Safety Mechanism)
            elapsed = time.time() - start_time
            is_warming_up = elapsed < WARMUP_SECONDS
            
            if is_warming_up:
                remaining = int(WARMUP_SECONDS - elapsed)
                if remaining % 60 == 0:
                    logging.info(f"🛡️  WARMUP MODE: {remaining}s until signals active.")

            # 2. SCAN SYMBOLS
            for symbol in SYMBOLS:
                try:
                    # A. Fetch Data WITH FAILOVER
                    # We fetch 3m, 5m, 15m. The engine will check alignment.
                    # If one timeframe fails, we treat as missing data for that symbol.
                    
                    df_3m, source_3m = ex_manager.fetch_candles(symbol, '3m')
                    df_5m, source_5m = ex_manager.fetch_candles(symbol, '5m')
                    df_15m, source_15m = ex_manager.fetch_candles(symbol, '15m')
                    
                    # Skip if critical data (5m) is missing
                    if df_5m is None or len(df_5m) < 200:
                        continue

                    # Log successful data source (Optional, keeps user informed of failover)
                    # logging.debug(f"📡 {symbol} via {source_5m}")

                    # B. Process Logic
                    signal = engine.process_tick(
                        symbol, 
                        df_3m, df_5m, df_15m, 
                        df_5m.iloc[-1]
                    )

                    # C. Handle Signal
                    if signal:
                        if is_warming_up:
                            logging.warning(f"🔒 BLOCKED (Warmup): {symbol} signal ignored.")
                        else:
                            # Add source exchange to signal info
                            signal['source'] = source_5m
                            logging.info(f"✅ SIGNAL FOUND: {signal}")
                            # TODO: Add Discord/Telegram Webhook logic here

                except Exception as sym_error:
                    logging.error(f"⚠️  Scan Error {symbol}: {str(sym_error)[:40]}")
                    continue

            # 3. SLEEP (CPU Management)
            time.sleep(SCANNER_INTERVAL)

    except KeyboardInterrupt:
        logging.info("🛑 SYSTEM SHUTDOWN")
    except Exception as e:
        logging.critical(f"💥 CRITICAL FAILURE: {e}")
        # Render will auto-restart

if __name__ == "__main__":
    run()
