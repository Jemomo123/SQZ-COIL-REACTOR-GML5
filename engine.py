import pandas as pd
import numpy as np

class JeremiahEngine:
    def __init__(self):
        self.SQZ_THRESHOLD = 0.005 

    def calculate_sma(self, data, period):
        return data.rolling(window=period).mean()

    def check_sma_respect(self, df, current_index):
        if current_index < 20:
            return False, "INSUFFICIENT DATA"
        window = df.iloc[current_index-10:current_index+1]
        sma20 = self.calculate_sma(window['close'], 20)
        sma100 = self.calculate_sma(window['close'], 100)
        sma200 = self.calculate_sma(window['close'], 200)
        
        diff_20_100 = sma20 - sma100
        diff_20_200 = sma20 - sma200
        
        sign_changes_100 = np.sign(diff_20_100).diff().abs().sum()
        sign_changes_200 = np.sign(diff_20_200).diff().abs().sum()
        total_whipsaws = sign_changes_100 + sign_changes_200

        if total_whipsaws > 2:
            return False, "WHIPSAW DETECTED"
        
        curr_row = df.iloc[current_index]
        curr_sma20 = sma20.iloc[-1]
        body = abs(curr_row['close'] - curr_row['open'])
        range_total = curr_row['high'] - curr_row['low']
        
        if range_total > body * 3 and total_whipsaws > 0:
            return False, "CHAOTIC COMPRESSION"

        return True, "SMA RESPECTED"

    def check_crossover(self, df, current_index, sma_fast, sma_slow):
        if current_index < 2: return False, "None"
        curr_diff = sma_fast.iloc[current_index] - sma_slow.iloc[current_index]
        prev_diff = sma_fast.iloc[current_index-1] - sma_slow.iloc[current_index-1]
        
        if prev_diff < 0 and curr_diff >= 0:
            return True, "BULL CROSS"
        elif prev_diff > 0 and curr_diff <= 0:
            return True, "BEAR CROSS"
        return False, "HOLDING"

    def analyze_sqz(self, row, sma20, sma100, sma200):
        price = row['close']
        def in_range(v1, v2, v3):
            vals = [v for v in [v1, v2, v3] if pd.notna(v)]
            if len(vals) < 3: return False
            return (max(vals) - min(vals)) <= max(vals) * self.SQZ_THRESHOLD

        sqz_type = "NONE"
        valid = False

        if pd.notna(sma100) and in_range(price, sma20, sma100):
            sqz_type = "ALL TOGETHER"
            valid = True
        elif pd.notna(sma200) and in_range(price, sma20, sma200):
            sqz_type = "SPECIAL ONE"
            valid = True

        return sqz_type, valid

    def check_expansion(self, row, df, current_index):
        body = abs(row['close'] - row['open'])
        wick_lower = row['close'] - row['low'] if row['close'] > row['open'] else row['open'] - row['low']
        wick_upper = row['high'] - row['close'] if row['close'] > row['open'] else row['high'] - row['open']
        
        lookback = df.iloc[max(0, current_index-10):current_index+1]
        avg_body = lookback.apply(lambda x: abs(x['close'] - x['open']), axis=1).mean()
        if avg_body == 0: avg_body = body

        exp_type = "NONE"
        direction = "NEUTRAL"
        
        if body > (avg_body * 1.5):
            exp_type = "ELEPHANT"
            direction = "BULLISH" if row['close'] > row['open'] else "BEARISH"
        elif wick_lower > (body * 2):
            exp_type = "TAIL BAR"
            direction = "BULLISH"
        elif wick_upper > (body * 2):
            exp_type = "TAIL BAR"
            direction = "BEARISH"

        return exp_type, direction

    def scan_timeframe(self, df, tf_name):
        if len(df) < 200: return None
        df = df.copy()
        df['sma20'] = self.calculate_sma(df['close'], 20)
        df['sma100'] = self.calculate_sma(df['close'], 100)
        df['sma200'] = self.calculate_sma(df['close'], 200)

        idx = len(df) - 1
        row = df.iloc[idx]

        sqz_type, is_sqz_valid = self.analyze_sqz(row, df['sma20'].iloc[idx], df['sma100'].iloc[idx], df['sma200'].iloc[idx])
        is_respected, respect_status = self.check_sma_respect(df, idx)
        
        cross_active, cross_type = "NO", "NONE"
        if is_sqz_valid and is_respected:
            ca, ct = self.check_crossover(df, idx, df['sma20'], df['sma100'])
            if ca:
                cross_active, cross_type = "YES", ct
            else:
                ca, ct = self.check_crossover(df, idx, df['sma20'], df['sma200'])
                if ca:
                    cross_active, cross_type = "YES", ct

        exp_type, exp_dir = self.check_expansion(row, df, idx)
        
        final_validity = "INVALID"
        if is_sqz_valid and is_respected and exp_type != "NONE":
            final_validity = "ACTIVE"
        elif is_sqz_valid and not is_respected:
            final_validity = "INVALID"
        elif is_sqz_valid and is_respected and exp_type == "NONE":
            final_validity = "WAIT"

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
        res_3m = self.scan_timeframe(data_3m, "3m")
        res_5m = self.scan_timeframe(data_5m, "5m")
        res_15m = self.scan_timeframe(data_15m, "15m")

        if not res_3m or not res_5m or not res_15m:
            return None

        is_mega = False
        if res_3m['sqz_type'] == res_5m['sqz_type'] == res_15m['sqz_type'] and res_3m['sqz_type'] != "NONE":
            is_mega = True
            res_15m['sqz_type'] = f"MEGA {res_15m['sqz_type']}"

        return {
            "symbol": symbol,
            "data_15m": res_15m,
            "mega_status": is_mega,
            "timestamp": pd.Timestamp.now().strftime("%H:%M:%S")
        }
