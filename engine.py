import pandas as pd
import numpy as np

class JeremiahEngine:
    def __init__(self):
        # STRICT 0.1% Threshold (Tightened from 0.2%)
        self.SQZ_THRESHOLD = 0.001 

    def calculate_sma(self, data, period):
        return data.rolling(window=period).mean()

    def check_sma_respect(self, df, current_index):
        """
        STRICT STRUCTURE RULE:
        Rejects if price is violently whipsawing through SMAs.
        """
        if current_index < 20:
            return False, "INSUFFICIENT DATA"
        
        window = df.iloc[current_index-10:current_index+1]
        sma20 = self.calculate_sma(window['close'], 20)
        sma100 = self.calculate_sma(window['close'], 100)
        sma200 = self.calculate_sma(window['close'], 200)
        
        # Detect Crossings
        diff_20_100 = sma20 - sma100
        diff_20_200 = sma20 - sma200
        
        sign_changes_100 = np.sign(diff_20_100).diff().abs().sum()
        sign_changes_200 = np.sign(diff_20_200).diff().abs().sum()
        total_whipsaws = sign_changes_100 + sign_changes_200

        # Invalid if whipsaws detected
        if total_whipsaws > 2:
            return False, f"REJECTED: Whipsaw Detected ({total_whipsaws})"
        
        # Invalid if chaotic compression (range huge vs body)
        curr_row = df.iloc[current_index]
        body = abs(curr_row['close'] - curr_row['open'])
        range_total = curr_row['high'] - curr_row['low']
        
        if range_total > body * 3 and total_whipsaws > 0:
            return False, "REJECTED: Chaotic Compression"

        return True, "SMA RESPECTED"

    def check_compression(self, df, current_index):
        """
        Compression = Tightening candle ranges.
        """
        if current_index < 10:
            return False, 0.0, "WAIT"
        
        current_range = df.iloc[current_index]['high'] - df.iloc[current_index]['low']
        avg_range = (df.iloc[current_index-10:current_index]['high'] - df.iloc[current_index-10:current_index]['low']).mean()
        
        if avg_range == 0: avg_range = current_range
        
        # Rule: Current range <= Average * 0.8
        is_compressed = current_range <= avg_range * 0.8
        
        pct = (current_range / df.iloc[current_index]['close'])
        
        if is_compressed:
            return True, pct, f"Compressed ({pct*100:.3f}%)"
        else:
            return False, pct, f"Expanding ({pct*100:.3f}%)"

    def check_expansion(self, row, df, current_index):
        """
        ELEPHANT or TAIL BAR.
        """
        body = abs(row['close'] - row['open'])
        wick_lower = row['close'] - row['low'] if row['close'] > row['open'] else row['open'] - row['low']
        wick_upper = row['high'] - row['close'] if row['close'] > row['open'] else row['high'] - row['open']
        total_range = row['high'] - row['low']
        
        if total_range == 0:
            return False, "NONE", "NEUTRAL", "No Candle Data"

        # Context
        lookback = df.iloc[max(0, current_index-10):current_index+1]
        avg_body = lookback.apply(lambda x: abs(x['close'] - x['open']), axis=1).mean()
        if avg_body == 0: avg_body = body

        exp_type = "NONE"
        direction = "NEUTRAL"
        reason = "No Expansion"

        # ELEPHANT BAR
        if body > (avg_body * 1.5):
            exp_type = "ELEPHANT"
            direction = "BULLISH" if row['close'] > row['open'] else "BEARISH"
            reason = "Strong Momentum"
            
        # TAIL BAR
        elif wick_lower > (body * 2):
            exp_type = "TAIL BAR"
            direction = "BULLISH"
            reason = "Bullish Rejection"
        elif wick_upper > (body * 2):
            exp_type = "TAIL BAR"
            direction = "BEARISH"
            reason = "Bearish Rejection"

        is_valid = exp_type in ["ELEPHANT", "TAIL BAR"]
        return is_valid, exp_type, direction, reason

    def analyze_sqz(self, row, sma20, sma100, sma200):
        """
        ALL TOGETHER (20/100) or SPECIAL ONE (20/200).
        0.1% Threshold (0.001).
        """
        price = row['close']
        
        def in_range(v1, v2, v3):
            vals = [v for v in [v1, v2, v3] if pd.notna(v)]
            if len(vals) < 3: return False, 0
            max_val = max(vals)
            min_val = min(vals)
            dist_pct = (max_val - min_val) / max_val
            return dist_pct <= self.SQZ_THRESHOLD, round(dist_pct*100, 3)

        sqz_type = "NONE"
        is_valid = False
        dist_pct = 0.0

        # ALL TOGETHER
        is_20_100, d_20_100 = in_range(price, sma20, sma100)
        if is_20_100:
            sqz_type = "ALL TOGETHER"
            is_valid = True
            dist_pct = d_20_100
            
        # SPECIAL ONE
        elif not is_valid:
            is_20_200, d_20_200 = in_range(price, sma20, sma200)
            if is_20_200:
                sqz_type = "SPECIAL ONE"
                is_valid = True
                dist_pct = d_20_200

        return sqz_type, is_valid, dist_pct

    def scan_timeframe(self, df, tf_name):
        if len(df) < 200: return None
        df = df.copy()
        df['sma20'] = self.calculate_sma(df['close'], 20)
        df['sma100'] = self.calculate_sma(df['close'], 100)
        df['sma200'] = self.calculate_sma(df['close'], 200)

        idx = len(df) - 1
        row = df.iloc[idx]

        # 1. Check SQZ
        sqz_type, sqz_valid, dist_pct = self.analyze_sqz(row, df['sma20'].iloc[idx], df['sma100'].iloc[idx], df['sma200'].iloc[idx])
        
        # 2. Check SMA Respect
        is_respected, respect_msg = self.check_sma_respect(df, idx)
        
        # 3. Check Compression
        is_comp, comp_pct, comp_msg = self.check_compression(df, idx)
        
        # 4. Check Expansion
        exp_valid, exp_type, exp_dir, exp_reason = self.check_expansion(row, df, idx)
        
        # Determine Final Status
        status = "INVALID"
        reason = ""
        
        if not sqz_valid:
            status = "INVALID"
            reason = f"No SQZ ({dist_pct}%)"
        elif not is_respected:
            status = "INVALID"
            reason = respect_msg
        elif not is_comp:
            status = "WAIT"
            reason = comp_msg
        elif not exp_valid:
            status = "WAIT"
            reason = "Waiting for Expansion"
        else:
            status = "ACTIVE"
            reason = exp_reason

        return {
            "tf": tf_name,
            "sqz_type": sqz_type,
            "status": status,
            "reason": reason,
            "dist_pct": dist_pct,
            "comp_status": "YES" if is_comp else "NO",
            "exp_type": exp_type,
            "exp_dir": exp_dir
        }

    def generate_master_signal(self, symbol, data_3m, data_5m, data_15m):
        res_3m = self.scan_timeframe(data_3m, "3m")
        res_5m = self.scan_timeframe(data_5m, "5m")
        res_15m = self.scan_timeframe(data_15m, "15m")

        if not res_3m or not res_5m or not res_15m:
            return None

        # MEGA SQZ CHECK
        is_mega = False
        if (res_3m['sqz_type'] == res_5m['sqz_type'] == res_15m['sqz_type'] and 
            res_3m['sqz_type'] != "NONE"):
            is_mega = True
            res_15m['sqz_type'] = f"MEGA {res_15m['sqz_type']}"

        # Prioritize 15m for execution, but report 3m/5m status
        return {
            "symbol": symbol,
            "price": float(data_15m.iloc[-1]['close']),
            "status_15m": res_15m,
            "status_5m": res_5m,
            "status_3m": res_3m,
            "mega_status": is_mega
        }
