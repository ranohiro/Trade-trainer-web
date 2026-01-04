# Trade Training Studio

A practice-focused investment simulator built with Python and Streamlit.

## Overview

This application allows you to practice technical trading using historical stock data. It features:
-   **Candlestick Charts**: Daily, Weekly, and Index charts.
-   **Indicators**: Moving Averages (5, 25, 75) and Stochastics (%K, %D, Slow%D).
-   **Simulation**: Step through data day-by-day, hiding future price movements.
-   **Trading**: Buy, Sell, and Close positions to practice entries and exits.
-   **Review**: Track your equity curve and trade statistics (Win Rate, Profit Factor).

## Installation

1.  Clone the repository.
2.  Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Run the Streamlit application:

```bash
streamlit run app.py
```

1.  **Sidebar**: Enter a Ticker Symbol (e.g., `7203.T` for Toyota) and choose a Start Mode (Random or Beginning).
2.  **Start**: Click "Start / Restart".
3.  **Trade**:
    -   Use **Next Day** to advance the chart.
    -   Use **BUY** / **SELL** to enter positions (100 shares).
    -   Use **CLOSE** to exit positions.
4.  **Review**: Check the "Review" tab for your asset curve and statistics.

## Tech Stack

-   Python 3.9+
-   Streamlit
-   Plotly
-   yfinance
-   Pandas & pandas_ta
