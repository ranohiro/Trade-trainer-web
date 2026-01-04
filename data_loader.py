import yfinance as yf
import pandas as pd

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

    # Stochastics (K=14, D=3, SlowD=3) - Fast Stochastic
    low_min = df['Low'].rolling(window=14).min()
    high_max = df['High'].rolling(window=14).max()
    
    # Fast %K
    df['Stoch_K'] = 100 * ((df['Close'] - low_min) / (high_max - low_min))
    
    # Fast %D (which is often what people call %K in Slow Stochastic, but let's stick to standard)
    # The user asked for %K, %D, Slow%D. Usually:
    # Fast %K = (Close - Low14) / (High14 - Low14)
    # Fast %D = SMA(Fast %K, 3)  <-- This is often called "K" in Slow Stoch
    # Slow %D = SMA(Fast %D, 3)  <-- This is often called "D" in Slow Stoch
    
    # Let's align with common Japanese chart settings (Slow Stochastic is common):
    # %K (Fast %D)
    df['Stoch_K'] = df['Stoch_K'].rolling(window=3).mean() 
    # %D (Slow %D)
    df['Stoch_D'] = df['Stoch_K'].rolling(window=3).mean()
    # Slow %D
    df['Stoch_SlowD'] = df['Stoch_D'].rolling(window=3).mean()

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
