import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import random
import sys
import data_loader

def main():
    # Page Config
    st.set_page_config(layout="wide", page_title="Trade Training Studio")

    # Constants
    INITIAL_BALANCE = 10000000 # 10 Million Yen for flexibility
    DEFAULT_TICKER = "7203.T"
    DEFAULT_TICKER = "7203.T"
    # INDEX_TICKER removed, will be selected by user
    LOT_SIZE = 100
    LOT_SIZE = 100

    # Helper Functions
    def calculate_metrics(history):
        if not history:
            return 0, 0, 0, 0, 0, 0

        wins = [t['pnl'] for t in history if t.get('pnl', 0) > 0]
        losses = [t['pnl'] for t in history if t.get('pnl', 0) < 0]

        win_rate = len(wins) / len([t for t in history if t.get('pnl', 0) != 0]) if wins or losses else 0
        total_profit = sum(wins)
        total_loss = abs(sum(losses))
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

        avg_profit = total_profit / len(wins) if wins else 0
        avg_loss = total_loss / len(losses) if losses else 0

        return win_rate, total_profit, total_loss, profit_factor, avg_profit, avg_loss

    def calculate_max_drawdown(equity_history):
        if not equity_history:
            return 0.0

        equity_curve = [e['Equity'] for e in equity_history]
        max_drawdown = 0.0
        peak = equity_curve[0]

        for value in equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            if dd > max_drawdown:
                max_drawdown = dd

        return max_drawdown

    # Session State
    if 'simulation_started' not in st.session_state:
        st.session_state.simulation_started = False
    if 'current_step' not in st.session_state:
        st.session_state.current_step = 100
    if 'balance' not in st.session_state:
        st.session_state.balance = INITIAL_BALANCE
    if 'position' not in st.session_state:
        st.session_state.position = 0
    if 'avg_price' not in st.session_state:
        st.session_state.avg_price = 0.0
    if 'trade_history' not in st.session_state:
        st.session_state.trade_history = []
    if 'equity_history' not in st.session_state:
        st.session_state.equity_history = []
    if 'df_daily' not in st.session_state:
        st.session_state.df_daily = None
    if 'df_weekly' not in st.session_state:
        st.session_state.df_weekly = None
    if 'df_index' not in st.session_state:
        st.session_state.df_index = None

    def start_simulation(ticker, index_ticker, start_mode="Random"):
        with st.spinner("Loading Data..."):
            df = data_loader.fetch_data(ticker)
            if df is not None:
                df = data_loader.calculate_indicators(df)
                st.session_state.df_daily = df
                st.session_state.df_weekly = data_loader.get_weekly_data(df)

                st.session_state.df_weekly = data_loader.get_weekly_data(df)

                df_idx = data_loader.fetch_data(index_ticker)
                if df_idx is not None:
                    st.session_state.df_index = data_loader.calculate_indicators(df_idx)

                st.session_state.simulation_started = True
                st.session_state.balance = INITIAL_BALANCE
                st.session_state.position = 0
                st.session_state.avg_price = 0.0
                st.session_state.trade_history = []
                st.session_state.equity_history = []

                if start_mode == "Random":
                    # Ensure we have enough history for indicators (75 days + buffer)
                    min_idx = 100
                    max_idx = max(min_idx, len(df) - 200) # Leave at least 200 days for sim
                    if max_idx > min_idx:
                        st.session_state.current_step = random.randint(min_idx, max_idx)
                    else:
                        st.session_state.current_step = min_idx
                else:
                    st.session_state.current_step = 100
            else:
                st.error("Failed to load data.")

    def execute_trade(action, current_price, current_date):
        qty = LOT_SIZE
        pnl = 0
        trade_type = ""

        if action == "BUY":
            # Buying logic
            # 1. Covering Short
            if st.session_state.position < 0:
                cover_qty = min(qty, abs(st.session_state.position))
                # PnL = (Entry - Exit) * Qty
                pnl += (st.session_state.avg_price - current_price) * cover_qty
                st.session_state.position += cover_qty
                # Balance update: PnL is realized, Margin/Cash handles itself?
                # Let's use simplified Cash Model:
                # Short Entry: Cash + Proceeds.
                # Short Exit: Cash - Cost.
                st.session_state.balance -= (current_price * cover_qty)

                if st.session_state.position == 0:
                    st.session_state.avg_price = 0

                qty -= cover_qty # Remaining to buy (flip to long)
                trade_type = "Buy (Cover)"

            # 2. Opening/Adding Long
            if qty > 0:
                cost = current_price * qty
                if st.session_state.balance >= cost: # Basic check
                    old_val = st.session_state.position * st.session_state.avg_price
                    st.session_state.balance -= cost
                    st.session_state.position += qty
                    st.session_state.avg_price = (old_val + cost) / st.session_state.position
                    trade_type = "Buy (Long)" if trade_type == "" else "Buy (Flip)"
                else:
                    st.error("Insufficient Funds to Open Long")
                    return

        elif action == "SELL":
            # Selling logic
            # 1. Closing Long
            if st.session_state.position > 0:
                close_qty = min(qty, st.session_state.position)
                # PnL = (Exit - Entry) * Qty
                pnl += (current_price - st.session_state.avg_price) * close_qty
                st.session_state.balance += (current_price * close_qty)
                st.session_state.position -= close_qty

                if st.session_state.position == 0:
                    st.session_state.avg_price = 0

                qty -= close_qty
                trade_type = "Sell (Close)"

            # 2. Opening/Adding Short
            if qty > 0:
                # Short proceeds add to cash (simplified)
                proceeds = current_price * qty
                st.session_state.balance += proceeds

                # Weighted Avg for Short
                old_val = abs(st.session_state.position) * st.session_state.avg_price
                st.session_state.position -= qty
                st.session_state.avg_price = (old_val + proceeds) / abs(st.session_state.position)
                trade_type = "Sell (Short)" if trade_type == "" else "Sell (Flip)"

        elif action == "CLOSE":
            if st.session_state.position == 0:
                return

            if st.session_state.position > 0:
                # Close Long
                qty = st.session_state.position
                pnl = (current_price - st.session_state.avg_price) * qty
                st.session_state.balance += (current_price * qty)
                trade_type = "Close (Long)"
            else:
                # Close Short
                qty = abs(st.session_state.position)
                pnl = (st.session_state.avg_price - current_price) * qty
                st.session_state.balance -= (current_price * qty)
                trade_type = "Close (Short)"

            st.session_state.position = 0
            st.session_state.avg_price = 0

        # Record History
        st.session_state.trade_history.append({
            'Step': st.session_state.current_step,
            'Date': current_date,
            'Action': action,
            'Type': trade_type,
            'Price': current_price,
            'PnL': pnl
        })
        st.rerun()

    def draw_candlestick(df, title, trade_history=None):
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            vertical_spacing=0.03, subplot_titles=(title, 'Stochastics'),
                            row_heights=[0.7, 0.3])

        # Candlestick
        fig.add_trace(go.Candlestick(x=df.index,
                    open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                    name='Price'), row=1, col=1)

        # MAs
        colors = {'MA5': 'orange', 'MA25': 'blue', 'MA75': 'green'}
        for ma, color in colors.items():
            if ma in df.columns:
                fig.add_trace(go.Scatter(x=df.index, y=df[ma], line=dict(color=color, width=1), name=ma), row=1, col=1)

        # Trade Markers
        if trade_history:
            # Filter history for current view
            start_date = df.index[0]
            end_date = df.index[-1]

            # Helper to filter trades within the view window
            visible_trades = [t for t in trade_history if start_date <= t['Date'] <= end_date]

            buy_dates = [t['Date'] for t in visible_trades if t['Action'] == 'BUY']
            buy_prices = [t['Price'] for t in visible_trades if t['Action'] == 'BUY']

            sell_dates = [t['Date'] for t in visible_trades if t['Action'] == 'SELL']
            sell_prices = [t['Price'] for t in visible_trades if t['Action'] == 'SELL']

            close_dates = [t['Date'] for t in visible_trades if t['Action'] == 'CLOSE']
            close_prices = [t['Price'] for t in visible_trades if t['Action'] == 'CLOSE']

            if buy_dates:
                fig.add_trace(go.Scatter(x=buy_dates, y=buy_prices, mode='markers', marker=dict(symbol='triangle-up', size=10, color='red'), name='Buy'), row=1, col=1)
            if sell_dates:
                fig.add_trace(go.Scatter(x=sell_dates, y=sell_prices, mode='markers', marker=dict(symbol='triangle-down', size=10, color='blue'), name='Sell'), row=1, col=1)
            if close_dates:
                fig.add_trace(go.Scatter(x=close_dates, y=close_prices, mode='markers', marker=dict(symbol='x', size=8, color='black'), name='Close'), row=1, col=1)

        # Stochastics
        if 'Stoch_K' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['Stoch_K'], line=dict(color='blue', width=1), name='%K'), row=2, col=1)
        if 'Stoch_D' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['Stoch_D'], line=dict(color='orange', width=1), name='%D'), row=2, col=1)
        if 'Stoch_SlowD' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['Stoch_SlowD'], line=dict(color='green', width=1), name='Slow%D'), row=2, col=1)

        fig.update_layout(xaxis_rangeslider_visible=False, height=600, margin=dict(l=0, r=0, t=30, b=0))
        fig.update_yaxes(title_text="Price", row=1, col=1)
        fig.update_yaxes(title_text="Stoch", range=[0, 100], row=2, col=1)
        return fig

    # --- Main UI ---

    # Sidebar
    st.sidebar.title("Configuration")
    input_ticker = st.sidebar.text_input("Ticker", DEFAULT_TICKER)
    input_index = st.sidebar.selectbox("Index Ticker", ["^N225", "^TOPX", "^MOTHERS"], index=0)
    start_mode = st.sidebar.radio("Start Mode", ["Random", "Specific Date (Beginning)"])

    if st.sidebar.button("Start / Restart"):
        start_simulation(input_ticker, input_index, start_mode)

    # Stats Panel in Sidebar
    if st.session_state.simulation_started:
        st.sidebar.divider()
        st.sidebar.subheader("Trade Log")
        if st.session_state.trade_history:
            log_df = pd.DataFrame(st.session_state.trade_history)
            # Format for display
            display_log = log_df[['Date', 'Type', 'Price', 'PnL']].copy()
            display_log['Date'] = display_log['Date'].dt.strftime('%Y-%m-%d')
            display_log['Price'] = display_log['Price'].apply(lambda x: f"{x:,.0f}")
            display_log['PnL'] = display_log['PnL'].apply(lambda x: f"{x:,.0f}")
            st.sidebar.dataframe(display_log, height=300)

    # Main Area
    if st.session_state.simulation_started and st.session_state.df_daily is not None:

        # Data Slicing
        current_idx = st.session_state.current_step
        df_full = st.session_state.df_daily

        # Check bounds
        if current_idx >= len(df_full):
            current_idx = len(df_full) - 1
            st.warning("Simulation reached end of data.")

        df_slice = df_full.iloc[:current_idx+1]
        current_date = df_slice.index[-1]
        current_price = df_slice['Close'].iloc[-1]

        # Update Equity History (for graph)
        equity_val = st.session_state.balance + (st.session_state.position * current_price)

        # Avoid duplicate entry for same step if just refreshing
        if not st.session_state.equity_history or st.session_state.equity_history[-1]['Step'] != current_idx:
            st.session_state.equity_history.append({'Step': current_idx, 'Date': current_date, 'Equity': equity_val})

        # Weekly Slice
        df_w = st.session_state.df_weekly
        df_w_slice = df_w[df_w.index <= current_date] if df_w is not None else None

        # Index Slice
        df_i = st.session_state.df_index
        df_i_slice = df_i[df_i.index <= current_date] if df_i is not None else None

        # Header Metrics
        unrealized = (current_price - st.session_state.avg_price) * st.session_state.position if st.session_state.position != 0 else 0

        # Calculate Win Rate etc
        win_rate, t_profit, t_loss, pf, avg_profit, avg_loss = calculate_metrics(st.session_state.trade_history)
        max_dd = calculate_max_drawdown(st.session_state.equity_history)

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Date", current_date.strftime('%Y-%m-%d'))
        m2.metric("Equity", f"¥{equity_val:,.0f}")
        m3.metric("Pos (Avg)", f"{st.session_state.position} (@{st.session_state.avg_price:,.0f})")
        m4.metric("Unrealized P&L", f"¥{unrealized:,.0f}", delta_color="normal")
        m5.metric("Win Rate / PF", f"{win_rate:.1%} / {pf:.2f}")

        # Tabs
        t1, t2, t3, t4 = st.tabs(["Daily", "Weekly", "Index", "Review"])

        with t1:
            # Show last 100 days
            display_df = df_slice.tail(100)
            fig = draw_candlestick(display_df, f"Daily: {input_ticker}", st.session_state.trade_history)
            st.plotly_chart(fig, use_container_width=True)

        with t2:
            if df_w_slice is not None:
                # Show last 50 weeks
                st.plotly_chart(draw_candlestick(df_w_slice.tail(50), "Weekly"), use_container_width=True)

        with t3:
            if df_i_slice is not None:
                st.plotly_chart(draw_candlestick(df_i_slice.tail(100), f"Index: {INDEX_TICKER}"), use_container_width=True)

        with t4:
            st.subheader("Asset Transition")
            if st.session_state.equity_history:
                eq_df = pd.DataFrame(st.session_state.equity_history)
                st.line_chart(eq_df.set_index('Date')['Equity'])

            st.subheader("Statistics")
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.write(f"Total Trades: {len([t for t in st.session_state.trade_history if t.get('pnl',0)!=0])}")
                st.write(f"Total Profit: ¥{t_profit:,.0f}")
                st.write(f"Total Loss: ¥{t_loss:,.0f}")
            with col_s2:
                st.write(f"Avg Profit: ¥{avg_profit:,.0f}")
                st.write(f"Avg Loss: ¥{avg_loss:,.0f}")
                st.write(f"Max Drawdown: {max_dd:.2%}")

        # Controls
        st.divider()
        c1, c2, c3, c4, c5 = st.columns(5)

        # Navigation
        if c1.button("Back (-1)"):
            # Decrease step but don't go below minimum (usually 100)
            new_step = max(100, st.session_state.current_step - 1)
            st.session_state.current_step = new_step
            st.rerun()

        if c2.button("Next Day (+1)"):
            st.session_state.current_step += 1
            st.rerun()

        if c2.button("Next Week (+5)"):
            st.session_state.current_step += 5
            st.rerun()

        # Trading
        # Disable buttons if at end
        disabled = current_idx >= len(df_full) - 1

        if c3.button("BUY", disabled=disabled):
            execute_trade("BUY", current_price, current_date)

        if c4.button("SELL", disabled=disabled):
            execute_trade("SELL", current_price, current_date)

        if c5.button("CLOSE", disabled=disabled):
            execute_trade("CLOSE", current_price, current_date)

    else:
        st.info("Welcome to Trade Training Studio. Configure settings in the sidebar and start.")

if __name__ == "__main__":
    if st.runtime.exists():
        main()
    else:
        print(f"Please run this application with: streamlit run {sys.argv[0]}")
