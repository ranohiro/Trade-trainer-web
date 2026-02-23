import streamlit as st
import json
import os
import glob

# Ensure strategies directory exists
os.makedirs("strategies", exist_ok=True)

# Default Strategy Template
DEFAULT_STRATEGY = {
    "strategy_name": "New Strategy",
    "memo": "",
    "setup_long_rules": [],
    "setup_short_rules": [],
    "maintain_long_rules": [],
    "maintain_short_rules": [],
    "exit_long_rules": [],
    "exit_short_rules": [],
    "entry_logic_long": {"entry_type": "recent_high", "lookback": 5},
    "stop_logic_long": {"stop_type": "current_low", "lookback": 1},
    "entry_logic_short": {"entry_type": "recent_low", "lookback": 5},
    "stop_logic_short": {"stop_type": "current_high", "lookback": 1}
}

INDICATORS = [
    "Stoch_K", "Stoch_D", "Stoch_SlowD",
    "Stoch_K_prev", "Stoch_D_prev", "Stoch_SlowD_prev",
    "Stoch_K_Angle",
    "RSI",
    "SMA5_dev", "SMA25_dev",
    "ATR", "Volume_Ratio",
    "Open_Gap_%",
    "dip_formed", "peak_formed"
]

def render_strategy_builder():
    st.title("Strategy Builder")

    # --- Initialize Session State ---
    # We initialize if not present.
    # Note: If user switches modes, we might want to preserve the state.
    if 'strategy_name' not in st.session_state:
        # Load default
        for k, v in DEFAULT_STRATEGY.items():
            st.session_state[k] = v

    # --- File Management (Sidebar) ---
    st.sidebar.divider()
    st.sidebar.subheader("Strategy Management")

    # List existing strategies
    strategy_files = glob.glob("strategies/*.json")
    strategy_files = [os.path.basename(f) for f in strategy_files]

    selected_file = st.sidebar.selectbox("Load Strategy", ["Select..."] + strategy_files)
    if st.sidebar.button("Load"):
        if selected_file != "Select...":
            try:
                with open(f"strategies/{selected_file}", "r") as f:
                    data = json.load(f)
                    # Validate keys? Ideally yes, but for now trust the file.
                    for k, v in data.items():
                        st.session_state[k] = v
                st.sidebar.success(f"Loaded '{selected_file}'")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Failed to load: {e}")

    st.sidebar.divider()

    # Inputs for saving
    # We bind these to session_state keys directly if possible, or update them.
    # Text input with key automatically updates session_state[key]
    st.sidebar.text_input("Strategy Name (Filename)", key='strategy_name')
    st.sidebar.text_area("Memo", key='memo')

    if st.sidebar.button("Save Strategy"):
        name = st.session_state.get('strategy_name', '')
        if not name:
            st.sidebar.error("Strategy Name is required.")
        else:
            filename = f"strategies/{name}.json"
            # Collect data
            data = {}
            for k in DEFAULT_STRATEGY.keys():
                if k in st.session_state:
                    data[k] = st.session_state[k]
                else:
                    data[k] = DEFAULT_STRATEGY[k]

            try:
                with open(filename, "w") as f:
                    json.dump(data, f, indent=2)
                st.sidebar.success(f"Saved to '{filename}'")
                st.rerun() # Refresh file list
            except Exception as e:
                st.sidebar.error(f"Failed to save: {e}")

    if st.sidebar.button("Reset to Default"):
        for k, v in DEFAULT_STRATEGY.items():
            st.session_state[k] = v
        st.rerun()

    # --- Strategy Rules UI ---

    st.subheader("Setup Rules (Entry Environment)")
    render_rule_list("setup_long_rules", "Long Setup Rules")
    render_rule_list("setup_short_rules", "Short Setup Rules")
    st.divider()

    st.subheader("Maintain Rules (Cancel Conditions)")
    st.info("💡 If these conditions become False while waiting for an Entry Trigger, the Setup is cancelled. (e.g. to avoid large gaps, add 'Open_Gap_%' < 3.0 here)")
    render_rule_list("maintain_long_rules", "Long Maintain Rules")
    render_rule_list("maintain_short_rules", "Short Maintain Rules")
    st.divider()

    st.subheader("Exit Rules")
    render_rule_list("exit_long_rules", "Long Exit Rules")
    render_rule_list("exit_short_rules", "Short Exit Rules")
    st.divider()

    st.subheader("Entry/Stop Pricing Logic")
    st.markdown("**Long Logic**")
    render_logic_config("entry_logic_long", "Entry")
    render_logic_config("stop_logic_long", "Stop")

    st.markdown("**Short Logic**")
    render_logic_config("entry_logic_short", "Entry")
    render_logic_config("stop_logic_short", "Stop")

def render_rule_list(key, title):
    st.markdown(f"**{title}**")

    if key not in st.session_state:
        st.session_state[key] = []

    rules = st.session_state[key]

    # Display existing rules
    to_delete = None
    for i, rule in enumerate(rules):
        cols = st.columns([5, 1])
        rule_str = f"{rule['left']} {rule['operator']} "
        if rule['right_type'] == 'value':
            rule_str += str(rule['right'])
        else:
            rule_str += f"[{rule['right']}]"

        cols[0].text(f"{i+1}. {rule_str}")
        if cols[1].button("🗑️", key=f"del_{key}_{i}"):
            to_delete = i

    if to_delete is not None:
        rules.pop(to_delete)
        st.rerun()

    # Add New Rule
    with st.expander("Add Rule"):
        c1, c2, c3, c4 = st.columns([3, 2, 3, 3])
        with c1: left = st.selectbox("Left", INDICATORS, key=f"left_{key}")
        with c2: op = st.selectbox("Op", [">", "<", ">=", "<=", "==", "!="], key=f"op_{key}")
        with c3: r_type = st.selectbox("Type", ["value", "indicator"], key=f"rtype_{key}")
        with c4:
            if r_type == "value":
                r_val = st.text_input("Value", value="0", key=f"rval_{key}")
            else:
                r_val = st.selectbox("Right", INDICATORS, key=f"rind_{key}")

        if st.button("Add", key=f"add_{key}"):
            final_val = r_val
            if r_type == "value":
                # Type conversion
                if str(final_val).lower() == "true": final_val = True
                elif str(final_val).lower() == "false": final_val = False
                else:
                    try: final_val = float(final_val)
                    except:
                        # Keep as string if not float/bool
                        pass

            new_rule = {
                "left": left,
                "operator": op,
                "right_type": r_type,
                "right": final_val
            }
            st.session_state[key].append(new_rule)
            st.rerun()

def render_logic_config(key, label):
    if key not in st.session_state:
        st.session_state[key] = {"entry_type": "recent_high", "lookback": 5} if "entry" in key else {"stop_type": "current_low", "lookback": 1}

    current_dict = st.session_state[key]

    # Determine initial index/value
    l_type = current_dict.get('entry_type', current_dict.get('stop_type', 'recent_high'))
    lookback = current_dict.get('lookback', 1)

    opts = ["recent_high", "recent_low", "current_high", "current_low", "close_price", "open_price"]
    idx = opts.index(l_type) if l_type in opts else 0

    c1, c2 = st.columns([3, 1])
    with c1:
        sel_type = st.selectbox(f"{label} Type", opts, index=idx, key=f"type_{key}")
    with c2:
        sel_lb = st.number_input("Lookback", min_value=1, value=lookback, key=f"lb_{key}")

    # Update dict
    type_field = "entry_type" if "entry" in key else "stop_type"
    st.session_state[key] = {type_field: sel_type, "lookback": sel_lb}
