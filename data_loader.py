import yfinance as yf
import pandas as pd
import numpy as np

def fetch_data(ticker, period="10y", interval="1d"):
    """
    Fetches historical data for a given ticker.
    """
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty:
            return None

        # Ensure MultiIndex columns are handled
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def calculate_indicators(df):
    """
    Calculates Moving Averages and Stochastics using pandas.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    # Moving Averages (5, 25, 75)
    df['MA5'] = df['Close'].rolling(window=5).mean()
    df['MA25'] = df['Close'].rolling(window=25).mean()
    df['MA75'] = df['Close'].rolling(window=75).mean()

    # Stochastics (K=13, D=5, SlowD=4)
    low_min = df['Low'].rolling(window=13).min()
    high_max = df['High'].rolling(window=13).max()
    
    # Fast %K
    df['Stoch_K'] = 100 * ((df['Close'] - low_min) / (high_max - low_min))
    df['Stoch_K_Angle'] = df['Stoch_K'].diff()
    
    # %D (SMA of %K, window=5)
    df['Stoch_D'] = df['Stoch_K'].rolling(window=5).mean()
    
    # Slow %D (SMA of %D, window=4)
    df['Stoch_SlowD'] = df['Stoch_D'].rolling(window=4).mean()

    # RSI (14-day)
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # Open Gap (%)
    df['Open_Gap_%'] = ((df['Open'] / df['Close'].shift(1)) - 1) * 100

    # SMA Deviations (%)
    df['SMA5_dev'] = (df['Close'] / df['MA5'] - 1) * 100
    df['SMA25_dev'] = (df['Close'] / df['MA25'] - 1) * 100

    # ATR (14-day)
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(14).mean()

    # Volume Ratio (Current vs 20-day MA)
    df['Volume_MA20'] = df['Volume'].rolling(window=20).mean()
    df['Volume_Ratio'] = df['Volume'] / df['Volume_MA20']

    return df

def get_weekly_data(df):
    """
    Resamples daily data to weekly and calculates indicators.
    """
    if df is None or df.empty:
        return None

    logic = {
        'Open': 'first',
        'High': 'max',
        'Low': 'min',
        'Close': 'last',
        'Volume': 'sum'
    }

    # Resample
    w_df = df.resample('W-FRI').apply(logic)
    w_df = w_df.dropna()

    # Weekly MAs (5, 25, 75 weeks)
    w_df['MA5'] = w_df['Close'].rolling(window=5).mean()
    w_df['MA25'] = w_df['Close'].rolling(window=25).mean()
    w_df['MA75'] = w_df['Close'].rolling(window=75).mean()

    return w_df
