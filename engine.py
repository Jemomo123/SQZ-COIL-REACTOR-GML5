import pandas as pd
import numpy as np

class StructureEngine:
    def __init__(self):
        # Ephemeral memory only. Resets on restart (Rule 14 / Free Tier Constraint)
        self.memory = {} 

    def get_memory(self, symbol):
        if symbol not in self.memory:
            self.memory[symbol] = {
                "last_sqz_type": None,
                "is_expanded": False
            }
        return self.memory[symbol]

    def process_tick(self, symbol, df_3m, df_5m, df_15m, current_tick):
        """
        Process market data and return a signal dictionary if valid.
        """
        mem = self.get_memory(symbol)
        
        # ─────────────────────────────────────────────────────────────
        # 1. MARKET VALIDITY FILTER (HARD GATE - Rule 1)
        # ─────────────────────────────────────────────────────────────
        if not self._is_valid_market(df_5m):
            return None

        # ─────────────────────────────────────────────────────────────
        # 2. SQZ DETECTION (Rule 2)
        # ─────────────────────────────────────────────────────────────
        is_sqz_5m, type_5m = self._detect_sqz(df_5m)
        is_sqz_3m, _ = self._detect_sqz(df_3m)
        is_sqz_15m, _ = self._detect_sqz(df_15m)
        is_mega = is_sqz_3m and is_sqz_5m and is_sqz_15m

        # ─────────────────────────────────────────────────────────────
        # 3. SQZ RESET & CYCLE MANAGEMENT (Rule 10)
        # ─────────────────────────────────────────────────────────────
        if not is_sqz_5m:
            # Structure broken, reset local memory
            mem["last_sqz_type"] = None
            mem["is_expanded"] = False
            return None
        
        # Check if we already signaled during this session (Rule 9 - One Shot)
        if mem["is_expanded"]:
            return None

        # ─────────────────────────────────────────────────────────────
        # 4. COMPRESSION CHECK (Rule 3)
        # ─────────────────────────────────────────────────────────────
        if not self._check_compression(df_5m):
            return None

        # ─────────────────────────────────────────────────────────────
        # 5. EXPANSION ENTRY (Rule 4)
        # ─────────────────────────────────────────────────────────────
        # Analyze the most recent candle
        current_candle = df_5m.iloc[-1]
        history = df_5m.iloc[-11:-1] # Last 10 closed candles for context
        
        exp_type, sweep = self._analyze_candle(current_candle, history)

        if exp_type in ["ELEPHANT", "TAIL"]:
            # LOCK SIGNAL (Rule 9)
            mem["is_expanded"] = True 
            mem["last_sqz_type"] = type_5m
            
            return {
                "symbol": symbol,
                "sqz_state": f"TYPE {type_5m} {'(MEGA)' if is_mega else ''}",
                "compression": "PRESENT",
                "expansion": exp_type,
                "sweep": sweep,
                "status": "VALID"
            }

        return None

    # ──────────────────────────────────────────────────────────────────
    # HELPER FUNCTIONS
    # ──────────────────────────────────────────────────────────────────
    
    def _is_valid_market(self, df):
        """Rule 1: Structure Check"""
        # Requires at least 100 candles for SMAs
        if len(df) < 200: return False
        
        close = df['close']
        sma20 = close.rolling(20).mean().iloc[-1]
        sma100 = close.rolling(100).mean().iloc[-1]
        
        # Simple structure check: SMAs must be aligned (not heavily tangled)
        # If SMAs are too close and crossing constantly, it's chop
        if abs(sma20 - sma100) < (close.iloc[-1] * 0.001): # 0.1% separation minimum
            return False
            
        return True

    def _detect_sqz(self, df):
        """Rule 2: Strict SQZ Definition"""
        if len(df) < 200: return False, None
        
        price = df['close'].iloc[-1]
        sma20 = df['close'].rolling(20).mean().iloc[-1]
        sma100 = df['close'].rolling(100).mean().iloc[-1]
        sma200 = df['close'].rolling(200).mean().iloc[-1]

        # Condition A: Price + SMA20 + SMA100 within 0.5%
        range_a = max(price, sma20, sma100) - min(price, sma20, sma100)
        avg_a = (price + sma20 + sma100) / 3
        if avg_a > 0 and (range_a / avg_a) <= 0.005:
            return True, "A"

        # Condition B: Price + SMA20 + SMA200 within 0.5%
        range_b = max(price, sma20, sma200) - min(price, sma20, sma200)
        avg_b = (price + sma20 + sma200) / 3
        if avg_b > 0 and (range_b / avg_b) <= 0.005:
            return True, "B"

        return False, None

    def _check_compression(self, df):
        """Rule 3: Reduced Volatility"""
        # Need enough history for average
        if len(df) < 25: return False
        
        recent_vol = (df['high'].iloc[-4:-1] - df['low'].iloc[-4:-1]).mean()
        avg_vol = (df['high'].iloc[-25:-1] - df['low'].iloc[-25:-1]).mean()
        
        # Recent range < 70% of average range
        return recent_vol < (avg_vol * 0.7)

    def _analyze_candle(self, current, history):
        """Rules 5, 6, 7: Identify Expansion"""
        body = abs(current['close'] - current['open'])
        range_c = current['high'] - current['low']
        
        if body == 0: return "NONE", "NONE"
        
        # Compare to recent average
        avg_body = (history['close'] - history['open']).abs().mean()
        
        # Elephant Bar (Rule 5)
        if body > (avg_body * 1.5):
            return "ELEPHANT", "NONE"
        
        # Tail Bar (Rule 6)
        wick_bottom = min(current['open'], current['close']) - current['low']
        wick_top = current['high'] - max(current['open'], current['close'])
        
        if wick_bottom > (body * 2) or wick_top > (body * 2):
            return "TAIL", "NONE"
            
        return "NONE", "NONE"
