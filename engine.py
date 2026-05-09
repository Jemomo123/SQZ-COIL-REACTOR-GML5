import pandas as pd
import numpy as np

class JeremiahEngine:
    def __init__(self):
        self.SQZ_THRESHOLD = 0.005 # 0.5%

    def calculate_sma(self, data, period):
        return data.rolling(window=period).mean()

    def check_sma_respect(self, df, current_index):
        """
        SMA RESPECT RULE:
        Detects if structure is CLEAN or CHAOTIC.
        Checks for violent crossings and whipsaws in the last 10 candles.
        """
        if current_index < 20:
            return False, "INSUFFICIENT DATA"

        # Look at last 10 candles
        window = df.iloc[current_index-10:current_index+1]
        
        # Calculate SMAs for the window
        sma20 = self.calculate_sma(window['close'], 20)
        sma100 = self.calculate_sma(window['close'], 100)
        sma200 = self.calculate_sma(window['close'], 200)
        
        # Detect Crossings (SMA20 vs SMA100/200)
        # A crossing is where the sign of the difference changes
        diff_20_100 = sma20 - sma100
        diff_20_200 = sma20 - sma200
        
        # Count sign changes
        sign_changes_100 = np.sign(diff_20_100).diff().abs().sum()
        sign_changes_200 = np.sign(diff_20_200).diff().abs().sum()
        
        total_whipsaws = sign_changes_100 + sign_changes_200

        # VALIDATION LOGIC
        if total_whipsaws > 2:
            return False, "WHIPSAW DETECTED"
        
        # Check if current candle is "messy" (Violent rejection through SMAs)
        curr_row = df.iloc[current_index]
        curr_sma20 = sma20.iloc[-1]
        curr_sma100 = sma100.iloc[-1]
        
        # If price is chopping wildly around SMAs
        body = abs(curr_row['close'] - curr_row['open'])
        range_total = curr_row['high'] - curr_row['low']
        
        # If range is huge but body is small (Indecision/Chaos) inside compression zone
        if range_total > body * 3 and total_whipsaws > 0:
            return False, "CHAOTIC COMPRESSION"

        return True, "SMA RESPECTED"

    def check_crossover(self, df, current_index, sma_fast, sma_slow):
        """
        Detects if crossover just happened (Alignment).
        """
        if current_index < 2: return False, "None"
        
        # Current vs Previous
        curr_diff = sma_fast.iloc[current_index] - sma_slow.iloc[current_index]
        prev_diff = sma_fast.iloc[current_index-1] - sma_slow.iloc[current_index-1]
        
        # Bull Crossover
        if prev_diff < 0 and curr_diff >= 0:
            return True, "BULL CROSS"
        # Bear Crossover
        elif prev_diff > 0 and curr_diff <= 0:
            return True, "BEAR CROSS"
            
        return False, "HOLDING"

    def analyze_sqz(self, row, sma20, sma100, sma200):
        """
        STRICT SQZ DEFINITIONS
        """
        price = row['close']
        
        def in_range(v1, v2, v3):
            vals = [v for v in [v1, v2, v3] if pd.notna(v)]
            if len(vals) < 3: return False
            return (max(vals) - min(vals)) <= max(vals) * self.SQZ_THRESHOLD

        sqz_type = "NONE"
        valid = False

        # 1. ALL TOGETHER (Price, 20, 100)
        if pd.notna(sma100) and in_range(price, sma20, sma100):
            sqz_type = "ALL TOGETHER"
            valid = True
            
        # 2. SPECIAL ONE (Price, 20, 200)
        elif pd.notna(sma200) and in_range(price, sma20, sma200):
            sqz_type = "SPECIAL ONE"
            valid = True

        return sqz_type, valid

    def check_expansion(self, row, df, current_index):
        """
        EXPANSION LOGIC: Elephant or Tail Bar
        """
        body = abs(row['close'] - row['open'])
        wick_lower = row['close'] - row['low'] if row['close'] > row['open'] else row['open'] - row['low']
        wick_upper = row['high'] - row['close'] if row['close'] > row['open'] else row['high'] - row['open']
        
        # Context
        lookback = df.iloc[max(0, current_index-10):current_index+1]
        avg_body = lookback.apply(lambda x: abs(x['close'] - x['open']), axis=1).mean()
        if avg_body == 0: avg_body = body

        exp_type = "NONE"
        direction = "NEUTRAL"
        
        # ELEPHANT BAR
        if body > (avg_body * 1.5):
            exp_type = "ELEPHANT"
            direction = "BULLISH" if row['close'] > row['open'] else "BEARISH"
            
        # TAIL BAR
        elif wick_lower > (body * 2):
            exp_type = "TAIL BAR"
            direction = "BULLISH"
        elif wick_upper > (body * 2):
            exp_type = "TAIL BAR"
            direction = "BEARISH"

        return exp_type, direction

    def scan_timeframe(self, df, tf_name):
        """
        Executes full structural scan for one timeframe.
        """
        if len(df) < 200: return None
        
        df = df.copy()
        df['sma20'] = self.calculate_sma(df['close'], 20)
        df['sma100'] = self.calculate_sma(df['close'], 100)
        df['sma200'] = self.calculate_sma(df['close'], 200)

        idx = len(df) - 1
        row = df.iloc[idx]

        # 1. Check SQZ Type & Validity
        sqz_type, is_sqz_valid = self.analyze_sqz(row, df['sma20'].iloc[idx], df['sma100'].iloc[idx], df['sma200'].iloc[idx])

        # 2. Check SMA Respect (Structure Cleanliness)
        is_respected, respect_status = self.check_sma_respect(df, idx)
        
        # 3. Check Crossover
        cross_active, cross_type = "NO", "NONE"
        if is_sqz_valid and is_respected:
            # Check 20/100 cross
            ca, ct = self.check_crossover(df, idx, df['sma20'], df['sma100'])
            if ca:
                cross_active, cross_type = "YES", ct
            else:
                # Check 20/200 cross
                ca, ct = self.check_crossover(df, idx, df['sma20'], df['sma200'])
                if ca:
                    cross_active, cross_type = "YES", ct

        # 4. Check Expansion
        exp_type, exp_dir = self.check_expansion(row, df, idx)
        
        # DETERMINE FINAL VALIDITY
        # Must be SQZ + Respect + Expansion
        final_validity = "INVALID"
        if is_sqz_valid and is_respected and exp_type != "NONE":
            final_validity = "ACTIVE"
        elif is_sqz_valid and not is_respected:
            final_validity = "INVALID" # SMA Broken/Chaotic
        elif is_sqz_valid and is_respected and exp_type == "NONE":
            final_validity = "WAIT" # Compression active, waiting for expansion

        return {
            "timeframe": tf_name,
            "sqz_type": sqz_type,
            "validity": final_validity,
            "sma_status": respect_status,
            "crossover": cross_type,
            "expansion_type": exp_type,
            "expansion_dir": exp_dir,
            "elephant_detected": "YES" if exp_type == "ELEPHANT" else "NO",
            "tail_detected": "YES" if exp_type == "TAIL BAR" else "NO"
        }

    def generate_master_signal(self, symbol, data_3m, data_5m, data_15m):
        """
        Master Logic: MEGA SQZ detection and Timeframe Priority.
        """
        res_3m = self.scan_timeframe(data_3m, "3m")
        res_5m = self.scan_timeframe(data_5m, "5m")
        res_15m = self.scan_timeframe(data_15m, "15m")

        if not res_3m or not res_5m or not res_15m:
            return None

        # MEGA SQZ CHECK
        is_mega = False
        if res_3m['sqz_type'] == res_5m['sqz_type'] == res_15m['sqz_type'] and res_3m['sqz_type'] != "NONE":
            is_mega = True
            # If MEGA, display MEGA type
            res_15m['sqz_type'] = f"MEGA {res_15m['sqz_type']}"

        # Priority: 15m is final, 5m confirm, 3m early.
        # Return the 15m state as primary, but note MEGA if present.
        return {
            "symbol": symbol,
            "data_15m": res_15m,
            "mega_status": is_mega,
            "timestamp": pd.Timestamp.now().strftime("%H:%M:%S")
        }
