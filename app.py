import streamlit as st
import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import random
import sys
import extra_streamlit_components as stx
import data_loader
import backtest

def main():
    # Page Config
    st.set_page_config(layout="wide", page_title="Trade Training Studio")

    # Constants
    INITIAL_BALANCE = 10000000 # 10 Million Yen for flexibility
    DEFAULT_TICKER = "7203.T"

    # Random Ticker List (Major JP Stocks)
    MAJOR_TICKERS = [
        "7203.T", "9984.T", "6758.T", "6861.T", "8035.T", # Toyota, Softbank, Sony, Keyence, Tokyo Electron
        "6501.T", "7974.T", "9432.T", "8306.T", "6098.T", # Hitachi, Nintendo, NTT, MUFG, Recruit
        "4063.T", "4502.T", "6367.T", "6902.T", "7741.T", # Shin-Etsu, Takeda, Daikin, Denso, Hoya
        "6981.T", "6954.T", "7267.T", "8411.T", "8001.T"  # Murata, Fanuc, Honda, Mizuho, Itochu
    ]

    # Authorization Config
    try:
        USERS = st.secrets["users"]
    except Exception:
        USERS = {}

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

    # Session State Initialization
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

    def get_manager():
        return stx.CookieManager()

    cookie_manager = get_manager()
    auth_token = cookie_manager.get(cookie="auth_token")

    if not st.session_state.authenticated:
        if auth_token and auth_token in USERS:
            st.session_state.authenticated = True
            st.session_state.user_level = USERS[auth_token]["level"]
            st.session_state.username = auth_token

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
                    cookie_manager.set("auth_token", user, expires_at=datetime.datetime.now() + datetime.timedelta(days=30))
                    st.rerun()
                else:
                    st.error("Invalid credentials")

    if not st.session_state.authenticated:
        login()
        return

    # --- Common UI Components ---
    st.sidebar.title("Configuration")
    st.sidebar.write(f"User: {st.session_state.username} (Level {st.session_state.user_level})")

    # App Mode Selector
    app_mode = st.sidebar.radio("Application Mode", ["Manual Practice", "Auto Backtest"])

    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        cookie_manager.delete("auth_token")
        st.rerun()

    # --- Manual Practice Mode ---
    if app_mode == "Manual Practice":
        def start_simulation(ticker, index_ticker, start_mode="Random", initial_balance=INITIAL_BALANCE, specific_date=None):
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
                        min_idx = 100
                        max_idx = max(min_idx, len(df) - 200)
                        if max_idx > min_idx:
                            st.session_state.current_step = random.randint(min_idx, max_idx)
                        else:
                            st.session_state.current_step = min_idx

                    elif start_mode == "Latest":
                        st.session_state.current_step = len(df) - 1

                    elif start_mode == "Specific Date" and specific_date:
                        try:
                            target_ts = pd.Timestamp(specific_date)
                            idx = df.index.get_indexer([target_ts], method='nearest')[0]
                            st.session_state.current_step = max(100, idx)
                        except Exception as e:
                            st.sidebar.error(f"Date lookup failed: {e}")
                            st.session_state.current_step = 100
                    else:
                        st.session_state.current_step = 100
                else:
                    st.error("Failed to load data.")

        def execute_trade(action, current_price, current_date, ticker, qty_param=100):
            pnl = 0
            trade_type = ""
            actual_qty_transacted = 0

            initial_position = st.session_state.position
            initial_avg_price = st.session_state.avg_price

            if action == "BUY":
                remaining_qty_to_buy = qty_param
                if st.session_state.position < 0:
                    cover_qty = min(remaining_qty_to_buy, abs(st.session_state.position))
                    pnl += (st.session_state.avg_price - current_price) * cover_qty
                    st.session_state.balance -= (current_price * cover_qty)
                    st.session_state.position += cover_qty
                    remaining_qty_to_buy -= cover_qty
                    actual_qty_transacted = cover_qty
                    trade_type = "Buy (Cover)"

                    if st.session_state.position == 0:
                        st.session_state.avg_price = 0
                        st.session_state.pos_start_date = None

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
                    actual_qty_transacted = remaining_qty_to_buy
                    trade_type = "Buy (Long)" if trade_type == "" else "Buy (Flip)"

            elif action == "SELL":
                remaining_qty_to_sell = qty_param
                if st.session_state.position > 0:
                    close_qty = min(remaining_qty_to_sell, st.session_state.position)
                    pnl += (current_price - st.session_state.avg_price) * close_qty
                    st.session_state.balance += (current_price * close_qty)
                    st.session_state.position -= close_qty
                    remaining_qty_to_sell -= close_qty
                    actual_qty_transacted = close_qty
                    trade_type = "Sell (Close)"

                    if st.session_state.position == 0:
                        st.session_state.avg_price = 0
                        st.session_state.pos_start_date = None

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
                    if st.session_state.position < 0:
                        st.session_state.avg_price = (old_val + cost) / (abs(st.session_state.position) + remaining_qty_to_sell)
                    else:
                        st.session_state.avg_price = current_price
                    st.session_state.position -= remaining_qty_to_sell
                    actual_qty_transacted = remaining_qty_to_sell
                    trade_type = "Sell (Short)" if trade_type == "" else "Sell (Flip)"

            elif action == "CLOSE":
                if st.session_state.position == 0: return
                qty_to_close = abs(st.session_state.position)
                actual_qty_transacted = qty_to_close
                if st.session_state.position > 0:
                    pnl = (current_price - st.session_state.avg_price) * qty_to_close
                    st.session_state.balance += (current_price * qty_to_close)
                    trade_type = "Sell (Close)"
                else:
                    pnl = (st.session_state.avg_price - current_price) * qty_to_close
                    st.session_state.balance -= (current_price * qty_to_close)
                    trade_type = "Buy (Close)"
                st.session_state.position = 0
                st.session_state.avg_price = 0
                st.session_state.pos_start_date = None
            
            holding_days = ""
            if pnl != 0 or "Close" in trade_type or "Cover" in trade_type:
                if st.session_state.pos_start_date is not None:
                    holding_days = (current_date - st.session_state.pos_start_date).days
            
            if st.session_state.position != 0 and st.session_state.pos_start_date is None:
                st.session_state.pos_start_date = current_date

            st.session_state.trade_history.append({
                'Step': st.session_state.current_step,
                'Date': current_date,
                'Ticker': ticker,
                'Action': action,
                'Type': trade_type,
                'Price': current_price,
                'Qty': actual_qty_transacted,
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

            fig.add_trace(go.Candlestick(x=df.index,
                        open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                        name='Price',
                        increasing_line_color='red', increasing_fillcolor='red',
                        decreasing_line_color='green', decreasing_fillcolor='green',
                        hoverinfo='x+text',
                        text=[f"O:{o:,.0f}<br>H:{h:,.0f}<br>L:{l:,.0f}<br>C:{c:,.0f}" for o, h, l, c in zip(df['Open'], df['High'], df['Low'], df['Close'])]
                        ), row=1, col=1)

            colors = {'MA5': 'orange', 'MA25': 'blue', 'MA75': 'green'}
            for ma, color in colors.items():
                if ma in df.columns:
                    fig.add_trace(go.Scatter(x=df.index, y=df[ma], line=dict(color=color, width=1), name=ma, hoverinfo='skip'), row=1, col=1)

            vol_colors = ['red' if c >= o else 'green' for c, o in zip(df['Close'], df['Open'])]
            fig.add_trace(go.Bar(x=df.index, y=df['Volume'], name='Volume', marker_color=vol_colors), row=2, col=1)

            if trade_history:
                dt_index = pd.to_datetime(df.index)
                visible_trades = []
                for t in trade_history:
                    t_date = t['Date']
                    if t_date > dt_index[-1]: continue
                    try:
                        idx = dt_index.get_indexer([t_date], method='bfill')[0]
                    except:
                        idx = -1
                    if idx != -1:
                        matched_date = dt_index[idx]
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

            if 'Stoch_K' in df.columns:
                fig.add_trace(go.Scatter(x=df.index, y=df['Stoch_K'], line=dict(color='blue', width=1), name='%K'), row=3, col=1)
            if 'Stoch_D' in df.columns:
                fig.add_trace(go.Scatter(x=df.index, y=df['Stoch_D'], line=dict(color='orange', width=1), name='%D'), row=3, col=1)
            if 'Stoch_SlowD' in df.columns:
                fig.add_trace(go.Scatter(x=df.index, y=df['Stoch_SlowD'], line=dict(color='green', width=1), name='Slow%D'), row=3, col=1)

            n_candles = len(df.index)
            for i in range(0, n_candles, 10):
                x0 = i - 0.5
                x1 = min(i + 5, n_candles) - 0.5
                fig.add_vrect(x0=x0, x1=x1, fillcolor="#333333", opacity=0.5, layer="below", line_width=0)

            fig.update_layout(xaxis_rangeslider_visible=False, height=700, margin=dict(l=0, r=0, t=30, b=0), template="plotly_dark",)
            fig.update_yaxes(title_text="Price", row=1, col=1, showgrid=True, gridcolor="#444444")
            fig.update_yaxes(title_text="Volume", row=2, col=1, showgrid=True, gridcolor="#444444")
            fig.update_yaxes(title_text="Stoch", range=[0, 100], row=3, col=1, showgrid=True, gridcolor="#444444")
            fig.update_xaxes(showgrid=True, gridcolor="#444444", type='category', tickangle=90, dtick=5)
            return fig

        if st.session_state.user_level == 1:
            input_ticker = "7203.T"
            st.sidebar.text_input("Ticker", value=input_ticker, disabled=True)
        else:
            if 'random_ticker_trigger' not in st.session_state:
                st.session_state.random_ticker_trigger = False
            col_t1, col_t2 = st.sidebar.columns([3, 1])
            with col_t2:
                if st.button("🎲", help="Random Ticker"):
                    st.session_state.random_ticker_trigger = True
            default_val = DEFAULT_TICKER
            if st.session_state.random_ticker_trigger:
                default_val = random.choice(MAJOR_TICKERS)
                st.session_state.random_ticker_trigger = False
            if 'ticker_input_val' not in st.session_state:
                st.session_state.ticker_input_val = DEFAULT_TICKER
            if default_val != DEFAULT_TICKER:
                st.session_state.ticker_input_val = default_val
            with col_t1:
                input_ticker = st.text_input("Ticker", key="ticker_input_val")
        
        input_index = st.sidebar.selectbox("Index Ticker", ["^N225", "^TOPX", "^MOTHERS"], index=0)

        start_options = ["Random", "Latest"]
        if st.session_state.user_level >= 2:
            start_options.append("Specific Date")
            
        start_mode_sel = st.sidebar.radio("Start Mode", start_options)

        specific_date_val = None
        if start_mode_sel == "Specific Date":
            specific_date_val = st.sidebar.date_input("Start Date", value=datetime.date(2023, 1, 1))

        initial_balance_str = st.sidebar.text_input("Initial Balance", value=f"{INITIAL_BALANCE:,}")
        try:
            initial_balance_in = int(initial_balance_str.replace(",", ""))
        except ValueError:
            st.sidebar.error("Invalid balance format. Using default.")
            initial_balance_in = INITIAL_BALANCE

        trade_goal = st.sidebar.slider("Trade Goal (Count)", 5, 50, 10)

        if st.sidebar.button("Start / Restart"):
            start_simulation(input_ticker, input_index, start_mode_sel, initial_balance_in, specific_date_val)
            st.rerun()
            
        if st.session_state.simulation_started:
            st.sidebar.divider()
            st.sidebar.subheader("Trade Log")
            if st.session_state.trade_history:
                log_df = pd.DataFrame(st.session_state.trade_history)
                if 'Qty' not in log_df.columns: log_df['Qty'] = 0
                if 'Days' not in log_df.columns: log_df['Days'] = ""
                if 'Ticker' not in log_df.columns: log_df['Ticker'] = ""
                display_log = log_df[['Date', 'Ticker', 'Type', 'Price', 'Qty', 'PnL', 'Days']].copy()
                display_log['Date'] = display_log['Date'].dt.strftime('%Y-%m-%d')
                display_log['Price'] = display_log['Price'].apply(lambda x: f"{x:,.0f}")
                display_log['Qty'] = display_log['Qty'].apply(lambda x: f"{x:,.0f}")
                display_log['PnL'] = display_log['PnL'].apply(lambda x: f"{x:,.0f}")
                st.sidebar.dataframe(display_log, height=300)

        if st.session_state.simulation_started and st.session_state.df_daily is not None:
            current_idx = st.session_state.current_step
            df_full = st.session_state.df_daily
            if current_idx >= len(df_full):
                current_idx = len(df_full) - 1
                st.warning("Simulation reached end of data.")

            df_slice = df_full.iloc[:current_idx+1]
            current_date = df_slice.index[-1]
            current_price = df_slice['Close'].iloc[-1]
            equity_val = st.session_state.balance + (st.session_state.position * current_price)

            if not st.session_state.equity_history or st.session_state.equity_history[-1]['Step'] != current_idx:
                st.session_state.equity_history.append({'Step': current_idx, 'Date': current_date, 'Equity': equity_val})

            df_w = st.session_state.df_weekly
            df_w_slice = df_w[df_w.index <= current_date] if df_w is not None else None
            df_i = st.session_state.df_index
            df_i_slice = df_i[df_i.index <= current_date] if df_i is not None else None

            unrealized = (current_price - st.session_state.avg_price) * st.session_state.position if st.session_state.position != 0 else 0
            win_rate, t_profit, t_loss, pf, avg_profit, avg_loss = calculate_metrics(st.session_state.trade_history)
            max_dd = calculate_max_drawdown(st.session_state.equity_history)

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

            c_left, c_right = st.columns([3, 1])
            with c_left:
                if st.session_state.user_level == 1:
                    tab_names = ["Daily", "Review"]
                else:
                    tab_names = ["Daily", "Weekly", "Index", "Review"]
                tabs = st.tabs(tab_names)
                with tabs[0]:
                    display_df = df_slice.tail(30)
                    fig = draw_candlestick(display_df, f"Daily: {input_ticker}", st.session_state.trade_history)
                    st.plotly_chart(fig, use_container_width=True)
                if "Weekly" in tab_names:
                    with tabs[tab_names.index("Weekly")]:
                        if df_w_slice is not None:
                            st.plotly_chart(draw_candlestick(df_w_slice.tail(50), "Weekly", st.session_state.trade_history), use_container_width=True)
                if "Index" in tab_names:
                    with tabs[tab_names.index("Index")]:
                        if df_i_slice is not None:
                            st.plotly_chart(draw_candlestick(df_i_slice.tail(30), f"Index: {input_index}"), use_container_width=True)
                with tabs[-1]:
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
                total_len = len(st.session_state.df_daily) if st.session_state.df_daily is not None else 0
                is_at_end = st.session_state.current_step >= total_len - 1
                if st.button("Next Day (+1)", use_container_width=True, disabled=is_at_end):
                    st.session_state.current_step = min(st.session_state.current_step + 1, total_len - 1)
                    st.rerun()
                if st.button("Next Week (+5)", use_container_width=True, disabled=is_at_end):
                    st.session_state.current_step = min(st.session_state.current_step + 5, total_len - 1)
                    st.rerun()
                trades_count = len([t for t in st.session_state.trade_history if t.get('PnL', 0) != 0])
                if trades_count >= trade_goal:
                    st.success(f"Goal Reached! You have completed {trades_count} trades.")
                    csv = pd.DataFrame(st.session_state.trade_history).to_csv(index=False).encode('utf-8')
                    st.download_button(label="Download Trade Results (CSV)", data=csv, file_name='trade_results.csv', mime='text/csv',)
                st.divider()
                st.write("### Order")
                trade_type = st.radio("Type", ["BUY", "SELL"])
                quantity = st.number_input("Quantity", min_value=100, step=100, value=100)
                disabled = current_idx >= len(df_full) - 1
                if st.button("Place Order", use_container_width=True, disabled=disabled):
                    execute_trade(trade_type, current_price, current_date, input_ticker, quantity)
                st.divider()
                st.write("### Exit")
                if st.session_state.position != 0:
                    if st.button("Close Position", use_container_width=True, disabled=disabled):
                        execute_trade("CLOSE", current_price, current_date, input_ticker)
                else:
                    st.info("No Open Position")
                st.divider()
                if st.session_state.user_level >= 3:
                    if st.button("Back (-1)", use_container_width=True):
                        new_step = max(100, st.session_state.current_step - 1)
                        st.session_state.current_step = new_step
                        st.rerun()
        else:
            st.info("Welcome to Trade Training Studio. Configure settings in the sidebar and start.")

    elif app_mode == "Auto Backtest":
        st.header("Auto Backtest Mode")

        # --- Backtest Configuration ---
        with st.sidebar:
            st.divider()
            st.subheader("Backtest Settings")

            if st.session_state.user_level == 1:
                bt_ticker = "7203.T"
                st.text_input("Ticker", value=bt_ticker, disabled=True, key="bt_ticker_disp")
            else:
                bt_ticker = st.text_input("Ticker", value="7203.T", key="bt_ticker_input")

            # Date Range
            today = datetime.date.today()
            start_default = today - datetime.timedelta(days=365)
            bt_start_date = st.date_input("Start Date", value=start_default, key="bt_start")
            bt_end_date = st.date_input("End Date", value=today, key="bt_end")
            
            # Balance
            bt_balance = st.number_input("Initial Balance", value=10000000, step=1000000, key="bt_balance")
            
            # Strategy Mode
            st.subheader("Strategy Logic")
            bt_mode = st.selectbox("Entry/Stop Mode",
                                   ["Mode A (Touch)", "Mode B (Close/Next Open)"],
                                   index=0, key="bt_mode")
            mode_code = "A" if "Mode A" in bt_mode else "B"
            
            bt_exit = st.selectbox("Signal Exit Timing",
                                   ["Close (Same Day)", "Open (Next Day)"],
                                   index=0, key="bt_exit")
            exit_code = "Close" if "Close" in bt_exit else "Open"
            
            run_bt = st.button("Run Backtest", type="primary")

        # --- Main Area ---
        if run_bt:
            with st.spinner(f"Running Backtest for {bt_ticker}..."):
                # 1. Fetch Data
                df_bt = data_loader.fetch_data(bt_ticker)
                
                if df_bt is not None and not df_bt.empty:
                    # Calculate Indicators
                    df_bt = data_loader.calculate_indicators(df_bt)

                    # Slice Data based on Date Range
                    ts_start = pd.Timestamp(bt_start_date)
                    ts_end = pd.Timestamp(bt_end_date)

                    if df_bt.index[-1] < ts_start:
                         st.error("Data ends before Start Date.")
                    else:
                        # Slice from Start Date (Backtester skips first 20 rows for stabilization)
                        # To ensure users get trades from their Start Date, we should include a buffer.
                        # Buffer: 30 days (~20 trading days)
                        buffer_days = 40
                        mask_start = ts_start - pd.Timedelta(days=buffer_days)

                        df_run = df_bt[(df_bt.index >= mask_start) & (df_bt.index <= ts_end)]

                        if len(df_run) < 20:
                            st.warning("Not enough data points in the selected range (need at least 20 + buffer).")
                        else:
                            backtester = backtest.StochasticBacktester(initial_balance=bt_balance)
                            summary, log_df = backtester.run_backtest(df_run, mode=mode_code, exit_timing=exit_code)

                            # Filter results to show only trades within requested range
                            if not log_df.empty:
                                log_df = log_df[log_df['Signal Date'] >= ts_start]

                                # Re-calculate summary for filtered trades
                                if not log_df.empty:
                                    wins = log_df[log_df['PnL'] > 0]
                                    losses = log_df[log_df['PnL'] <= 0]
                                    total_profit = wins['PnL'].sum()
                                    total_loss = abs(losses['PnL'].sum())
                                    net_pnl = total_profit - total_loss
                                    pf = total_profit / total_loss if total_loss > 0 else float('inf')
                                    win_rate = (len(wins) / len(log_df)) * 100

                                    n_wins = len(wins)
                                    n_losses = len(losses)
                                    avg_profit = total_profit / n_wins if n_wins > 0 else 0
                                    avg_loss = total_loss / n_losses if n_losses > 0 else 0
                                    payoff = avg_profit / avg_loss if avg_loss > 0 else float('inf')
                                    avg_days = log_df['Holding Days'].mean() if len(log_df) > 0 else 0

                                    summary['Total Trades'] = len(log_df)
                                    summary['Win Rate'] = win_rate
                                    summary['Total PnL'] = net_pnl
                                    summary['Profit Factor'] = pf
                                    summary['Final Balance'] = bt_balance + net_pnl
                                    summary['Avg Profit'] = avg_profit
                                    summary['Avg Loss'] = avg_loss
                                    summary['Payoff Ratio'] = payoff
                                    summary['Avg Days'] = avg_days
                                else:
                                    summary = {"Total Trades": 0, "Win Rate": 0, "Total PnL": 0, "Profit Factor": 0, "Final Balance": bt_balance}

                            # Display Results
                            st.subheader("Backtest Results")

                            if not log_df.empty:
                                # 1. Summary Metrics
                                col1, col2, col3, col4 = st.columns(4)
                                col1.metric("Total Trades", summary['Total Trades'])
                                col2.metric("Win Rate", f"{summary['Win Rate']:.1f}%")
                                col3.metric("Profit Factor", f"{summary['Profit Factor']:.2f}")
                                col4.metric("Total PnL", f"¥{summary['Total PnL']:,.0f}")

                                col1, col2, col3, col4 = st.columns(4)
                                col1.metric("Avg Profit", f"¥{summary.get('Avg Profit', 0):,.0f}")
                                col2.metric("Avg Loss", f"¥{summary.get('Avg Loss', 0):,.0f}")
                                col3.metric("Payoff Ratio", f"{summary.get('Payoff Ratio', 0):.2f}")
                                col4.metric("Avg Hold (Days)", f"{summary.get('Avg Days', 0):.1f}")

                                st.metric("Final Balance", f"¥{summary['Final Balance']:,.0f}")

                                # 2. Equity Curve (Realized)
                                # Construct equity curve from filtered trades
                                # Base dataframe is df_run filtered by ts_start
                                df_chart = df_run[df_run.index >= ts_start]
                                equity_series = pd.Series(index=df_chart.index, data=0.0)

                                # Accumulate PnL by Exit Date
                                pnl_by_date = log_df.groupby('Exit Date')['PnL'].sum()
                                pnl_series = pnl_by_date.reindex(df_chart.index, fill_value=0).cumsum()
                                equity_series = bt_balance + pnl_series

                                st.line_chart(equity_series)
                                st.caption("Equity Curve (Realized PnL)")

                                # 3. Trade Log
                                st.dataframe(log_df)

                                csv = log_df.to_csv(index=False).encode('utf-8')
                                st.download_button("Download CSV", csv, "backtest_results.csv", "text/csv")

                            else:
                                st.warning("No trades generated in this period.")
                else:
                    st.error("Could not fetch data.")

if __name__ == "__main__":
    if st.runtime.exists():
        main()
    else:
        print(f"Please run this application with: streamlit run {sys.argv[0]}")
