import pandas as pd
import numpy as np

class JeremiahEngine:
    def __init__(self):
        # STRICT 0.1% Threshold
        self.SQZ_THRESHOLD = 0.001 

    def calculate_sma(self, data, period):
        return data.rolling(window=period).mean()

    def check_sma_respect(self, df, current_index):
        """
        STRICT STRUCTURE FILTER: Violent whipsaws invalidate SQZ.
        """
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

        # Invalid if whipsaws detected
        if total_whipsaws > 2:
            return False, "WHIPSAW"
        
        # Invalid if chaotic compression (range huge vs body)
        curr_row = df.iloc[current_index]
        body = abs(curr_row['close'] - curr_row['open'])
        range_total = curr_row['high'] - curr_row['low']
        
        if range_total > body * 3 and total_whipsaws > 0:
            return False, "CHAOTIC"

        return True, "CLEAN"

    def get_active_cluster(self, df, current_index):
        """
        DYNAMIC CLUSTER DETECTION.
        Iterates backwards to identify ACTIVE compression structure.
        Returns: (cluster_df, cluster_count)
        """
        cluster_candles = []
        
        # Check lookback up to 100 candles
        start_idx = max(0, current_index - 100)
        
        for i in range(current_index - 1, start_idx - 1, -1):
            # Check SQZ Condition (0.1%)
            row = df.iloc[i]
            sma20 = df['sma20'].iloc[i]
            sma100 = df['sma100'].iloc[i]
            sma200 = df['sma200'].iloc[i]
            
            # Reuse SQZ Logic to find range
            sqz_type, is_sqz, _ = self.analyze_sqz(row, sma20, sma100, sma200)
            
            # TERMINATION 1: SQZ Breaks
            if not is_sqz:
                break
            
            # TERMINATION 2: Violent Separation (Price shoots away from SMAs)
            # We check spread. If > 0.5%, it's not "tight" compression anymore.
            vals = [row['close'], sma20, sma100]
            if pd.isna(sma100): vals = [row['close'], sma20, sma200]
            
            max_v = max(vals)
            min_v = min(vals)
            spread_pct = (max_v - min_v) / max_v
            
            if spread_pct > 0.005: # 0.5% separation threshold
                break
            
            # TERMINATION 3: Chaotic Whipsaw (Checked on individual candle context)
            body = abs(row['close'] - row['open'])
            rng = row['high'] - row['low']
            if rng > body * 3:
                break

            cluster_candles.append(row)
            
        return cluster_candles, len(cluster_candles)

    def analyze_sqz(self, row, sma20, sma100, sma200):
        """
        0.1% Convergence Check.
        Returns SQZ Type, Validity, and Spread %.
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
        spread_pct = 0.0

        # ALL TOGETHER (Price, 20, 100)
        is_20_100, d_20_100 = in_range(price, sma20, sma100)
        if is_20_100:
            sqz_type = "ALL TOGETHER"
            is_valid = True
            spread_pct = d_20_100
            
        # SPECIAL ONE (Price, 20, 200)
        if not is_valid:
            is_20_200, d_20_200 = in_range(price, sma20, sma200)
            if is_20_200:
                sqz_type = "SPECIAL ONE"
                is_valid = True
                spread_pct = d_20_200

        return sqz_type, is_valid, spread_pct

    def check_expansion(self, row, df, current_index):
        """
        DYNAMIC ELEPHANT BAR LOGIC.
        Evaluated relative ONLY to ACTIVE compression cluster.
        """
        # 1. Get Active Cluster
        cluster_candles, cluster_count = self.get_active_cluster(df, current_index)
        
        if not cluster_candles:
            return False, "NONE", "NEUTRAL", "No Active Compression"

        # 2. Calculate Dynamic Metrics from Cluster
        cluster_df = pd.DataFrame(cluster_candles)
        avg_body_cluster = cluster_df.apply(lambda x: abs(x['close'] - x['open']), axis=1).mean()
        
        # Compression Zone: Range of cluster
        cluster_zone_high = cluster_df['high'].max()
        cluster_zone_low = cluster_df['low'].min()
        
        # 3. Analyze Current Candle vs Cluster
        body = abs(row['close'] - row['open'])
        wick_lower = row['close'] - row['low'] if row['close'] > row['open'] else row['open'] - row['low']
        wick_upper = row['high'] - row['close'] if row['close'] > row['open'] else row['high'] - row['open']
        
        exp_type = "NONE"
        direction = "NEUTRAL"
        reason = "No Expansion"
        is_valid = False

        # 4. Elephant Bar Rules
        # Rule A: Dominance (Body > Average Body of Active Cluster)
        is_dominant = body > (avg_body_cluster * 1.5)
        
        # Rule B: Breakout (Outside Compression Zone)
        is_breakout = False
        
        if row['close'] > row['open']: # Bullish
            if row['high'] > cluster_zone_high:
                is_breakout = True
        else: # Bearish
            if row['low'] < cluster_zone_low:
                is_breakout = True
        
        if is_dominant and is_breakout:
            exp_type = "ELEPHANT"
            direction = "LONG" if row['close'] > row['open'] else "SHORT"
            reason = "Explosive Release"
            is_valid = True
            
        # 5. Tail Bar Rules
        elif wick_lower > (body * 2):
            exp_type = "TAIL BAR"
            direction = "LONG"
            reason = "Bullish Rejection"
            is_valid = True
        elif wick_upper > (body * 2):
            exp_type = "TAIL BAR"
            direction = "SHORT"
            reason = "Bearish Rejection"
            is_valid = True

        return is_valid, exp_type, direction, reason, cluster_count

    def scan_timeframe(self, df, tf_name):
        if len(df) < 200: return None
        df = df.copy()
        df['sma20'] = self.calculate_sma(df['close'], 20)
        df['sma100'] = self.calculate_sma(df['close'], 100)
        df['sma200'] = self.calculate_sma(df['close'], 200)

        idx = len(df) - 1
        row = df.iloc[idx]

        # 1. SQZ Check
        sqz_type, sqz_valid, spread_pct = self.analyze_sqz(row, df['sma20'].iloc[idx], df['sma100'].iloc[idx], df['sma200'].iloc[idx])
        
        # 2. SMA Respect
        is_respected, respect_status = self.check_sma_respect(df, idx)
        
        # 3. Expansion (Dynamic Logic)
        exp_valid, exp_type, exp_dir, exp_reason, cluster_count = self.check_expansion(row, df, idx)
        
        # 4. Calculate Individual Distances (DEBUG)
        price = row['close']
        dist_20 = abs(price - df['sma20'].iloc[idx]) / price
        dist_100 = abs(price - df['sma100'].iloc[idx]) / price
        dist_200 = abs(price - df['sma200'].iloc[idx]) / price
        
        # 5. Status
        status = "INVALID"
        if not is_respected:
            status = "INVALID"
            reason = respect_status
        elif exp_valid:
            status = "ACTIVE"
            reason = exp_reason
        elif sqz_valid:
            status = "WAIT"
            reason = "Compression Building"
        else:
            status = "WAIT"
            reason = "No SQZ"

        return {
            "tf": tf_name,
            "sqz_type": sqz_type,
            "status": status,
            "reason": reason,
            "spread_pct": round(spread_pct*100, 3),
            "expansion_type": exp_type,
            "direction": exp_dir,
            "expansion_status": "FIRED" if exp_valid else "NO",
            "valid": exp_valid, # Signal validity
            
            # DEBUG DATA
            "debug_dist_20": round(dist_20*100, 3),
            "debug_dist_100": round(dist_100*100, 3),
            "debug_dist_200": round(dist_200*100, 3),
            "debug_cluster_count": cluster_count
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
