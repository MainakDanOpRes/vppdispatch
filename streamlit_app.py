import streamlit as st
import requests
import pandas as pd

st.title("VPP Dispatch Dashboard")

# Simple input for demonstration
customer_id = st.text_input("Customer ID", "C1")

if st.button("Run Dispatch"):
    # Replace this with your actual API URL
    API_URL = "https://vppdispatch.onrender.com/dispatch"
    
    payload = {
        "customer_id": customer_id,
        "pv_kw": [0.0] * 12,
        "fixed_load_kw": [1.0] * 12,
        "price_buy": [0.2] * 12,
        "price_sell": [0.1] * 12
    }
    
    response = requests.post(API_URL, json=payload)
    
    if response.status_code == 200:
        data = response.json()
        st.success("Dispatch complete!")
        
        # Create a chart
        df = pd.DataFrame({
            "Grid": data['p_grid'],
            "Charge": data['p_ch'],
            "Discharge": data['p_dis']
        })
        st.line_chart(df)
    else:
        st.error(f"Error: {response.status_code}")