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
    # Authorization Config
    USERS = {
        "user1": {"pw": "pass1", "level": 1},
        "user2": {"pw": "pass2", "level": 2},
        "dev":   {"pw": "devpass", "level": 3}
    }

    # Helper Functions
    def calculate_metrics(history):
        if not history:
            return 0, 0, 0, 0, 0, 0

        wins = [t['PnL'] for t in history if t.get('PnL', 0) > 0]
        losses = [t['PnL'] for t in history if t.get('PnL', 0) < 0]
        
        # Check against non-zero PnL for closed trades
        closed_trades = [t for t in history if t.get('PnL', 0) != 0]
        win_rate = len(wins) / len(closed_trades) if closed_trades else 0
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
    if 'pos_start_date' not in st.session_state:
        st.session_state.pos_start_date = None
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.user_level = 0
        st.session_state.username = ""

    def login():
        st.title("Login")
        with st.form("login_form"):
            user = st.text_input("Username")
            pw = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            if submitted:
                if user in USERS and USERS[user]["pw"] == pw:
                    st.session_state.authenticated = True
                    st.session_state.user_level = USERS[user]["level"]
                    st.session_state.username = user
                    st.rerun()
                else:
                    st.error("Invalid credentials")

    if not st.session_state.authenticated:
        login()
        return

    def start_simulation(ticker, index_ticker, start_mode="Random", initial_balance=INITIAL_BALANCE):
        with st.spinner("Loading Data..."):
            df = data_loader.fetch_data(ticker)
            if df is not None:
                df = data_loader.calculate_indicators(df)
                st.session_state.df_daily = df
                st.session_state.df_weekly = data_loader.get_weekly_data(df)

                df_idx = data_loader.fetch_data(index_ticker)
                if df_idx is not None:
                    st.session_state.df_index = data_loader.calculate_indicators(df_idx)

                st.session_state.simulation_started = True
                st.session_state.balance = initial_balance
                st.session_state.position = 0
                st.session_state.avg_price = 0.0
                st.session_state.trade_history = []
                st.session_state.equity_history = []
                st.session_state.pos_start_date = None

                if start_mode == "Random":
                    # Ensure we have enough history for indicators (75 days + buffer)
                    min_idx = 100
                    max_idx = max(min_idx, len(df) - 200) # Leave at least 200 days for sim
                    if max_idx > min_idx:
                        st.session_state.current_step = random.randint(min_idx, max_idx)
                    else:
                        st.session_state.current_step = min_idx

                elif start_mode == "Latest":
                    st.session_state.current_step = len(df) - 1
                else:
                    st.session_state.current_step = 100
            else:
                st.error("Failed to load data.")

    def execute_trade(action, current_price, current_date, ticker, qty_param=100):
        # qty_param is the quantity requested by the user for the action
        pnl = 0
        trade_type = ""
        actual_qty_transacted = 0 # To record in history
        
        # Store initial position and avg_price for PnL calculation if position flips
        initial_position = st.session_state.position
        initial_avg_price = st.session_state.avg_price

        if action == "BUY":
            remaining_qty_to_buy = qty_param

            # 1. Covering Short
            if st.session_state.position < 0:
                cover_qty = min(remaining_qty_to_buy, abs(st.session_state.position))
                pnl += (st.session_state.avg_price - current_price) * cover_qty
                st.session_state.balance -= (current_price * cover_qty) # Cash out for cover
                st.session_state.position += cover_qty
                remaining_qty_to_buy -= cover_qty
                actual_qty_transacted = cover_qty # For this part of the trade
                trade_type = "Buy (Cover)"

                if st.session_state.position == 0:
                    st.session_state.avg_price = 0
                    # If position is fully closed, reset pos_start_date
                    st.session_state.pos_start_date = None

            # 2. Opening/Adding Long
            if remaining_qty_to_buy > 0:
                cost = current_price * remaining_qty_to_buy
                
                unrealized = (current_price - st.session_state.avg_price) * st.session_state.position if st.session_state.position != 0 else 0
                equity = st.session_state.balance + unrealized
                
                new_pos_size = abs(st.session_state.position + remaining_qty_to_buy)
                new_pos_value = new_pos_size * current_price
                
                if new_pos_value > equity * 3:
                     st.error(f"Order Rejected: Exceeds 3x Leverage Limit. Max: ¥{equity*3:,.0f}, Requested: ¥{new_pos_value:,.0f}")
                     return

                old_val = st.session_state.position * st.session_state.avg_price
                st.session_state.balance -= cost
                st.session_state.position += remaining_qty_to_buy
                st.session_state.avg_price = (old_val + cost) / st.session_state.position
                
                actual_qty_transacted = remaining_qty_to_buy # For this part of the trade
                trade_type = "Buy (Long)" if trade_type == "" else "Buy (Flip)"

        elif action == "SELL":
            remaining_qty_to_sell = qty_param

            # 1. Closing Long
            if st.session_state.position > 0:
                close_qty = min(remaining_qty_to_sell, st.session_state.position)
                pnl += (current_price - st.session_state.avg_price) * close_qty
                st.session_state.balance += (current_price * close_qty)
                st.session_state.position -= close_qty
                remaining_qty_to_sell -= close_qty
                actual_qty_transacted = close_qty # For this part of the trade
                trade_type = "Sell (Close)"

                if st.session_state.position == 0:
                    st.session_state.avg_price = 0
                    # If position is fully closed, reset pos_start_date
                    st.session_state.pos_start_date = None

            # 2. Opening/Adding Short
            if remaining_qty_to_sell > 0:
                unrealized = (current_price - st.session_state.avg_price) * st.session_state.position if st.session_state.position != 0 else 0
                equity = st.session_state.balance + unrealized
                
                new_pos_size = abs(st.session_state.position - remaining_qty_to_sell)
                new_pos_value = new_pos_size * current_price
                
                if new_pos_value > equity * 3:
                     st.error(f"Order Rejected: Exceeds 3x Leverage Limit. Max: ¥{equity*3:,.0f}, Requested: ¥{new_pos_value:,.0f}")
                     return

                cost = current_price * remaining_qty_to_sell
                
                old_val = abs(st.session_state.position) * st.session_state.avg_price
                st.session_state.balance += cost
                
                if st.session_state.position < 0: # Already short
                     st.session_state.avg_price = (old_val + cost) / (abs(st.session_state.position) + remaining_qty_to_sell)
                else: # First short position
                    st.session_state.avg_price = current_price

                st.session_state.position -= remaining_qty_to_sell
                actual_qty_transacted = remaining_qty_to_sell # For this part of the trade
                trade_type = "Sell (Short)" if trade_type == "" else "Sell (Flip)"

        elif action == "CLOSE":
            if st.session_state.position == 0:
                return # Nothing to close

            qty_to_close = abs(st.session_state.position)
            actual_qty_transacted = qty_to_close

            if st.session_state.position > 0:
                # Close Long
                pnl = (current_price - st.session_state.avg_price) * qty_to_close
                st.session_state.balance += (current_price * qty_to_close)
                trade_type = "Sell (Close)"
            else:
                # Close Short
                pnl = (st.session_state.avg_price - current_price) * qty_to_close
                st.session_state.balance -= (current_price * qty_to_close)
                trade_type = "Buy (Close)"

            st.session_state.position = 0
            st.session_state.avg_price = 0
            # If position is fully closed, reset pos_start_date
            st.session_state.pos_start_date = None
        
        # Calculate Holding Period
        holding_days = "" # Default to empty string if not applicable

        # If position was closed (pnl != 0 implies a closing component)
        # Or if the trade type explicitly indicates a close/cover
        if pnl != 0 or "Close" in trade_type or "Cover" in trade_type:
            if st.session_state.pos_start_date is not None:
                holding_days = (current_date - st.session_state.pos_start_date).days
        
        # Update pos_start_date if a new position is opened or an existing one is modified
        if st.session_state.position != 0 and st.session_state.pos_start_date is None:
            st.session_state.pos_start_date = current_date
        
        # Record History
        st.session_state.trade_history.append({
            'Step': st.session_state.current_step,
            'Date': current_date,
            'Ticker': ticker,
            'Action': action, # Original action (BUY/SELL/CLOSE)
            'Type': trade_type, # Derived type (Buy (Cover), Sell (Long), etc.)
            'Price': current_price,
            'Qty': actual_qty_transacted, # Actual quantity involved in the final trade type
            'PnL': pnl,
            'Days': holding_days
        })
        st.rerun()

    def draw_candlestick(df, title, trade_history=None):
        # Convert index to string to remove gaps (Category Axis)
        df = df.copy()
        df.index = df.index.strftime('%Y-%m-%d')
        
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                            vertical_spacing=0.03, subplot_titles=(title, 'Volume', 'Stochastics'),
                            row_heights=[0.5, 0.2, 0.3])

        # Candlestick (Row 1)
        fig.add_trace(go.Candlestick(x=df.index,
                    open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                    name='Price',
                    increasing_line_color='red', increasing_fillcolor='red',
                    decreasing_line_color='green', decreasing_fillcolor='green'), row=1, col=1)

        # MAs (Row 1)
        colors = {'MA5': 'orange', 'MA25': 'blue', 'MA75': 'green'}
        for ma, color in colors.items():
            if ma in df.columns:
                fig.add_trace(go.Scatter(x=df.index, y=df[ma], line=dict(color=color, width=1), name=ma), row=1, col=1)

        # Volume (Row 2) - same color logic: Red if Up, Green if Down
        # Up (Close >= Open) -> Red
        # Down (Close < Open) -> Green
        vol_colors = ['red' if c >= o else 'green' for c, o in zip(df['Close'], df['Open'])]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='Volume', marker_color=vol_colors), row=2, col=1)

        # Trade Markers (Row 1)
        if trade_history:
            # Filter history for current view
            # Use original datetime index for robust matching (Daily & Weekly)
            # df.index passed to this function is likely DatetimeIndex (before str conversion above)
            # Wait, line 265 converted it: df.index = df.index.strftime...
            # We need the original datetime index.
            # df was copied at line 264. But we need access to the original index values.
            # We can re-parse, or better:
            # Access the original df passed in? No, we modified local 'df'.
            # Let's assume we can convert strings back or just rely on the strings being ISO?
            # No, 'bfill' needs math.
            # Let's convert back for matching.
            dt_index = pd.to_datetime(df.index)
            
            # Helper to find location
            # Note: dt_index is monotonic increasing.
            
            visible_trades = []
            for t in trade_history:
                t_date = t['Date']
                
                # Fast check bounds
                if t_date > dt_index[-1]:
                    continue
                
                # Find nearest candle forward (containing the trade)
                # get_indexer returns -1 if out of bounds (but we handled right bound)
                # For left bound (trade older than first candle):
                # bfill will return index 0. We must check distance.
                
                try:
                    idx = dt_index.get_indexer([t_date], method='bfill')[0]
                except:
                    idx = -1
                    
                if idx != -1:
                    matched_date = dt_index[idx]
                    
                    # Check if match is reasonable (e.g. within 7 days for Weekly, 1 day for Daily)
                    # Daily gap might be larger due to holidays (e.g. 5 days).
                    # Weekly gap max 7 days.
                    # Let's say if diff > 10 days, it's definitely an old trade mapping to first candle.
                    if (matched_date - t_date).days <= 10:
                        date_str = matched_date.strftime('%Y-%m-%d')
                        visible_trades.append({**t, 'DateStr': date_str})

            buy_dates = [t['DateStr'] for t in visible_trades if t['Action'] == 'BUY']
            buy_prices = [t['Price'] for t in visible_trades if t['Action'] == 'BUY']

            sell_dates = [t['DateStr'] for t in visible_trades if t['Action'] == 'SELL']
            sell_prices = [t['Price'] for t in visible_trades if t['Action'] == 'SELL']

            close_dates = [t['DateStr'] for t in visible_trades if t['Action'] == 'CLOSE']
            close_prices = [t['Price'] for t in visible_trades if t['Action'] == 'CLOSE']

            if buy_dates:
                fig.add_trace(go.Scatter(x=buy_dates, y=buy_prices, mode='markers', marker=dict(symbol='triangle-up', size=12, color='blue', line=dict(width=1, color='black')), name='Buy'), row=1, col=1)
            if sell_dates:
                fig.add_trace(go.Scatter(x=sell_dates, y=sell_prices, mode='markers', marker=dict(symbol='triangle-down', size=12, color='blue', line=dict(width=1, color='white')), name='Sell'), row=1, col=1)
            if close_dates:
                fig.add_trace(go.Scatter(x=close_dates, y=close_prices, mode='markers', marker=dict(symbol='x', size=8, color='gold', line=dict(width=1, color='black')), name='Close'), row=1, col=1)

        # Stochastics (Row 3)
        if 'Stoch_K' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['Stoch_K'], line=dict(color='blue', width=1), name='%K'), row=3, col=1)
        if 'Stoch_D' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['Stoch_D'], line=dict(color='orange', width=1), name='%D'), row=3, col=1)
        if 'Stoch_SlowD' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['Stoch_SlowD'], line=dict(color='green', width=1), name='Slow%D'), row=3, col=1)

        # Add stripes (background bands) every 5 days
        # Since x-axis is category (strings), we can use integer indices - 0.5 to position rects
        n_candles = len(df.index)
        for i in range(0, n_candles, 10):
            # i is the integer index of the start
            x0 = i - 0.5
            x1 = min(i + 5, n_candles) - 0.5
            
            fig.add_vrect(x0=x0, x1=x1, fillcolor="#333333", opacity=0.5, layer="below", line_width=0)

        fig.update_layout(
            xaxis_rangeslider_visible=False, 
            height=700, 
            margin=dict(l=0, r=0, t=30, b=0), 
            template="plotly_dark",
        )
        fig.update_yaxes(title_text="Price", row=1, col=1, showgrid=True, gridcolor="#444444")
        fig.update_yaxes(title_text="Volume", row=2, col=1, showgrid=True, gridcolor="#444444")
        fig.update_yaxes(title_text="Stoch", range=[0, 100], row=3, col=1, showgrid=True, gridcolor="#444444")
        fig.update_xaxes(showgrid=True, gridcolor="#444444", type='category', tickangle=90, dtick=5) # dtick 5 to match stripes roughly
        return fig

    # --- Main UI ---

    # Sidebar
    st.sidebar.title("Configuration")
    st.sidebar.write(f"User: {st.session_state.username} (Level {st.session_state.user_level})")
    
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.rerun()

    if st.session_state.user_level == 1:
        input_ticker = "7203.T"
        st.sidebar.text_input("Ticker", value=input_ticker, disabled=True)
    else:
        input_ticker = st.sidebar.text_input("Ticker", DEFAULT_TICKER)
    input_index = st.sidebar.selectbox("Index Ticker", ["^N225", "^TOPX", "^MOTHERS"], index=0)
    start_mode_sel = st.sidebar.radio("Start Mode", ["Random", "Latest"])
    
    # Use text_input to allow comma formatting, parse manually
    initial_balance_str = st.sidebar.text_input("Initial Balance", value=f"{INITIAL_BALANCE:,}")
    try:
        initial_balance_in = int(initial_balance_str.replace(",", ""))
    except ValueError:
        st.sidebar.error("Invalid balance format. Using default.")
        initial_balance_in = INITIAL_BALANCE
    
    # Trade Goal
    trade_goal = st.sidebar.slider("Trade Goal (Count)", 5, 50, 10)
            
    if st.sidebar.button("Start / Restart"):
        # Map selection to mode string
        if "Random" in start_mode_sel:
            mode = "Random"
        else:
            mode = "Latest"
        
        start_simulation(input_ticker, input_index, mode, initial_balance_in)
        st.rerun()
    # Stats Panel in Sidebar
    if st.session_state.simulation_started:
        st.sidebar.divider()
        st.sidebar.subheader("Trade Log")
        if st.session_state.trade_history:
            log_df = pd.DataFrame(st.session_state.trade_history)
            # Format for display
            # Ensure cols exist
            if 'Qty' not in log_df.columns: log_df['Qty'] = 0
            if 'Days' not in log_df.columns: log_df['Days'] = ""
            if 'Ticker' not in log_df.columns: log_df['Ticker'] = ""
            
            display_log = log_df[['Date', 'Ticker', 'Type', 'Price', 'Qty', 'PnL', 'Days']].copy()
            display_log['Date'] = display_log['Date'].dt.strftime('%Y-%m-%d')
            display_log['Price'] = display_log['Price'].apply(lambda x: f"{x:,.0f}")
            display_log['Qty'] = display_log['Qty'].apply(lambda x: f"{x:,.0f}")
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
        # Custom spacing and style to match "Ruin Simulator" look roughly
        # We use st.markdown with HTML for better control over "Tabs" visual interference
        
        st.markdown(f"""
        <div style="display: flex; flex-direction: row; justify-content: space-between; margin-bottom: 10px; padding: 10px 0; border-bottom: 1px solid #444;">
            <div style="flex: 1;">
                <div style="font-size: 12px; color: #aaa;">Date</div>
                <div style="font-size: 20px; font-weight: bold;">{current_date.strftime('%Y-%m-%d')}</div>
            </div>
            <div style="flex: 1;">
                <div style="font-size: 12px; color: #aaa;">Equity</div>
                <div style="font-size: 20px; font-weight: bold;">¥{equity_val:,.0f}</div>
            </div>
            <div style="flex: 1;">
                <div style="font-size: 12px; color: #aaa;">Pos (Avg)</div>
                <div style="font-size: 20px; font-weight: bold;">{st.session_state.position} (@{st.session_state.avg_price:,.0f})</div>
            </div>
            <div style="flex: 1;">
                <div style="font-size: 12px; color: #aaa;">Unrealized P&L</div>
                <div style="font-size: 20px; font-weight: bold; color: {'#00ff00' if unrealized >= 0 else '#ff0000'};">¥{unrealized:,.0f}</div>
            </div>
            <div style="flex: 1;">
                <div style="font-size: 12px; color: #aaa;">Win Rate / PF</div>
                <div style="font-size: 20px; font-weight: bold;">{win_rate:.1%} / {pf:.2f}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Main Layout: 2 Columns (Chart | Controls)
        c_left, c_right = st.columns([3, 1])

        with c_left:
            # Tabs Logic for RBAC
            if st.session_state.user_level == 1:
                tab_names = ["Daily", "Review"]
            else:
                tab_names = ["Daily", "Weekly", "Index", "Review"]
            
            tabs = st.tabs(tab_names)
            
            # Map content to tabs based on name
            # Daily (Always present)
            with tabs[0]: # Daily
                # Show last 30 days
                display_df = df_slice.tail(30)
                fig = draw_candlestick(display_df, f"Daily: {input_ticker}", st.session_state.trade_history)
                st.plotly_chart(fig, use_container_width=True)

            # Weekly (Level 2+)
            if "Weekly" in tab_names:
                idx = tab_names.index("Weekly")
                with tabs[idx]:
                    if df_w_slice is not None:
                        # Show last 50 weeks
                        st.plotly_chart(draw_candlestick(df_w_slice.tail(50), "Weekly", st.session_state.trade_history), use_container_width=True)

            # Index (Level 2+)
            if "Index" in tab_names:
                idx = tab_names.index("Index")
                with tabs[idx]:
                    if df_i_slice is not None:
                        st.plotly_chart(draw_candlestick(df_i_slice.tail(30), f"Index: {input_index}"), use_container_width=True)

            # Review (Always present)
            with tabs[-1]: # Review is always last
                st.subheader("Asset Transition")
                if st.session_state.equity_history:
                    eq_df = pd.DataFrame(st.session_state.equity_history)
                    st.line_chart(eq_df.set_index('Date')['Equity'])

                st.subheader("Statistics")
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    st.write(f"Total Trades: {len([t for t in st.session_state.trade_history if t.get('PnL',0)!=0])}")
                    st.write(f"Total Profit: ¥{t_profit:,.0f}")
                    st.write(f"Total Loss: ¥{t_loss:,.0f}")
                with col_s2:
                    st.write(f"Avg Profit: ¥{avg_profit:,.0f}")
                    st.write(f"Avg Loss: ¥{avg_loss:,.0f}")
                    st.write(f"Max Drawdown: {max_dd:.2%}")

        with c_right:
            st.subheader("Actions")
            
            # Navigation
            # Disable Next buttons if at end of data
            df_len = len(df_slice) if df_slice is not None else 0 # this is slice, wait. We need total df len.
            # st.session_state.df_daily is the source.
            total_len = len(st.session_state.df_daily) if st.session_state.df_daily is not None else 0
            is_at_end = st.session_state.current_step >= total_len - 1
            
            if st.button("Next Day (+1)", use_container_width=True, disabled=is_at_end):
                st.session_state.current_step = min(st.session_state.current_step + 1, total_len - 1)
                st.rerun()

            if st.button("Next Week (+5)", use_container_width=True, disabled=is_at_end):
                st.session_state.current_step = min(st.session_state.current_step + 5, total_len - 1)
                st.rerun()

            # Check Goal
            trades_count = len([t for t in st.session_state.trade_history if t.get('PnL', 0) != 0])
            if trades_count >= trade_goal:
                st.success(f"Goal Reached! You have completed {trades_count} trades.")
                
                # Convert log to CSV for download
                csv = pd.DataFrame(st.session_state.trade_history).to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download Trade Results (CSV)",
                    data=csv,
                    file_name='trade_results.csv',
                    mime='text/csv',
                )

            st.divider()

            # Trade Entry
            st.write("### Order")
            trade_type = st.radio("Type", ["BUY", "SELL"])
            quantity = st.number_input("Quantity", min_value=100, step=100, value=100)
            
            # Disable buttons if at end or goal reached? 
            # User said "Result can be saved", implies stopping or at least pausing.
            # Let's keep it active but warn/celebrate.
            disabled = current_idx >= len(df_full) - 1
            
            if st.button("Place Order", use_container_width=True, disabled=disabled):
                execute_trade(trade_type, current_price, current_date, input_ticker, quantity)

            st.divider()

            # Position Management
            st.write("### Exit")
            if st.session_state.position != 0:
                if st.button("Close Position", use_container_width=True, disabled=disabled):
                    # Close current position
                    execute_trade("CLOSE", current_price, current_date, input_ticker)
            else:
                st.info("No Open Position") 
            
            st.divider()
            
            # Back Button - RBAC Level 3 Only
            if st.session_state.user_level >= 3:
                if st.button("Back (-1)", use_container_width=True):
                    new_step = max(100, st.session_state.current_step - 1)
                    st.session_state.current_step = new_step
                    st.rerun()

    else:
        st.info("Welcome to Trade Training Studio. Configure settings in the sidebar and start.")

if __name__ == "__main__":
    if st.runtime.exists():
        main()
    else:
        print(f"Please run this application with: streamlit run {sys.argv[0]}")
