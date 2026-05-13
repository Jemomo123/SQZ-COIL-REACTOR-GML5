import pandas as pd
import numpy as np

class SimpleSQZEngine:
    def __init__(self):
        # STRICT 0.1% Threshold
        self.SQZ_THRESHOLD = 0.001 

    def calculate_sma(self, data, period):
        return data.rolling(window=period).mean()

    def analyze_sqz(self, row, sma20, sma100, sma200):
        """
        Check if Price + SMAs are within 0.1%.
        """
        price = row['close']
        
        # Helper to check range
        def in_range(v1, v2, v3):
            vals = [v for v in [v1, v2, v3] if pd.notna(v)]
            if len(vals) < 3: return False, 0, "NONE"
            max_val = max(vals)
            min_val = min(vals)
            dist_pct = (max_val - min_val) / max_val
            return dist_pct <= self.SQZ_THRESHOLD, dist_pct

        sqz_type = "NONE"
        is_valid = False
        spread_pct = 0.0

        # ALL TOGETHER
        is_20_100, d_20_100 = in_range(price, sma20, sma100)
        if is_20_100:
            sqz_type = "ALL TOGETHER"
            is_valid = True
            spread_pct = d_20_100
            
        # SPECIAL ONE
        if not is_valid:
            is_20_200, d_20_200 = in_range(price, sma20, sma200)
            if is_20_200:
                sqz_type = "SPECIAL ONE"
                is_valid = True
                spread_pct = d_20_200

        return is_valid, sqz_type, spread_pct

    def analyze_expansion(self, curr_row, prev_row, prev_was_sqz):
        """
        Check if Current Candle is an Elephant Bar breaking out.
        Logic: Breaks Previous Range + Large Body.
        """
        body_curr = abs(curr_row['close'] - curr_row['open'])
        body_prev = abs(prev_row['close'] - prev_row['open'])
        
        if body_prev == 0: body_prev = body_curr

        # Rule A: Dominance (Body > Previous Body * 1.5)
        is_dominant = body_curr > (body_prev * 1.5)
        
        # Rule B: Breakout (Close outside Previous Range)
        is_breakout = False
        direction = "NEUTRAL"
        
        if curr_row['close'] > prev_row['open']: # Bullish
            if curr_row['close'] > prev_row['high']:
                is_breakout = True
                direction = "LONG"
        else: # Bearish
            if curr_row['close'] < prev_row['low']:
                is_breakout = True
                direction = "SHORT"

        # Expansion is VALID only if Previous candle was SQZ (The setup exists)
        is_valid = prev_was_sqz and is_dominant and is_breakout
        
        exp_type = "ELEPHANT" if is_valid else "NONE"
        
        return is_valid, exp_type, direction

    def scan_timeframe(self, df, tf_name):
        if len(df) < 200: return None
        df = df.copy()
        df['sma20'] = self.calculate_sma(df['close'], 20)
        df['sma100'] = self.calculate_sma(df['close'], 100)
        df['sma200'] = self.calculate_sma(df['close'], 200)

        # Focus ONLY on last 2 candles (Current, Previous)
        if len(df) < 2: return None
        
        curr_idx = len(df) - 1
        prev_idx = len(df) - 2
        
        curr_row = df.iloc[curr_idx]
        prev_row = df.iloc[prev_idx]

        # 1. Check SQZ Status on BOTH candles
        prev_is_sqz, prev_sqz_type, prev_spread = self.analyze_sqz(prev_row, df['sma20'].iloc[prev_idx], df['sma100'].iloc[prev_idx], df['sma200'].iloc[prev_idx])
        curr_is_sqz, curr_sqz_type, curr_spread = self.analyze_sqz(curr_row, df['sma20'].iloc[curr_idx], df['sma100'].iloc[curr_idx], df['sma200'].iloc[curr_idx])
        
        # 2. Check Expansion on Current Candle (relative to Previous SQZ)
        exp_valid, exp_type, exp_dir = self.analyze_expansion(curr_row, prev_row, prev_is_sqz)
        
        # 3. Determine Status
        status = "INVALID"
        reason = "NO SQZ"
        
        if exp_valid:
            status = "ACTIVE"
            reason = "EXPLOSION RELEASE"
        elif curr_is_sqz:
            status = "WAIT"
            reason = "COMPRESSION BUILDING"
        
        # Debug: Use Current Spread for visibility
        debug_spread = curr_spread * 100

        return {
            "tf": tf_name,
            "status": status,
            "reason": reason,
            "sqz_type": curr_sqz_type,
            "spread_pct": debug_spread,
            "expansion_type": exp_type,
            "direction": exp_dir,
            "expansion_status": "FIRED" if exp_valid else "NO",
            "valid": exp_valid,
            # For Debug Panel
            "debug_dist_20": 0, # Simplified out to save speed
            "debug_dist_100": 0,
            "debug_dist_200": 0,
            "debug_cluster_cnt": 0
        }
