import pandas as pd
import numpy as np

class StochasticBacktester:
    def __init__(self, initial_balance=10000000):
        self.initial_balance = initial_balance

    def run_backtest(self, df, mode="A", exit_timing="Close"):
        """
        Runs the backtest logic based on the provided dataframe and parameters.

        Parameters:
        - df: DataFrame containing OHLCV and calculated Stochastics (Stoch_K, Stoch_D, Stoch_SlowD).
              The index should be Datetime or convertible to it.
        - mode: "A" (Touch/Intraday) or "B" (Close/Next Open) for Entry/Stop execution.
        - exit_timing: "Close" (Same day close) or "Open" (Next day open) for Signal Exit (Stoch Cross).

        Returns:
        - summary: Dictionary with performance metrics.
        - trade_log: DataFrame with individual trade details.
        """

        if df is None or df.empty:
            return {}, pd.DataFrame()

        # Ensure required columns exist
        required_cols = ['Open', 'High', 'Low', 'Close', 'Stoch_K', 'Stoch_D', 'Stoch_SlowD']
        for col in required_cols:
            if col not in df.columns:
                # Try to see if they are just case sensitive
                raise ValueError(f"Missing required column: {col}")

        # Initialize State
        balance = self.initial_balance
        position = 0 # 0: None, >0: Long Qty, <0: Short Qty
        entry_price = 0.0
        stop_price = 0.0

        # Pending Orders (for Next Open execution)
        # Used for Mode B Entry and Exit, and Mode A Exit (if Open)
        pending_action = None # {'type': 'Entry'/'Exit', 'direction': 'Long'/'Short', 'reason': str, 'stop_trigger': float}

        # Setup State
        setup_state = None # 'Long' or 'Short'
        setup_entry_trigger = 0.0
        setup_stop_trigger = 0.0
        setup_signal_date = None

        trade_history = []
        current_trade = {}

        # Helper to record trade
        def close_trade(date, exit_price, reason, pnl, qty):
            nonlocal position, current_trade, balance
            current_trade['Exit Date'] = date
            current_trade['Exit Price'] = exit_price
            current_trade['Reason'] = reason
            current_trade['PnL'] = pnl

            # PnL %
            if current_trade.get('Entry Price', 0) > 0:
                cost = current_trade['Entry Price'] * qty
                current_trade['PnL %'] = (pnl / cost) * 100 if cost > 0 else 0
            else:
                 current_trade['PnL %'] = 0.0

            if 'Entry Date' in current_trade:
                current_trade['Holding Days'] = (date - current_trade['Entry Date']).days

            # Result
            if pnl > 0: res = 'Win'
            elif pnl < 0: res = 'Loss'
            else: res = 'Draw'
            current_trade['Result'] = res

            trade_history.append(current_trade)

            balance += pnl
            position = 0
            current_trade = {}

        # Iterate through DataFrame
        n_rows = len(df)

        # Start index: Need at least 3 previous candles for Dip/Peak logic (prev-3)
        # And indicators must be valid (usually ~20 periods).
        # We'll rely on pandas isna check.

        for i in range(20, n_rows):
            date = df.index[i]
            row = df.iloc[i]
            prev = df.iloc[i-1]
            prev2 = df.iloc[i-2]
            prev3 = df.iloc[i-3]

            # Check for NaN in indicators
            if pd.isna(row['Stoch_K']) or pd.isna(prev['Stoch_K']) or pd.isna(prev2['Stoch_K']) or pd.isna(prev3['Stoch_K']):
                continue

            open_p = row['Open']
            high_p = row['High']
            low_p = row['Low']
            close_p = row['Close']

            # --- 1. Handle Pending Executions (Next Open) ---
            if pending_action:
                act_type = pending_action['type']

                if act_type == 'Exit':
                    # Execute Exit at Open
                    exit_p = open_p
                    qty = abs(position)

                    if position > 0: # Long Exit
                        pnl = (exit_p - entry_price) * qty
                    else: # Short Exit
                        pnl = (entry_price - exit_p) * qty

                    close_trade(date, exit_p, pending_action['reason'], pnl, qty)
                    pending_action = None
                    # Position is now 0. Can we enter new setup same day? Yes.

                elif act_type == 'Entry':
                    # Execute Entry at Open
                    # Only if position is 0 (should be)
                    if position == 0:
                        ptype = pending_action['direction']
                        stop_trigger = pending_action['stop_trigger']

                        entry_price = open_p
                        qty = 100 # Fixed quantity

                        if ptype == 'Long':
                            position = qty
                        else:
                            position = -qty

                        current_trade = {
                            'Trade No': len(trade_history) + 1,
                            'Type': ptype,
                            'Signal Date': pending_action['signal_date'],
                            'Entry Date': date,
                            'Entry Price': entry_price,
                            'Qty': qty,
                            'Stop Trigger': stop_trigger,
                            'Risk': abs(entry_price - stop_trigger) * qty
                        }
                        stop_price = stop_trigger

                    pending_action = None

            # --- 2. In-Position Logic ---
            if position != 0:
                is_long = position > 0
                qty = abs(position)
                trade_closed = False

                # A. Stop Loss Check
                sl_hit = False
                sl_exec_price = 0.0
                sl_reason = ""

                if mode == "A": # Touch (Intraday)
                    if is_long and low_p <= stop_price:
                        sl_hit = True
                        sl_exec_price = stop_price
                        sl_reason = "Stop Loss (Touch)"
                    elif not is_long and high_p >= stop_price:
                        sl_hit = True
                        sl_exec_price = stop_price
                        sl_reason = "Stop Loss (Touch)"

                    if sl_hit:
                        if is_long: pnl = (sl_exec_price - entry_price) * qty
                        else: pnl = (entry_price - sl_exec_price) * qty
                        close_trade(date, sl_exec_price, sl_reason, pnl, qty)
                        trade_closed = True

                elif mode == "B": # Close (Next Open)
                    if is_long and close_p < stop_price:
                        pending_action = {'type': 'Exit', 'reason': "Stop Loss (Close)"}
                        # Trade not closed yet, will close next open
                    elif not is_long and close_p > stop_price:
                        pending_action = {'type': 'Exit', 'reason': "Stop Loss (Close)"}

                # B. Signal Exit Check (Stoch Cross)
                # Only check if not already closing via Stop Loss
                if not trade_closed and not pending_action:
                    signal_exit = False
                    # Long Exit: Dead Cross (Stoch D < SlowD)
                    # Short Exit: Golden Cross (Stoch D > SlowD)
                    # Note: Requirement implies "State" (Current D < Current SlowD)
                    # But usually "Cross" means change.
                    # Given Setup requires "Environment: Positive Turn (D > SlowD)",
                    # Exit occurs when this condition fails (D < SlowD).
                    if is_long:
                        if row['Stoch_D'] < row['Stoch_SlowD']:
                            signal_exit = True
                    else: # Short
                        if row['Stoch_D'] > row['Stoch_SlowD']:
                            signal_exit = True

                    if signal_exit:
                        if exit_timing == "Close":
                            # Exit immediately at Close
                            exit_p = close_p
                            if is_long: pnl = (exit_p - entry_price) * qty
                            else: pnl = (entry_price - exit_p) * qty
                            close_trade(date, exit_p, "Signal Exit (Close)", pnl, qty)
                            trade_closed = True

                        elif exit_timing == "Open":
                            pending_action = {'type': 'Exit', 'reason': "Signal Exit (Next Open)"}

            # --- 3. Setup & Entry Logic ---
            # If trade was closed this turn, we can check for NEW setup (for T+1)
            # But we CANNOT enter in T (today) if we just closed.
            # Setup identified at Close of T is valid for T+1.

            # If we are pending an exit for tomorrow, we can't take a new setup today?
            # Actually, if we exit at Open T+1, we might enter at Close T+1?
            # Or Enter at Open T+1 (Stop and Reverse)?
            # The logic below handles Setup for T+1.

            # Setup Identification Logic (Signal Candle)

            stoch_d = row['Stoch_D']
            stoch_sd = row['Stoch_SlowD']
            prev_d = prev['Stoch_D']
            prev_sd = prev['Stoch_SlowD']

            # Slopes (Current > Prev)
            d_slope_pos = stoch_d > prev_d
            sd_slope_pos = stoch_sd > prev_sd
            d_slope_neg = stoch_d < prev_d
            sd_slope_neg = stoch_sd < prev_sd

            env_long = (stoch_d > stoch_sd) and d_slope_pos and sd_slope_pos
            env_short = (stoch_d < stoch_sd) and d_slope_neg and sd_slope_neg

            stoch_k = row['Stoch_K']
            prev_k = prev['Stoch_K']
            prev2_k = prev2['Stoch_K']
            prev3_k = prev3['Stoch_K']

            dip_formed = (stoch_k > prev_k) and (prev_k < prev2_k or prev_k < prev3_k)
            peak_formed = (stoch_k < prev_k) and (prev_k > prev2_k or prev_k > prev3_k)

            new_setup = None
            if env_long and dip_formed:
                new_setup = 'Long'
                trig_entry = high_p
                trig_stop = low_p
            elif env_short and peak_formed:
                new_setup = 'Short'
                trig_entry = low_p
                trig_stop = high_p

            # Logic for Existing Setup (from yesterday)
            # Only process if we are currently flat (position == 0) and no pending action
            if setup_state and position == 0 and not pending_action:

                # Check Environment Validity (Cancel Condition)
                is_valid_env = False
                if setup_state == 'Long':
                    # Require Positive Turn Environment to persist?
                    # "Cancel condition... Environment (Stoch Positive Turn) ended"
                    # If Slope > 0 condition fails, is it ended?
                    # Or just D < SlowD?
                    # "Environment ... ended" usually means the MAIN condition (D > SlowD) flips.
                    # If slope flattens, it's weak but maybe not "ended".
                    # However, the definition of "Positive Turn" included slopes.
                    # Let's enforce Strict Environment: Must maintain Positive Turn definition.
                    if env_long: is_valid_env = True
                elif setup_state == 'Short':
                    if env_short: is_valid_env = True

                if not is_valid_env:
                    setup_state = None # Cancelled

                # Check Price Cancel (Close vs Stop)
                if setup_state == 'Long' and close_p < setup_stop_trigger:
                    setup_state = None
                elif setup_state == 'Short' and close_p > setup_stop_trigger:
                    setup_state = None

                # Check Entry Trigger (if still valid)
                if setup_state:
                    triggered = False

                    if mode == "A": # Touch
                        if setup_state == 'Long':
                            if high_p > setup_entry_trigger:
                                # Enter!
                                entry_exec_price = setup_entry_trigger
                                position = 100
                                current_trade = {
                                    'Trade No': len(trade_history) + 1,
                                    'Type': 'Long',
                                    'Signal Date': setup_signal_date,
                                    'Entry Date': date,
                                    'Entry Price': entry_exec_price,
                                    'Qty': 100,
                                    'Stop Trigger': setup_stop_trigger,
                                    'Risk': abs(entry_exec_price - setup_stop_trigger) * 100
                                }
                                entry_price = entry_exec_price
                                stop_price = setup_stop_trigger
                                setup_state = None

                                # Instant Stop Check
                                if low_p <= stop_price:
                                    pnl = (stop_price - entry_price) * 100
                                    close_trade(date, stop_price, "Stop Loss (Touch/Day)", pnl, 100)
                                    position = 0

                        elif setup_state == 'Short':
                            if low_p < setup_entry_trigger:
                                entry_exec_price = setup_entry_trigger
                                position = -100
                                current_trade = {
                                    'Trade No': len(trade_history) + 1,
                                    'Type': 'Short',
                                    'Signal Date': setup_signal_date,
                                    'Entry Date': date,
                                    'Entry Price': entry_exec_price,
                                    'Qty': 100,
                                    'Stop Trigger': setup_stop_trigger,
                                    'Risk': abs(entry_exec_price - setup_stop_trigger) * 100
                                }
                                entry_price = entry_exec_price
                                stop_price = setup_stop_trigger
                                setup_state = None

                                if high_p >= stop_price:
                                    pnl = (entry_price - stop_price) * 100
                                    close_trade(date, stop_price, "Stop Loss (Touch/Day)", pnl, 100)
                                    position = 0

                    elif mode == "B": # Close
                        if setup_state == 'Long':
                            if close_p > setup_entry_trigger:
                                pending_action = {
                                    'type': 'Entry',
                                    'direction': 'Long',
                                    'stop_trigger': setup_stop_trigger,
                                    'signal_date': setup_signal_date
                                }
                                setup_state = None

                        elif setup_state == 'Short':
                            if close_p < setup_entry_trigger:
                                pending_action = {
                                    'type': 'Entry',
                                    'direction': 'Short',
                                    'stop_trigger': setup_stop_trigger,
                                    'signal_date': setup_signal_date
                                }
                                setup_state = None

            # Update Setup for T+1
            if new_setup:
                # If we are NOT waiting for a pending entry, we can update setup.
                if not pending_action and position == 0:
                    setup_state = new_setup
                    setup_entry_trigger = trig_entry
                    setup_stop_trigger = trig_stop
                    setup_signal_date = date

        # End of Loop

        # Compile Results
        summary = self._calculate_summary(trade_history, balance)
        log_df = pd.DataFrame(trade_history)

        return summary, log_df

    def _calculate_summary(self, history, final_balance):
        if not history:
            return {
                "Total Trades": 0,
                "Win Rate": 0.0,
                "Total PnL": 0.0,
                "Profit Factor": 0.0,
                "Final Balance": final_balance
            }

        df_log = pd.DataFrame(history)
        wins = df_log[df_log['PnL'] > 0]
        losses = df_log[df_log['PnL'] <= 0] # Includes 0?

        n_wins = len(wins)
        n_losses = len(losses)
        n_trades = len(history)
        win_rate = (n_wins / n_trades) * 100 if n_trades > 0 else 0

        total_profit = wins['PnL'].sum()
        total_loss = abs(losses['PnL'].sum())
        total_pnl = total_profit - total_loss

        pf = total_profit / total_loss if total_loss > 0 else float('inf')

        avg_profit = total_profit / n_wins if n_wins > 0 else 0
        avg_loss = total_loss / n_losses if n_losses > 0 else 0
        payoff_ratio = avg_profit / avg_loss if avg_loss > 0 else float('inf')

        # Holding Days
        avg_days = df_log['Holding Days'].mean() if n_trades > 0 else 0
        avg_days_win = wins['Holding Days'].mean() if n_wins > 0 else 0
        avg_days_loss = losses['Holding Days'].mean() if n_losses > 0 else 0

        return {
            "Total Trades": n_trades,
            "Win Rate": win_rate,
            "Total PnL": total_pnl,
            "Profit Factor": pf,
            "Avg Profit": avg_profit,
            "Avg Loss": avg_loss,
            "Payoff Ratio": payoff_ratio,
            "Avg Days": avg_days,
            "Avg Days (Win)": avg_days_win,
            "Avg Days (Loss)": avg_days_loss,
            "Final Balance": final_balance
        }
