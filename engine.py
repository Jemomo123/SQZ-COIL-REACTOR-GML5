import pandas as pd
import numpy as np

class SQZEngine:
    def __init__(self):
        # Threshold strictly defined in prompt (0.5%)
        self.SQZ_THRESHOLD = 0.005 

    def calculate_sma(self, data, period):
        return data.rolling(window=period).mean()

    def check_sqz(self, row, sma20, sma100, sma200):
        """
        Checks for 'All Together' or 'Special One' SQZ.
        Rule: Price, SMA20, and SMA100/200 all within 0.5% range.
        """
        price = row['close']
        
        # Check Range helper
        def in_range(v1, v2, v3):
            # Handle NaN values gracefully for comparison
            vals = [v for v in [v1, v2, v3] if pd.notna(v)]
            if len(vals) < 3: return False
            
            max_val = max(vals)
            min_val = min(vals)
            return (max_val - min_val) <= max_val * self.SQZ_THRESHOLD

        sqz_type = "None"

        # ALL TOGETHER SQZ
        if pd.notna(sma100) and in_range(price, sma20, sma100):
            sqz_type = "All Together"
        
        # SPECIAL ONE SQZ
        elif pd.notna(sma200) and in_range(price, sma20, sma200):
            sqz_type = "Special One"

        return sqz_type

    def check_compression(self, df, current_index):
        """
        Compression = tightening candle ranges + reduced volatility.
        Logic: Current range is smaller than the average range of the previous 10 candles.
        """
        if current_index < 10:
            return False, 0.0
        
        current_range = df.iloc[current_index]['high'] - df.iloc[current_index]['low']
        avg_range = (df.iloc[current_index-10:current_index]['high'] - df.iloc[current_index-10:current_index]['low']).mean()
        
        # Avoid division by zero
        if avg_range == 0: avg_range = current_range
        
        # If current range is tight compared to recent average (Structure tightening)
        is_compressed = current_range <= avg_range * 0.8 
        
        # Range percentage relative to price
        current_price = df.iloc[current_index]['close']
        range_pct = (current_range / current_price) if current_price > 0 else 0.0
        
        return is_compressed, range_pct

    def check_expansion(self, row, df, current_index):
        """
        Detects Elephant or Tail Bar.
        """
        body = abs(row['close'] - row['open'])
        wick_lower = row['close'] - row['low'] if row['close'] > row['open'] else row['open'] - row['low']
        wick_upper = row['high'] - row['close'] if row['close'] > row['open'] else row['high'] - row['open']
        total_range = row['high'] - row['low']
        
        if total_range == 0:
            return False, "None", "None"

        # Calculate Average Body of last 10 candles for context
        if current_index < 10:
            avg_body = body
        else:
            avg_body = df.iloc[current_index-10:current_index].apply(
                lambda x: abs(x['close'] - x['open']), axis=1
            ).mean()

        if avg_body == 0: avg_body = body # Fallback

        exp_type = "None"
        direction = "None"

        # ELEPHANT CANDLE: Large body, strong momentum
        # Rule: Body > 1.5x Average Body
        if body > (avg_body * 1.5):
            exp_type = "Elephant"
            direction = "Bullish" if row['close'] > row['open'] else "Bearish"

        # TAIL BAR: Hammer or Shooting Star
        # Rule: Wick > 2x Body
        elif wick_lower > (body * 2):
            exp_type = "Tail Bar"
            direction = "Bullish" # Hammer
        elif wick_upper > (body * 2):
            exp_type = "Tail Bar"
            direction = "Bearish" # Shooting Star

        is_valid = exp_type in ["Elephant", "Tail Bar"]
        return is_valid, exp_type, direction

    def check_sweep(self, row, df, current_index):
        """
        Optional: Break of recent high/low + rejection.
        """
        if current_index < 5:
            return False, "None"
        
        recent_highs = df.iloc[current_index-5:current_index]['high'].max()
        recent_lows = df.iloc[current_index-5:current_index]['low'].min()
        
        sweep_type = "None"
        active = False
        
        # Bull Sweep: Broke low, closed back up (Rejection)
        if row['low'] < recent_lows and row['close'] > row['open']:
            active = True
            sweep_type = "Bull Sweep"
        
        # Bear Sweep: Broke high, closed back down (Rejection)
        elif row['high'] > recent_highs and row['close'] < row['open']:
            active = True
            sweep_type = "Bear Sweep"
            
        return active, sweep_type

    def scan_timeframe(self, df, tf_name):
        """
        Scans a single timeframe dataframe. 
        Returns the latest signal analysis.
        """
        if len(df) < 200: return None 

        df = df.copy()
        df['sma20'] = self.calculate_sma(df['close'], 20)
        df['sma100'] = self.calculate_sma(df['close'], 100)
        df['sma200'] = self.calculate_sma(df['close'], 200)

        idx = len(df) - 1
        row = df.iloc[idx]
        
        # 1. Check SQZ
        sqz_status = self.check_sqz(row, row['sma20'], row['sma100'], row['sma200'])
        
        # 2. Check Compression
        comp_raw_active, comp_range = self.check_compression(df, idx)
        
        # --- CORRECTION LAYER: COMPRESSION DEPENDENCY ---
        # Compression is ONLY valid if SQZ exists
        comp_active = comp_raw_active if sqz_status != "None" else False
        
        # 3. Check Expansion
        exp_valid, exp_type, exp_dir = self.check_expansion(row, df, idx)
        
        # 4. Check Sweep
        sweep_active, sweep_type = self.check_sweep(row, df, idx)

        # Structure Logic
        prev_high = df.iloc[idx-1]['high']
        prev_low = df.iloc[idx-1]['low']
        broke_high = row['high'] > prev_high
        broke_low = row['low'] < prev_low

        # Determine if full sequence exists on THIS timeframe
        # Rule: SQZ -> Compression -> Expansion
        valid_sequence = (sqz_status != "None") and comp_active and exp_valid

        return {
            "tf_name": tf_name,
            "sqz_type": sqz_status,
            "compression_active": comp_active,
            "compression_range_percent": comp_range, # ACTUAL VALUE
            "expansion_valid": exp_valid,
            "expansion_type": exp_type,
            "direction": exp_dir,
            "sweep_active": sweep_active,
            "sweep_type": sweep_type,
            "broke_high": broke_high,
            "broke_low": broke_low,
            "valid_sequence": valid_sequence
        }

    def generate_signal(self, symbol, data_3m, data_5m, data_15m):
        """
        Master scanner function. Enforces Timeframe Sequence and MEGA SQZ rules.
        """
        res_3m = self.scan_timeframe(data_3m, "3m")
        res_5m = self.scan_timeframe(data_5m, "5m")
        res_15m = self.scan_timeframe(data_15m, "15m")
        
        if not res_3m or not res_5m or not res_15m:
            return self._format_invalid(symbol, "Insufficient data")

        # --- CORRECTION LAYER: MEGA SQZ STRICT VALIDITY ---
        # MEGA SQZ ONLY if 3m == 5m == 15m (and type is not None)
        sqz_3m = res_3m['sqz_type']
        sqz_5m = res_5m['sqz_type']
        sqz_15m = res_15m['sqz_type']

        is_mega_sqz = (
            sqz_3m != "None" and 
            sqz_3m == sqz_5m == sqz_15m
        )

        # --- CORRECTION LAYER: TIMEFRAME SEQUENCE & PRIORITY ---
        # Priority: 3m -> 5m -> 15m
        # We find the first timeframe that has a valid sequence (SQZ + Comp + Expansion)
        active_signal_data = None
        active_tf = None

        if res_3m['valid_sequence']:
            active_signal_data = res_3m
            active_tf = "3m"
        elif res_5m['valid_sequence']:
            active_signal_data = res_5m
            active_tf = "5m"
        elif res_15m['valid_sequence']:
            active_signal_data = res_15m
            active_tf = "15m"

        # If no valid sequence found on any timeframe
        if not active_signal_data:
            return self._format_invalid(symbol, "No valid structure sequence (SQZ->Comp->Expansion)")

        # Determine SQZ Type for JSON output
        # If MEGA SQZ is active, report "MEGA SQZ"
        # If not MEGA, report the specific SQZ type of the active timeframe
        reported_sqz_type = "MEGA SQZ" if is_mega_sqz else active_signal_data['sqz_type']

        # CONSTRUCT VALID SIGNAL JSON
        # Using data from the ACTIVE timeframe
        return {
            "symbol": symbol,
            "timestamp": pd.Timestamp.now().strftime("%H:%M:%S"),
            "timeframe": active_tf, # Priority enforced
            
            "sqz": {
                "active": True,
                "type": reported_sqz_type,
                "timeframe_alignment": {
                    "3m": sqz_3m,
                    "5m": sqz_5m,
                    "15m": sqz_15m
                }
            },

            "compression": {
                "active": active_signal_data['compression_active'],
                "range_percent": active_signal_data['compression_range_percent'], # Actual computed value
                "threshold": 0.005
            },

            "expansion": {
                "valid": True,
                "type": active_signal_data['expansion_type'],
                "direction": active_signal_data['direction']
            },

            "sweep": {
                "active": active_signal_data['sweep_active'],
                "type": active_signal_data['sweep_type']
            },

            "structure": {
                "break_confirmed": active_signal_data['broke_high'] or active_signal_data['broke_low'],
                "previous_high_broken": active_signal_data['broke_high'],
                "previous_low_broken": active_signal_data['broke_low']
            },

            "final_status": "VALID SIGNAL"
        }

    def _format_invalid(self, symbol, reason):
        return {
            "symbol": symbol,
            "timestamp": pd.Timestamp.now().strftime("%H:%M:%S"),
            "status": "INVALID",
            "reason": reason
        }
