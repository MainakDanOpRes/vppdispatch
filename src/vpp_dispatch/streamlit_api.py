import streamlit as st
import requests
import pandas as pd

st.title("VPP Dispatch Control Panel")

# Inputs for your dispatch
customer_id = st.text_input("Customer ID", "C1")
# Add more inputs for pv_kw, etc., using st.slider or st.number_input

if st.button("Run Dispatch"):
    payload = {
        "customer_id": customer_id,
        "pv_kw": [0.0] * 12, # Replace with dynamic inputs
        "fixed_load_kw": [1.0] * 12,
        "price_buy": [0.2] * 12,
        "price_sell": [0.1] * 12
    }
    
    # Call your deployed FastAPI backend
    API_URL = "https://vppdispatch.onrender.com/dispatch"
    response = requests.post(API_URL, json=payload)
    
    if response.status_code == 200:
        result = response.json()
        st.success("Dispatch complete!")
        st.write("### Results")
        st.json(result) # Displays JSON nicely
        # Or display in a table:
        # st.table(result['p_grid'])
    else:
        st.error("Failed to get dispatch data")

    if response.status_code == 200:
        data = response.json()
        st.success("Dispatch complete!")
        
        # 1. Convert the result dictionary into a Pandas DataFrame
        # We assume the lists in 'data' are all the same length
        df = pd.DataFrame({
            "Grid Power": data['p_grid'],
            "Charge Power": data['p_ch'],
            "Discharge Power": data['p_dis'],
            "State of Charge (SOC)": data['soc']
        })

        # 2. Display the data as an interactive chart
        st.subheader("Dispatch Power Profiles")
        st.line_chart(df)

        # 3. Display the raw data in a toggleable table
        with st.expander("View Raw Data Table"):
            st.table(df)
            
        st.metric("Objective Value", f"{data['objective']:.4f}")