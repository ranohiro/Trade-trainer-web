import yfinance as yf
import pandas as pd
import time
from data_loader import fetch_data, calculate_indicators

def get_df():
    for _ in range(5):
        try:
            df = fetch_data('7203.T')
            if df is not None and not df.empty:
                return df
        except:
            pass
        time.sleep(2)
    return None

df = get_df()
df = calculate_indicators(df)
subset = df.loc['2026-02-02':'2026-02-12', ['Open', 'High', 'Low', 'Close', 'Stoch_K', 'Stoch_D', 'Stoch_SlowD']]
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
print(subset)
