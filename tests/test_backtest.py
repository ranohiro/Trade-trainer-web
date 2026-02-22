import unittest
import pandas as pd
import numpy as np
from backtest import StochasticBacktester

class TestStochasticBacktester(unittest.TestCase):
    def setUp(self):
        self.backtester = StochasticBacktester(initial_balance=1000000)

        # Create a base dataframe
        dates = pd.date_range(start='2023-01-01', periods=50, freq='D')
        self.df = pd.DataFrame(index=dates, columns=['Open', 'High', 'Low', 'Close', 'Stoch_K', 'Stoch_D', 'Stoch_SlowD'])
        self.df['Open'] = 100.0
        self.df['High'] = 105.0
        self.df['Low'] = 95.0
        self.df['Close'] = 100.0
        # Initialize with values that won't trigger random setups
        self.df['Stoch_K'] = 50.0
        self.df['Stoch_D'] = 50.0
        self.df['Stoch_SlowD'] = 50.0

    def test_long_setup_mode_a_entry_stop(self):
        # Scenario: Long Setup, Trigger Entry next day, Hit Stop immediately
        df = self.df.copy()

        # Day 20: Setup Candle
        df.iloc[18, df.columns.get_loc('Stoch_K')] = 20.0
        df.iloc[18, df.columns.get_loc('Stoch_D')] = 40.0
        df.iloc[18, df.columns.get_loc('Stoch_SlowD')] = 30.0

        df.iloc[19, df.columns.get_loc('Stoch_K')] = 10.0 # Dip
        df.iloc[19, df.columns.get_loc('Stoch_D')] = 42.0
        df.iloc[19, df.columns.get_loc('Stoch_SlowD')] = 32.0

        # Day 20 (Signal) - Env OK, Dip OK
        df.iloc[20, df.columns.get_loc('Stoch_K')] = 15.0 # Turn Up
        df.iloc[20, df.columns.get_loc('Stoch_D')] = 44.0
        df.iloc[20, df.columns.get_loc('Stoch_SlowD')] = 34.0

        # Signal Candle Prices
        df.iloc[20, df.columns.get_loc('High')] = 110.0 # Entry Trigger
        df.iloc[20, df.columns.get_loc('Low')] = 90.0 # Stop Trigger
        df.iloc[20, df.columns.get_loc('Close')] = 100.0

        # Day 21 (Execution)
        # MUST maintain Environment (Positive Turn) to allow Entry
        # D > SlowD AND Slopes > 0
        df.iloc[21, df.columns.get_loc('Stoch_D')] = 46.0 # > 44
        df.iloc[21, df.columns.get_loc('Stoch_SlowD')] = 36.0 # > 34
        # 46 > 36 OK.

        # Open 100, High 115 (Trigger Entry), Low 85 (Trigger Stop), Close 90
        df.iloc[21, df.columns.get_loc('Open')] = 100.0
        df.iloc[21, df.columns.get_loc('High')] = 115.0
        df.iloc[21, df.columns.get_loc('Low')] = 85.0
        df.iloc[21, df.columns.get_loc('Close')] = 90.0

        # Mode A: Touch Entry at 110. Touch Stop at 90.
        summary, log = self.backtester.run_backtest(df, mode="A", exit_timing="Close")

        self.assertEqual(len(log), 1)
        trade = log.iloc[0]
        self.assertEqual(trade['Type'], 'Long')
        self.assertEqual(trade['Entry Price'], 110.0)
        self.assertEqual(trade['Exit Price'], 90.0)
        self.assertEqual(trade['Reason'], 'Stop Loss (Touch/Day)')
        self.assertEqual(trade['PnL'], (90 - 110) * 100) # -2000

    def test_long_setup_mode_b_entry_signal_exit(self):
        # Scenario: Long Setup, Mode B Entry (Next Open), Signal Exit (Close)
        df = self.df.copy()

        # Setup (Same logic)
        df.iloc[18, df.columns.get_loc('Stoch_K')] = 20.0
        df.iloc[18, df.columns.get_loc('Stoch_D')] = 40.0
        df.iloc[18, df.columns.get_loc('Stoch_SlowD')] = 30.0

        df.iloc[19, df.columns.get_loc('Stoch_K')] = 10.0
        df.iloc[19, df.columns.get_loc('Stoch_D')] = 42.0
        df.iloc[19, df.columns.get_loc('Stoch_SlowD')] = 32.0

        df.iloc[20, df.columns.get_loc('Stoch_K')] = 15.0
        df.iloc[20, df.columns.get_loc('Stoch_D')] = 44.0
        df.iloc[20, df.columns.get_loc('Stoch_SlowD')] = 34.0

        df.iloc[20, df.columns.get_loc('High')] = 110.0
        df.iloc[20, df.columns.get_loc('Low')] = 90.0

        # Day 21 (Break Close)
        # Close > 110
        df.iloc[21, df.columns.get_loc('Close')] = 112.0

        # Maintain Env
        df.iloc[21, df.columns.get_loc('Stoch_D')] = 46.0
        df.iloc[21, df.columns.get_loc('Stoch_SlowD')] = 36.0

        # Day 22 (Entry at Open)
        df.iloc[22, df.columns.get_loc('Open')] = 113.0
        # Need to maintain env or not?
        # Once "Pending Entry" is set (at Close of Day 21), logic says:
        # "1. Handle Pending Executions (Next Open)" -> Executes at Open of Day 22.
        # So Environment check on Day 22 happens AFTER Entry.
        # But Entry execution depends on Setup validity?
        # Setup validity was checked on Day 21 (when triggering).
        # Once triggered and pending, we execute.

        # Day 23 (Signal Exit - Dead Cross)
        # Stoch D < SlowD
        df.iloc[23, df.columns.get_loc('Stoch_D')] = 60.0
        df.iloc[23, df.columns.get_loc('Stoch_SlowD')] = 61.0
        df.iloc[23, df.columns.get_loc('Close')] = 120.0

        summary, log = self.backtester.run_backtest(df, mode="B", exit_timing="Close")

        self.assertEqual(len(log), 1)
        trade = log.iloc[0]
        self.assertEqual(trade['Type'], 'Long')
        self.assertEqual(trade['Entry Price'], 113.0) # Open of Day 22
        self.assertEqual(trade['Exit Price'], 120.0) # Close of Day 23
        self.assertEqual(trade['Reason'], 'Signal Exit (Close)')
        self.assertEqual(trade['PnL'], (120 - 113) * 100)

    def test_short_setup_cancel(self):
        # Scenario: Short Setup, but cancelled by Environment End
        df = self.df.copy()

        # Day 20 Setup
        df.iloc[18, df.columns.get_loc('Stoch_K')] = 80.0
        df.iloc[18, df.columns.get_loc('Stoch_D')] = 60.0
        df.iloc[18, df.columns.get_loc('Stoch_SlowD')] = 70.0

        df.iloc[19, df.columns.get_loc('Stoch_K')] = 90.0 # Peak
        df.iloc[19, df.columns.get_loc('Stoch_D')] = 58.0
        df.iloc[19, df.columns.get_loc('Stoch_SlowD')] = 68.0

        df.iloc[20, df.columns.get_loc('Stoch_K')] = 85.0 # Turn Down
        df.iloc[20, df.columns.get_loc('Stoch_D')] = 56.0
        df.iloc[20, df.columns.get_loc('Stoch_SlowD')] = 66.0
        # D < SlowD (56 < 66) -> OK

        df.iloc[20, df.columns.get_loc('Low')] = 90.0 # Entry Trigger
        df.iloc[20, df.columns.get_loc('High')] = 110.0 # Stop Trigger

        # Day 21 (Cancel)
        # Environment Ends: Slopes become positive or D > SlowD
        df.iloc[21, df.columns.get_loc('Stoch_D')] = 57.0 # > 56 (Slope +)
        df.iloc[21, df.columns.get_loc('Stoch_SlowD')] = 67.0 # > 66 (Slope +)
        # D < SlowD still holds (57 < 67), but Slopes are positive.
        # Short Environment requires Slopes < 0.
        # So Environment invalid.

        # Even if Price hits trigger
        df.iloc[21, df.columns.get_loc('Low')] = 80.0

        summary, log = self.backtester.run_backtest(df, mode="A", exit_timing="Close")

        # Should be 0 trades because Setup Cancelled
        self.assertEqual(len(log), 0)

if __name__ == '__main__':
    unittest.main()
