import streamlit as st
import requests
import pandas as pd
import json

st.title("VPP Dispatch Dashboard")
st.subheader("Upload Customer Config")

uploaded_file = st.file_uploader("Upload a JSON or CSV file", 
                                 type=["json", "csv"])

if uploaded_file is not None:
    if uploaded_file.name.endswith(".json"):
        payload = json.load(uploaded_file)
        st.success("JSON loaded!")
        st.json(payload)
    elif uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
        st.dataframe(df)

        # build payload from csv column
        payload = {
            "customer_id": str(df["customer_id"].iloc[0]),
            "pv_kw": df["pv_kw"].tolist(),
            "fixed_load_kw": df["fixed_load_kw"].tolist(),
            "price_buy": df["price_buy"].tolist(),
            "price_sell": df["price_sell"].tolist()
        }

    # Simple input for demonstration
    if st.button("Run Dispatch"):
        API_URL = "https://vppdispatch.onrender.com/dispatch"
        response = requests.post(API_URL, json=payload)

        if response.status_code == 200:
            data = response.json()
            st.success("Dispatch complete!")
            result_df = pd.DataFrame({
                "Grid": data['p_grid'],
                "Charge": data['p_ch'],
                "Discharge": data['p_dis']
            })
            st.line_chart(result_df)
        else:
            st.error(f"Error: {response.status_code} — {response.text}")