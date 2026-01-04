import yfinance as yf
import pandas as pd
import pandas_ta as ta

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
    Calculates Moving Averages and Stochastics.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    # Moving Averages (5, 25, 75)
    df['MA5'] = ta.sma(df['Close'], length=5)
    df['MA25'] = ta.sma(df['Close'], length=25)
    df['MA75'] = ta.sma(df['Close'], length=75)

    # Stochastics (K=14, D=3, Smooth=3)
    stoch = ta.stoch(df['High'], df['Low'], df['Close'], k=14, d=3, smooth_k=3)

    if stoch is not None:
        df = pd.concat([df, stoch], axis=1)

        # Identify columns
        # pandas_ta returns like STOCHk_14_3_3, STOCHd_14_3_3
        k_col = [c for c in stoch.columns if c.startswith('STOCHk')][0]
        d_col = [c for c in stoch.columns if c.startswith('STOCHd')][0]

        df['Stoch_K'] = df[k_col]
        df['Stoch_D'] = df[d_col]

        # Calculate Slow%D (SMA of %D)
        df['Stoch_SlowD'] = ta.sma(df['Stoch_D'], length=3)

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
    w_df['MA5'] = ta.sma(w_df['Close'], length=5)
    w_df['MA25'] = ta.sma(w_df['Close'], length=25)
    w_df['MA75'] = ta.sma(w_df['Close'], length=75)

    return w_df
