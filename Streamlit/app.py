# Copyright (c) Streamlit Inc. (2018-2022) Snowflake Inc. (2022-2026)
# Licensed under the Apache License, Version 2.0 (the "License").
# http://www.apache.org/licenses/LICENSE-2.0
# Distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.
# Adapted from Streamlit's hello/dataframe_demo.py; see README.md.
"""DataFrame display excerpt; upload replaces the upstream remote demo dataset."""
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Interview data preview")
st.title("Interview data preview")
uploaded = st.file_uploader("Choose a CSV or Parquet file", type=["csv", "parquet"])
if uploaded is None:
    st.info("Choose your assessment data to start.")
    st.stop()
try:
    frame = pd.read_csv(uploaded) if uploaded.name.lower().endswith(".csv") else pd.read_parquet(uploaded)
except Exception as exc:
    st.error(f"Could not read this file: {exc}")
    st.stop()
st.dataframe(frame)
