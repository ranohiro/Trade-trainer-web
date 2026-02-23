import pandas as pd
import numpy as np

class StochasticBacktester:
    def __init__(self, initial_balance=10000000):
        self.initial_balance = initial_balance

    def prepare_data(self, df):
        """
        Prepares the DataFrame by adding necessary columns for dynamic rules.
        """
        df = df.copy()

        # Shifted columns for slope/prev comparisons
        # We need these because dynamic rules like "Stoch_D > Stoch_D_prev" refer to them.
        for col in ['Stoch_K', 'Stoch_D', 'Stoch_SlowD']:
            if col in df.columns:
                df[f'{col}_prev'] = df[col].shift(1)

        # Complex conditions: Dip and Peak
        if 'Stoch_K' in df.columns:
            prev_k = df['Stoch_K'].shift(1)
            prev2_k = df['Stoch_K'].shift(2)
            prev3_k = df['Stoch_K'].shift(3)

            # dip_formed: Current > Prev AND (Prev < Prev2 OR Prev < Prev3)
            df['dip_formed'] = (df['Stoch_K'] > prev_k) & ((prev_k < prev2_k) | (prev_k < prev3_k))

            # peak_formed: Current < Prev AND (Prev > Prev2 OR Prev > Prev3)
            df['peak_formed'] = (df['Stoch_K'] < prev_k) & ((prev_k > prev2_k) | (prev_k > prev3_k))

        return df

    def evaluate_rules(self, row, rules):
        """
        Evaluates a list of rules against a row.
        Returns True if ALL rules are met (AND condition).
        """
        if not rules:
            # If no rules provided, return True (pass).
            # Caller should handle empty/None if they want specific behavior.
            return True

        for rule in rules:
            # left: column name
            left_key = rule.get('left')
            if left_key not in row:
                return False
            left_val = row[left_key]

            # right
            right_val = None
            if rule.get('right_type') == 'value':
                right_val = rule.get('right')
            elif rule.get('right_type') == 'indicator':
                right_key = rule.get('right')
                if right_key not in row:
                    return False
                right_val = row[right_key]
            else:
                return False

            operator = rule.get('operator')

            try:
                if operator == '>':
                    if not (left_val > right_val): return False
                elif operator == '<':
                    if not (left_val < right_val): return False
                elif operator == '>=':
                    if not (left_val >= right_val): return False
                elif operator == '<=':
                    if not (left_val <= right_val): return False
                elif operator == '==':
                    if not (left_val == right_val): return False
                elif operator == '!=':
                    if not (left_val != right_val): return False
                else:
                    return False
            except:
                return False

        return True

    def get_default_rules(self):
        """
        Returns the hardcoded logic as a dynamic rule set.
        """
        # env_long: (stoch_d > stoch_sd) and d_slope_pos and sd_slope_pos
        env_long_rules = [
            {"left": "Stoch_D", "operator": ">", "right_type": "indicator", "right": "Stoch_SlowD"},
            {"left": "Stoch_D", "operator": ">", "right_type": "indicator", "right": "Stoch_D_prev"},
            {"left": "Stoch_SlowD", "operator": ">", "right_type": "indicator", "right": "Stoch_SlowD_prev"}
        ]

        # env_short: (stoch_d < stoch_sd) and d_slope_neg and sd_slope_neg
        env_short_rules = [
            {"left": "Stoch_D", "operator": "<", "right_type": "indicator", "right": "Stoch_SlowD"},
            {"left": "Stoch_D", "operator": "<", "right_type": "indicator", "right": "Stoch_D_prev"},
            {"left": "Stoch_SlowD", "operator": "<", "right_type": "indicator", "right": "Stoch_SlowD_prev"}
        ]

        return {
            "setup_long_rules": env_long_rules + [
                {"left": "dip_formed", "operator": "==", "right_type": "value", "right": True}
            ],
            "setup_short_rules": env_short_rules + [
                {"left": "peak_formed", "operator": "==", "right_type": "value", "right": True}
            ],
            # Rules to maintain the setup state (Environment Check)
            "maintain_long_rules": env_long_rules,
            "maintain_short_rules": env_short_rules,

            "exit_long_rules": [
                {"left": "Stoch_D", "operator": "<", "right_type": "indicator", "right": "Stoch_SlowD"}
            ],
            "exit_short_rules": [
                {"left": "Stoch_D", "operator": ">", "right_type": "indicator", "right": "Stoch_SlowD"}
            ]
        }

    def run_backtest(self, df, mode="A", exit_timing="Close", rules=None):
        """
        Runs the backtest logic based on the provided dataframe and parameters.

        Parameters:
        - df: DataFrame containing OHLCV and calculated Stochastics (Stoch_K, Stoch_D, Stoch_SlowD).
              The index should be Datetime or convertible to it.
        - mode: "A" (Touch/Intraday) or "B" (Close/Next Open) for Entry/Stop execution.
        - exit_timing: "Close" (Same day close) or "Open" (Next day open) for Signal Exit (Stoch Cross).
        - rules: JSON-like dictionary defining the entry/exit rules. If None, uses default hardcoded logic.

        Returns:
        - summary: Dictionary with performance metrics.
        - trade_log: DataFrame with individual trade details.
        - signal_log: DataFrame with signal details.
        """

        if df is None or df.empty:
            return {}, pd.DataFrame(), pd.DataFrame()

        # Ensure required columns exist
        required_cols = ['Open', 'High', 'Low', 'Close', 'Stoch_K', 'Stoch_D', 'Stoch_SlowD']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        # Use default rules if none provided
        if rules is None:
            rules = self.get_default_rules()

        # Pre-calculate dynamic columns (dip, peak, prev, etc.)
        df = self.prepare_data(df)

        # Initialize State
        balance = self.initial_balance
        position = 0 # 0: None, >0: Long Qty, <0: Short Qty
        entry_price = 0.0
        stop_price = 0.0

        pending_action = None

        setup_state = None
        setup_entry_trigger = 0.0
        setup_stop_trigger = 0.0
        setup_signal_date = None
        setup_signal_props = {}

        trade_history = []
        signal_history = []
        current_trade = {}

        def close_trade(date, exit_price, reason, pnl, qty, prev_row):
            nonlocal position, current_trade, balance
            current_trade['Exit Date'] = date
            current_trade['Exit Price'] = exit_price
            current_trade['Reason'] = reason
            current_trade['PnL'] = pnl
            
            # Save Exit Properties (previous day)
            current_trade['Exit %K'] = prev_row.get('Stoch_K', 0)
            current_trade['Exit %D'] = prev_row.get('Stoch_D', 0)
            current_trade['Exit Slow%D'] = prev_row.get('Stoch_SlowD', 0)
            current_trade['Exit RSI'] = prev_row.get('RSI', 0)
            current_trade['Exit SMA5 %'] = prev_row.get('SMA5_dev', 0)
            current_trade['Exit vs SMA25 %'] = prev_row.get('SMA25_dev', 0)
            current_trade['Exit ATR'] = prev_row.get('ATR', 0)
            current_trade['Exit Volume Ratio'] = prev_row.get('Volume_Ratio', 0)

            # PnL % and MFE/MAE
            if current_trade.get('Entry Price', 0) > 0:
                cost = current_trade['Entry Price'] * qty
                current_trade['PnL %'] = (pnl / cost) * 100 if cost > 0 else 0
                
                is_long = current_trade.get('Type') == 'Long'
                mfe_p = current_trade.get('MFE Price', exit_price)
                mae_p = current_trade.get('MAE Price', exit_price)
                
                if is_long:
                    current_trade['MFE'] = (mfe_p - current_trade['Entry Price']) * qty
                    current_trade['MAE'] = (mae_p - current_trade['Entry Price']) * qty
                else:
                    current_trade['MFE'] = (current_trade['Entry Price'] - mfe_p) * qty
                    current_trade['MAE'] = (current_trade['Entry Price'] - mae_p) * qty
                
                current_trade['MFE %'] = (current_trade['MFE'] / cost) * 100 if cost > 0 else 0
                current_trade['MAE %'] = (current_trade['MAE'] / cost) * 100 if cost > 0 else 0
            else:
                 current_trade['PnL %'] = 0.0
                 current_trade['MFE'] = 0.0
                 current_trade['MAE'] = 0.0
                 current_trade['MFE %'] = 0.0
                 current_trade['MAE %'] = 0.0

            if 'Entry Date' in current_trade:
                current_trade['Holding Days'] = (date - current_trade['Entry Date']).days

            if pnl > 0: res = 'Win'
            elif pnl < 0: res = 'Loss'
            else: res = 'Draw'
            current_trade['Result'] = res

            trade_history.append(current_trade)

            balance += pnl
            position = 0
            current_trade = {}

        n_rows = len(df)

        for i in range(20, n_rows):
            date = df.index[i]
            row = df.iloc[i]
            prev = df.iloc[i-1]
            prev2 = df.iloc[i-2]
            prev3 = df.iloc[i-3]

            if pd.isna(row['Stoch_K']) or pd.isna(prev['Stoch_K']) or pd.isna(prev2['Stoch_K']) or pd.isna(prev3['Stoch_K']):
                continue

            open_p = row['Open']
            high_p = row['High']
            low_p = row['Low']
            close_p = row['Close']

            # --- 1. Handle Pending Executions ---
            if pending_action:
                act_type = pending_action['type']

                if act_type == 'Exit':
                    exit_p = open_p
                    qty = abs(position)

                    if position > 0: pnl = (exit_p - entry_price) * qty
                    else: pnl = (entry_price - exit_p) * qty

                    close_trade(date, exit_p, pending_action['reason'], pnl, qty, prev)
                    pending_action = None

                elif act_type == 'Entry':
                    if position == 0:
                        ptype = pending_action['direction']
                        stop_trigger = pending_action['stop_trigger']

                        entry_price = open_p
                        qty = 100

                        if ptype == 'Long': position = qty
                        else: position = -qty

                        risk_amt = abs(entry_price - stop_trigger) * qty
                        risk_pct = (abs(entry_price - stop_trigger) / entry_price) * 100 if entry_price > 0 else 0

                        current_trade = {
                            'Trade No': len(trade_history) + 1,
                            'Type': ptype,
                            'Signal Date': pending_action['signal_date'],
                            'Trigger Entry Price': pending_action['setup_entry_trigger'],
                            'Entry Date': date,
                            'Entry Gap %': ((open_p / prev['Close']) - 1) * 100,
                            'Entry Price': entry_price,
                            'Qty': qty,
                            'Stop Trigger': stop_trigger,
                            'Risk': risk_amt,
                            'Risk %': risk_pct,
                            'MFE Price': entry_price,
                            'MAE Price': entry_price,
                            'MFE RSI': row.get('RSI', 0),
                            'MFE %K': row.get('Stoch_K', 0),
                            'MFE Volume Ratio': row.get('Volume_Ratio', 0),
                            'MAE RSI': row.get('RSI', 0),
                            'MAE %K': row.get('Stoch_K', 0),
                            'MAE Volume Ratio': row.get('Volume_Ratio', 0)
                        }
                        if 'signal_props' in pending_action:
                            current_trade.update(pending_action['signal_props'])
                        stop_price = stop_trigger

                    pending_action = None

            # --- 2. In-Position Logic ---
            if position != 0:
                is_long = position > 0
                qty = abs(position)
                trade_closed = False

                if current_trade:
                    if is_long:
                        if high_p > current_trade.get('MFE Price', entry_price):
                            current_trade['MFE Price'] = high_p
                            current_trade['MFE RSI'] = row.get('RSI', 0)
                            current_trade['MFE %K'] = row.get('Stoch_K', 0)
                            current_trade['MFE Volume Ratio'] = row.get('Volume_Ratio', 0)
                        
                        if low_p < current_trade.get('MAE Price', entry_price):
                            current_trade['MAE Price'] = low_p
                            current_trade['MAE RSI'] = row.get('RSI', 0)
                            current_trade['MAE %K'] = row.get('Stoch_K', 0)
                            current_trade['MAE Volume Ratio'] = row.get('Volume_Ratio', 0)
                    else:
                        if low_p < current_trade.get('MFE Price', entry_price):
                            current_trade['MFE Price'] = low_p
                            current_trade['MFE RSI'] = row.get('RSI', 0)
                            current_trade['MFE %K'] = row.get('Stoch_K', 0)
                            current_trade['MFE Volume Ratio'] = row.get('Volume_Ratio', 0)
                        
                        if high_p > current_trade.get('MAE Price', entry_price):
                            current_trade['MAE Price'] = high_p
                            current_trade['MAE RSI'] = row.get('RSI', 0)
                            current_trade['MAE %K'] = row.get('Stoch_K', 0)
                            current_trade['MAE Volume Ratio'] = row.get('Volume_Ratio', 0)

                # Gap Exit Logic (1% adverse gap from previous close to current open)
                if 'Entry Date' in current_trade and date > current_trade['Entry Date']:
                    prev_close = prev['Close']
                    if is_long and open_p <= prev_close * 0.99:
                        pnl = (open_p - entry_price) * qty
                        close_trade(date, open_p, "Gap Exit (Adverse)", pnl, qty, prev)
                        trade_closed = True
                    elif not is_long and open_p >= prev_close * 1.01:
                        pnl = (entry_price - open_p) * qty
                        close_trade(date, open_p, "Gap Exit (Adverse)", pnl, qty, prev)
                        trade_closed = True

                if not trade_closed:
                    sl_hit = False
                    sl_exec_price = 0.0
                    sl_reason = ""

                    if mode == "A":
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
                            close_trade(date, sl_exec_price, sl_reason, pnl, qty, prev)
                            trade_closed = True

                    elif mode == "B":
                        if is_long and close_p < stop_price:
                            pending_action = {'type': 'Exit', 'reason': "Stop Loss (Close)"}
                        elif not is_long and close_p > stop_price:
                            pending_action = {'type': 'Exit', 'reason': "Stop Loss (Close)"}

                if not trade_closed and not pending_action:
                    signal_exit = False
                    if is_long:
                        exit_rules = rules.get('exit_long_rules', [])
                        if exit_rules and self.evaluate_rules(row, exit_rules):
                            signal_exit = True
                    else:
                        exit_rules = rules.get('exit_short_rules', [])
                        if exit_rules and self.evaluate_rules(row, exit_rules):
                            signal_exit = True

                    if signal_exit:
                        if exit_timing == "Close":
                            exit_p = close_p
                            if is_long: pnl = (exit_p - entry_price) * qty
                            else: pnl = (entry_price - exit_p) * qty
                            close_trade(date, exit_p, "Signal Exit (Close)", pnl, qty, prev)
                            trade_closed = True
                        elif exit_timing == "Open":
                            pending_action = {'type': 'Exit', 'reason': "Signal Exit (Next Open)"}

            # --- 3. Setup & Entry Logic ---
            new_setup = None

            # Evaluate Long Setup
            long_rules = rules.get('setup_long_rules', [])
            if long_rules and self.evaluate_rules(row, long_rules):
                new_setup = 'Long'
                trig_entry = df['High'].iloc[i-4:i+1].max()
                trig_stop = low_p
            # Evaluate Short Setup
            else:
                short_rules = rules.get('setup_short_rules', [])
                if short_rules and self.evaluate_rules(row, short_rules):
                    new_setup = 'Short'
                    trig_entry = df['Low'].iloc[i-4:i+1].min()
                    trig_stop = high_p

            if new_setup:
                signal_props = {
                    'Signal %K Angle': row.get('Stoch_K_Angle', 0),
                    'Signal %K': row['Stoch_K'],
                    'Signal %D': row['Stoch_D'],
                    'Signal Slow%D': row['Stoch_SlowD'],
                    'Signal RSI': row.get('RSI', 0),
                    'Signal SMA5 %': row.get('SMA5_dev', 0),
                    'Signal SMA25 %': row.get('SMA25_dev', 0),
                    'Signal ATR': row.get('ATR', 0),
                    'Signal Volume Ratio': row.get('Volume_Ratio', 0)
                }

            if setup_state and position == 0 and not pending_action:
                triggered = False

                if mode == "A":
                    if setup_state == 'Long':
                        if high_p > setup_entry_trigger:
                            entry_exec_price = max(setup_entry_trigger, open_p)
                            position = 100
                            risk_amt = abs(entry_exec_price - setup_stop_trigger) * 100
                            risk_pct = (abs(entry_exec_price - setup_stop_trigger) / entry_exec_price) * 100

                            current_trade = {
                                'Trade No': len(trade_history) + 1,
                                'Type': 'Long',
                                'Signal Date': setup_signal_date,
                                'Trigger Entry Price': setup_entry_trigger,
                                'Entry Date': date,
                                'Entry Gap %': ((open_p / prev['Close']) - 1) * 100,
                                'Entry Price': entry_exec_price,
                                'Qty': 100,
                                'Stop Trigger': setup_stop_trigger,
                                'Risk': risk_amt,
                                'Risk %': risk_pct,
                                'MFE Price': entry_exec_price,
                                'MAE Price': entry_exec_price,
                                'MFE RSI': row.get('RSI', 0),
                                'MFE %K': row.get('Stoch_K', 0),
                                'MFE Volume Ratio': row.get('Volume_Ratio', 0),
                                'MAE RSI': row.get('RSI', 0),
                                'MAE %K': row.get('Stoch_K', 0),
                                'MAE Volume Ratio': row.get('Volume_Ratio', 0)
                            }
                            current_trade.update(setup_signal_props)
                            
                            entry_price = entry_exec_price
                            stop_price = setup_stop_trigger
                            setup_state = None
                            triggered = True

                            if low_p <= stop_price:
                                pnl = (stop_price - entry_price) * 100
                                close_trade(date, stop_price, "Stop Loss (Touch/Day)", pnl, 100, prev)
                                position = 0

                    elif setup_state == 'Short':
                        if low_p < setup_entry_trigger:
                            entry_exec_price = min(setup_entry_trigger, open_p)
                            position = -100
                            risk_amt = abs(entry_exec_price - setup_stop_trigger) * 100
                            risk_pct = (abs(entry_exec_price - setup_stop_trigger) / entry_exec_price) * 100

                            current_trade = {
                                'Trade No': len(trade_history) + 1,
                                'Type': 'Short',
                                'Signal Date': setup_signal_date,
                                'Trigger Entry Price': setup_entry_trigger,
                                'Entry Date': date,
                                'Entry Gap %': ((open_p / prev['Close']) - 1) * 100,
                                'Entry Price': entry_exec_price,
                                'Qty': 100,
                                'Stop Trigger': setup_stop_trigger,
                                'Risk': risk_amt,
                                'Risk %': risk_pct,
                                'MFE Price': entry_exec_price,
                                'MAE Price': entry_exec_price,
                                'MFE RSI': row.get('RSI', 0),
                                'MFE %K': row.get('Stoch_K', 0),
                                'MFE Volume Ratio': row.get('Volume_Ratio', 0),
                                'MAE RSI': row.get('RSI', 0),
                                'MAE %K': row.get('Stoch_K', 0),
                                'MAE Volume Ratio': row.get('Volume_Ratio', 0)
                            }
                            current_trade.update(setup_signal_props)
                            
                            entry_price = entry_exec_price
                            stop_price = setup_stop_trigger
                            setup_state = None
                            triggered = True

                            if high_p >= stop_price:
                                pnl = (entry_price - stop_price) * 100
                                close_trade(date, stop_price, "Stop Loss (Touch/Day)", pnl, 100, prev)
                                position = 0

                elif mode == "B":
                    if setup_state == 'Long':
                        if close_p > setup_entry_trigger:
                            pending_action = {
                                'type': 'Entry',
                                'direction': 'Long',
                                'setup_entry_trigger': setup_entry_trigger,
                                'stop_trigger': setup_stop_trigger,
                                'signal_date': setup_signal_date,
                                'signal_props': setup_signal_props
                            }
                            setup_state = None
                            triggered = True

                    elif setup_state == 'Short':
                        if close_p < setup_entry_trigger:
                            pending_action = {
                                'type': 'Entry',
                                'direction': 'Short',
                                'setup_entry_trigger': setup_entry_trigger,
                                'stop_trigger': setup_stop_trigger,
                                'signal_date': setup_signal_date,
                                'signal_props': setup_signal_props
                            }
                            setup_state = None
                            triggered = True

                if not triggered and setup_state:
                    is_valid_env = False
                    if setup_state == 'Long':
                        maintain_rules = rules.get('maintain_long_rules', [])
                        if not maintain_rules or self.evaluate_rules(row, maintain_rules):
                             is_valid_env = True
                    elif setup_state == 'Short':
                        maintain_rules = rules.get('maintain_short_rules', [])
                        if not maintain_rules or self.evaluate_rules(row, maintain_rules):
                            is_valid_env = True

                    if not is_valid_env:
                        setup_state = None

                    if setup_state == 'Long' and close_p < setup_stop_trigger:
                        setup_state = None
                    elif setup_state == 'Short' and close_p > setup_stop_trigger:
                        setup_state = None

            if new_setup:
                # Record Signal
                signal_history.append({
                    'Date': date,
                    'Type': new_setup,
                    'Trigger': trig_entry,
                    'Stop': trig_stop
                })

                if not pending_action and position == 0:
                    setup_state = new_setup
                    setup_entry_trigger = trig_entry
                    setup_stop_trigger = trig_stop
                    setup_signal_date = date
                    setup_signal_props = signal_props

        # End of Loop

        summary = self._calculate_summary(trade_history, signal_history, balance)
        log_df = pd.DataFrame(trade_history)
        signal_df = pd.DataFrame(signal_history)

        return summary, log_df, signal_df

    def _calculate_summary(self, history, signals, final_balance):
        import pandas as pd
        import numpy as np

        def calc_metrics(df_log, sig_count):
            if df_log.empty:
                return {
                    'Signal Count': sig_count, 'Entry Count': 0, 'Entry Rate %': 0.0,
                    'Win Rate %': 0.0, 'Avg Profit': 0.0, 'Avg Profit %': 0.0,
                    'Avg Loss': 0.0, 'Avg Loss %': 0.0, 'Max Profit': 0.0, 'Max Loss': 0.0,
                    'Profit Factor': 0.0, 'Payoff Ratio': 0.0, 'Expected Value': 0.0,
                    'Avg Days (Win)': 0.0, 'Avg Days (Loss)': 0.0,
                    'Max Cons Wins': 0, 'Max Cons Losses': 0,
                    'Avg MFE': 0.0, 'Avg MAE': 0.0, 'Total PnL': 0.0
                }
                
            wins = df_log[df_log['PnL'] > 0]
            losses = df_log[df_log['PnL'] <= 0]
            
            n_trades = len(df_log)
            n_wins = len(wins)
            n_losses = len(losses)
            
            entry_rate = (n_trades / sig_count * 100) if sig_count > 0 else 0
            win_rate = (n_wins / n_trades * 100) if n_trades > 0 else 0
            
            avg_profit = wins['PnL'].mean() if n_wins > 0 else 0
            avg_profit_pct = wins['PnL %'].mean() if n_wins > 0 else 0
            avg_loss = losses['PnL'].mean() if n_losses > 0 else 0
            avg_loss_pct = losses['PnL %'].mean() if n_losses > 0 else 0
            
            max_profit = float(df_log['PnL'].max())
            max_profit = max_profit if max_profit > 0 else 0
            max_loss = float(df_log['PnL'].min())
            max_loss = max_loss if max_loss < 0 else 0
            
            total_profit = wins['PnL'].sum()
            total_loss = abs(losses['PnL'].sum())
            total_pnl = df_log['PnL'].sum()
            
            pf = total_profit / total_loss if total_loss > 0 else float('inf')
            payoff_ratio = avg_profit / abs(avg_loss) if avg_loss != 0 else float('inf')
            expected_val = total_pnl / n_trades if n_trades > 0 else 0
            
            avg_days_win = wins['Holding Days'].mean() if n_wins > 0 else 0
            avg_days_loss = losses['Holding Days'].mean() if n_losses > 0 else 0
            
            cons_wins = 0
            max_cons_wins = 0
            cons_losses = 0
            max_cons_losses = 0
            
            for res in df_log['Result']:
                if res == 'Win':
                    cons_wins += 1
                    cons_losses = 0
                    if cons_wins > max_cons_wins: max_cons_wins = cons_wins
                elif res == 'Loss':
                    cons_losses += 1
                    cons_wins = 0
                    if cons_losses > max_cons_losses: max_cons_losses = cons_losses
                else:
                    cons_wins = 0
                    cons_losses = 0
                    
            avg_mfe = df_log['MFE'].mean() if 'MFE' in df_log.columns and n_trades > 0 else 0
            avg_mae = df_log['MAE'].mean() if 'MAE' in df_log.columns and n_trades > 0 else 0

            max_dd = 0.0
            if n_trades > 0:
                pnl_series = df_log['PnL'].cumsum()
                equity_curve = self.initial_balance + pnl_series
                peak = equity_curve.expanding(min_periods=1).max()
                drawdown = (equity_curve - peak) / peak
                max_dd = drawdown.min() * 100

            avg_risk_win = wins['Risk'].mean() if n_wins > 0 and 'Risk' in wins.columns else 0.0
            avg_risk_loss = losses['Risk'].mean() if n_losses > 0 and 'Risk' in losses.columns else 0.0

            return {
                'Signal Count': sig_count, 'Entry Count': n_trades, 'Entry Rate %': entry_rate,
                'Win Rate %': win_rate, 'Win Count': n_wins, 'Loss Count': n_losses,
                'Avg Profit': avg_profit, 'Avg Profit %': avg_profit_pct,
                'Avg Loss': avg_loss, 'Avg Loss %': avg_loss_pct, 'Max Profit': max_profit, 'Max Loss': max_loss,
                'Profit Factor': pf, 'Payoff Ratio': payoff_ratio, 'Expected Value': expected_val,
                'Avg Days (Win)': avg_days_win, 'Avg Days (Loss)': avg_days_loss,
                'Max Cons Wins': max_cons_wins, 'Max Cons Losses': max_cons_losses,
                'Avg MFE': avg_mfe, 'Avg MAE': avg_mae, 'Total PnL': total_pnl, 'Max Drawdown %': max_dd,
                'Avg Risk (Win)': avg_risk_win, 'Avg Risk (Loss)': avg_risk_loss
            }

        df_log = pd.DataFrame(history)
        df_sig = pd.DataFrame(signals)
        
        sig_count_total = len(df_sig)
        sig_count_long = len(df_sig[df_sig['Type'] == 'Long']) if not df_sig.empty else 0
        sig_count_short = len(df_sig[df_sig['Type'] == 'Short']) if not df_sig.empty else 0
        
        if not df_log.empty:
            df_long = df_log[df_log['Type'] == 'Long']
            df_short = df_log[df_log['Type'] == 'Short']
        else:
            df_long = pd.DataFrame()
            df_short = pd.DataFrame()

        total_metrics = calc_metrics(df_log, sig_count_total)
        long_metrics = calc_metrics(df_long, sig_count_long)
        short_metrics = calc_metrics(df_short, sig_count_short)
        
        return {
            'Total': total_metrics,
            'Long': long_metrics,
            'Short': short_metrics,
            'Final Balance': final_balance
        }
