import streamlit as st

if 'bt_results' not in st.session_state:
    st.session_state.bt_results = "Data"

st.write("Results:", st.session_state.bt_results)

if st.button("Clear"):
    del st.session_state.bt_results

st.download_button("Download", "hello world", "test.csv")
