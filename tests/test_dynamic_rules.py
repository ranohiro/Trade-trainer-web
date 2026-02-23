import unittest
import pandas as pd
import numpy as np
from backtest import StochasticBacktester

class TestDynamicRules(unittest.TestCase):
    def setUp(self):
        self.backtester = StochasticBacktester(initial_balance=1000000)

        # Create a simple DataFrame
        dates = pd.date_range(start='2023-01-01', periods=10, freq='D')
        self.df = pd.DataFrame(index=dates)
        self.df['A'] = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        self.df['B'] = [10, 15, 35, 35, 55, 65, 65, 85, 85, 105]
        self.df['C'] = [5, 5, 5, 5, 5, 5, 5, 5, 5, 5]

    def test_evaluate_rules_operators(self):
        row = self.df.iloc[2] # A=30, B=35, C=5

        # Test >
        rules = [{"left": "B", "operator": ">", "right_type": "indicator", "right": "A"}]
        self.assertTrue(self.backtester.evaluate_rules(row, rules))

        # Test <
        rules = [{"left": "A", "operator": "<", "right_type": "indicator", "right": "B"}]
        self.assertTrue(self.backtester.evaluate_rules(row, rules))

        # Test ==
        rules = [{"left": "C", "operator": "==", "right_type": "value", "right": 5}]
        self.assertTrue(self.backtester.evaluate_rules(row, rules))

        # Test !=
        rules = [{"left": "A", "operator": "!=", "right_type": "indicator", "right": "B"}]
        self.assertTrue(self.backtester.evaluate_rules(row, rules))

        # Test multiple rules (AND)
        rules = [
            {"left": "B", "operator": ">", "right_type": "indicator", "right": "A"},
            {"left": "C", "operator": "==", "right_type": "value", "right": 5}
        ]
        self.assertTrue(self.backtester.evaluate_rules(row, rules))

        # Test failure
        rules = [{"left": "A", "operator": ">", "right_type": "indicator", "right": "B"}] # 30 > 35 False
        self.assertFalse(self.backtester.evaluate_rules(row, rules))

    def test_evaluate_rules_missing_col(self):
        row = self.df.iloc[0]
        rules = [{"left": "Z", "operator": ">", "right_type": "value", "right": 0}]
        self.assertFalse(self.backtester.evaluate_rules(row, rules))

    def test_custom_backtest_rules(self):
        # Create a dataframe suitable for backtest loop (needs OHLCV + Stochs)
        dates = pd.date_range(start='2023-01-01', periods=50, freq='D')
        df = pd.DataFrame(index=dates)
        df['Open'] = 100.0
        df['High'] = 110.0
        df['Low'] = 90.0
        df['Close'] = 100.0
        df['Stoch_K'] = 50.0
        df['Stoch_D'] = 50.0
        df['Stoch_SlowD'] = 50.0

        # Setup specific conditions
        # Day 25: RSI (simulated column) > 70 -> Long Setup
        # We will trick the backtester by using 'Stoch_K' as our custom indicator

        df.iloc[25, df.columns.get_loc('Stoch_K')] = 80.0
        df.iloc[25, df.columns.get_loc('Low')] = 80.0 # Set Stop Trigger lower so it's not hit on entry day
        # Trigger requires High > entry trigger.
        # Default logic sets entry trigger = Max High(5 days).
        # Let's just use simple conditions.

        # Custom Rules:
        # Long Setup if Stoch_K > 70
        # Exit Long if Stoch_K < 30

        custom_rules = {
            "setup_long_rules": [
                {"left": "Stoch_K", "operator": ">", "right_type": "value", "right": 70.0}
            ],
            "setup_short_rules": [
                 # Impossible condition to ensure only Longs
                {"left": "Stoch_K", "operator": ">", "right_type": "value", "right": 999.0}
            ],
            "maintain_long_rules": [], # Always valid
            "exit_long_rules": [
                {"left": "Stoch_K", "operator": "<", "right_type": "value", "right": 30.0}
            ],
            "exit_short_rules": []
        }

        # Day 26 execution:
        # If Setup on Day 25, Entry Trigger = Max High(21..25) = 110.
        # Day 26 needs High > 110 to enter (Mode A).
        df.iloc[26, df.columns.get_loc('High')] = 115.0
        df.iloc[26, df.columns.get_loc('Stoch_K')] = 50.0 # Neutral

        # Day 28 Exit Signal
        df.iloc[28, df.columns.get_loc('Stoch_K')] = 20.0 # < 30

        # Day 28 Exit Execution (Close)

        summary, log, signals = self.backtester.run_backtest(df, mode="A", exit_timing="Close", rules=custom_rules)

        self.assertEqual(len(log), 1)
        self.assertEqual(log.iloc[0]['Type'], 'Long')
        self.assertEqual(log.iloc[0]['Entry Date'], dates[26])
        self.assertEqual(log.iloc[0]['Exit Date'], dates[28])
        self.assertEqual(log.iloc[0]['Reason'], 'Signal Exit (Close)')

    def test_dynamic_price_logic(self):
        # Test the newly added dynamic pricing logic (entry_logic_long, etc.)
        dates = pd.date_range(start='2023-01-01', periods=50, freq='D')
        df = pd.DataFrame(index=dates)
        df['Open'] = 100.0
        df['High'] = 100.0
        df['Low'] = 100.0
        df['Close'] = 100.0
        df['Stoch_K'] = 50.0
        df['Stoch_D'] = 50.0
        df['Stoch_SlowD'] = 50.0

        # Prepare Data for Scenario
        # Day 25: Signal Day (Stoch_K > 70)
        df.iloc[25, df.columns.get_loc('Stoch_K')] = 80.0

        # Custom Price History for Logic Check
        # Day 23: High 120
        # Day 24: High 130
        # Day 25: High 110
        df.iloc[23, df.columns.get_loc('High')] = 120.0
        df.iloc[24, df.columns.get_loc('High')] = 130.0
        df.iloc[25, df.columns.get_loc('High')] = 110.0

        # Case 1: recent_high with lookback 2 (Should look at Day 24, 25) -> Max is 130
        custom_rules_lb2 = {
            "setup_long_rules": [{"left": "Stoch_K", "operator": ">", "right_type": "value", "right": 70.0}],
            "setup_short_rules": [{"left": "Stoch_K", "operator": ">", "right_type": "value", "right": 999.0}],
            "entry_logic_long": {"entry_type": "recent_high", "lookback": 2},
            "stop_logic_long": {"stop_type": "current_low", "lookback": 1},
        }

        _, log, _ = self.backtester.run_backtest(df, mode="B", rules=custom_rules_lb2)
        # Mode B creates a pending entry based on setup.
        # We need to check if the pending entry has the correct price.
        # Actually run_backtest returns log of EXECUTED trades.
        # Let's check signal history or ensure it executes.

        # To execute, we need Day 26 Close > Trigger (for Mode B Long)
        # Trigger should be 130.
        df.iloc[26, df.columns.get_loc('Close')] = 131.0

        summary, log, signals = self.backtester.run_backtest(df, mode="B", rules=custom_rules_lb2)

        # Check Signal Trigger Price
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals.iloc[0]['Trigger'], 130.0)

        # Case 2: recent_high with lookback 1 (Day 25 only) -> Max is 110
        custom_rules_lb1 = {
             "setup_long_rules": [{"left": "Stoch_K", "operator": ">", "right_type": "value", "right": 70.0}],
             "setup_short_rules": [{"left": "Stoch_K", "operator": ">", "right_type": "value", "right": 999.0}],
             "entry_logic_long": {"entry_type": "recent_high", "lookback": 1},
             "stop_logic_long": {"stop_type": "current_low", "lookback": 1},
        }
        summary, log, signals = self.backtester.run_backtest(df, mode="B", rules=custom_rules_lb1)
        self.assertEqual(signals.iloc[0]['Trigger'], 110.0)

if __name__ == '__main__':
    unittest.main()
