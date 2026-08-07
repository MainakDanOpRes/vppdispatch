"""
VPP Dispatch Dashboard
-----------------------
Streamlit frontend for the vpp_dispatch FastAPI service.

Three modes:
  1. Quick Dispatch    - upload/paste a simple time-series (legacy /dispatch endpoint)
  2. Multi-Asset Builder - interactively build a fleet of PV/battery/load/grid
                           assets and run /dispatch/multi-asset
  3. Batch Dispatch    - run several customer configs at once via /dispatch/batch
"""

import json
import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="VPP Dispatch Dashboard", page_icon="⚡", layout="wide")
st.title("⚡ VPP Dispatch Dashboard")
st.caption(f"Backend: {BACKEND_URL}")


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def api_get(path: str):
    r = requests.get(f"{BACKEND_URL}{path}", timeout=15)
    r.raise_for_status()
    return r.json()


def api_post(path: str, payload: dict):
    r = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=60)
    if not r.ok:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        st.error(f"Request failed ({r.status_code}): {detail}")
        return None
    return r.json()


try:
    health = api_get("/health")
    st.sidebar.success(f"Backend reachable ({BACKEND_URL})")
except requests.exceptions.RequestException:
    st.sidebar.error(f"Cannot reach backend at {BACKEND_URL}. Is it running?")
    st.stop()

try:
    solvers = api_get("/solvers")
    st.sidebar.caption(f"Primary solver: **{solvers.get('primary')}**")
except requests.exceptions.RequestException:
    pass

mode = st.sidebar.radio(
    "Mode",
    ["Quick Dispatch", "Multi-Asset Builder", "Batch Dispatch"],
    help="Quick Dispatch uses the legacy default asset set. "
         "Multi-Asset Builder lets you configure any combination of assets. "
         "Batch Dispatch runs several customers in parallel.",
)


# ---------------------------------------------------------------------------
# Shared plotting helper
# ---------------------------------------------------------------------------


def plot_dispatch(t, price_buy=None, price_sell=None, series=None, title="Dispatch schedule"):
    """series: dict of {label: values} plotted as bars on the primary axis."""
    fig = go.Figure()
    series = series or {}
    for label, values in series.items():
        fig.add_trace(go.Bar(x=t, y=values, name=label, opacity=0.75))
    if price_buy is not None:
        fig.add_trace(go.Scatter(x=t, y=price_buy, name="Buy price", yaxis="y2", line=dict(color="red", width=2)))
    if price_sell is not None:
        fig.add_trace(
            go.Scatter(x=t, y=price_sell, name="Sell price", yaxis="y2", line=dict(color="orange", width=2, dash="dot"))
        )
    fig.update_layout(
        title=title,
        barmode="relative",
        xaxis_title="Period",
        yaxis=dict(title="kW"),
        yaxis2=dict(title="Price", overlaying="y", side="right"),
        legend=dict(orientation="h", y=-0.2),
    )
    return fig


# ===========================================================================
# MODE 1: Quick Dispatch (legacy endpoint, default asset fleet)
# ===========================================================================

if mode == "Quick Dispatch":
    st.subheader("Quick Dispatch")
    st.caption(
        "Uses the backend's default fleet (1 PV, 1 battery, 1 flexible EV-style load, "
        "1 grid connection) via `POST /dispatch`."
    )

    input_method = st.radio("Input method", ["Upload file", "Generate sample data"], horizontal=True)

    payload = None

    if input_method == "Upload file":
        uploaded_file = st.file_uploader("Upload a JSON or CSV file", type=["json", "csv"])
        if uploaded_file is not None:
            if uploaded_file.name.endswith(".json"):
                payload = json.load(uploaded_file)
                st.success("JSON loaded")
                st.json(payload)
            elif uploaded_file.name.endswith(".csv"):
                df = pd.read_csv(uploaded_file)
                st.dataframe(df, use_container_width=True)
                payload = {
                    "customer_id": str(df["customer_id"].iloc[0]) if "customer_id" in df else "csv_customer",
                    "pv_kw": df["pv_kw"].tolist(),
                    "fixed_load_kw": df["fixed_load_kw"].tolist(),
                    "price_buy": df["price_buy"].tolist(),
                    "price_sell": df["price_sell"].tolist(),
                }
    else:
        import numpy as np

        horizon = st.slider("Horizon (hours)", 6, 48, 24)
        seed = st.number_input("Random seed", min_value=0, value=42)
        rng = np.random.default_rng(seed)
        hours = np.arange(horizon)
        pv = np.clip(6 * np.sin((hours - 6) / 12 * np.pi), 0, None).round(2)
        load = (1.0 + 0.5 * np.sin(hours / 24 * 2 * np.pi) + rng.normal(0, 0.1, horizon)).clip(min=0.1).round(2)
        price_buy = (0.15 + 0.35 * (np.sin((hours - 18) / 24 * 2 * np.pi) ** 4)).round(3)
        price_sell = pd.Series([0.05] * horizon).round(3)

        df = pd.DataFrame(
            {"hour": hours, "pv_kw": pv, "fixed_load_kw": load, "price_buy": price_buy, "price_sell": price_sell}
        )
        st.caption("Edit values directly if needed:")
        df = st.data_editor(df, use_container_width=True, num_rows="fixed")
        payload = {
            "customer_id": "sample_customer",
            "pv_kw": df["pv_kw"].tolist(),
            "fixed_load_kw": df["fixed_load_kw"].tolist(),
            "price_buy": df["price_buy"].tolist(),
            "price_sell": df["price_sell"].tolist(),
        }

    if payload and st.button("Run dispatch", type="primary"):
        with st.spinner("Solving..."):
            result = api_post("/dispatch", payload)

        if result:
            st.success(
                "Solved with " + str(result["status"].get("solver", "?"))
                + " (" + str(result["status"].get("status", "?")) + ")"
            )
            m1, m2 = st.columns(2)
            m1.metric("Objective (net cost)", f"{result['objective']:.3f}")
            m2.metric("Solver", result["status"].get("solver", "unknown"))

            t = list(range(len(result["p_grid"])))
            fig = plot_dispatch(
                t,
                price_buy=payload["price_buy"],
                price_sell=payload["price_sell"],
                series={
                    "Grid": result["p_grid"],
                    "PV": result["pv_1"],
                    "Battery charge": result["p_ch"],
                    "Battery discharge": [-d for d in result["p_dis"]],
                    "Flex load (EV)": result["flex_ev"],
                },
                title="Quick dispatch schedule",
            )
            st.plotly_chart(fig, use_container_width=True)

            fig_soc = go.Figure()
            fig_soc.add_trace(go.Scatter(x=t, y=result["soc"], mode="lines+markers", name="Battery SOC"))
            fig_soc.update_layout(title="Battery state of charge", xaxis_title="Period", yaxis_title="kWh")
            st.plotly_chart(fig_soc, use_container_width=True)

            with st.expander("Raw response JSON"):
                st.json(result)


# ===========================================================================
# MODE 2: Multi-Asset Builder
# ===========================================================================

elif mode == "Multi-Asset Builder":
    st.subheader("Multi-Asset Builder")
    st.caption("Configure any combination of PV, battery, flexible load, fixed load, and grid assets.")

    if "assets" not in st.session_state:
        st.session_state.assets = []

    col_a, col_b = st.columns(2)
    with col_a:
        time_periods = st.number_input("Time periods", min_value=2, max_value=96, value=24)
    with col_b:
        batt_degradation_cost = st.number_input(
            "Battery degradation cost ($/kWh cycled)", min_value=0.0, value=0.01, step=0.01
        )

    st.markdown("#### Customer-level defaults (used by assets that don't set their own)")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        default_pv = st.text_input("Default PV profile (comma kW)", value=",".join(["0"] * time_periods))
    with d2:
        default_load = st.text_input("Default fixed load (comma kW)", value=",".join(["1"] * time_periods))
    with d3:
        default_price_buy = st.text_input("Default buy price (comma)", value=",".join(["0.2"] * time_periods))
    with d4:
        default_price_sell = st.text_input("Default sell price (comma)", value=",".join(["0.1"] * time_periods))

    def parse_series(s, n):
        vals = [float(x.strip()) for x in s.split(",") if x.strip() != ""]
        if len(vals) != n:
            st.warning(f"Expected {n} values, got {len(vals)} - padding/truncating.")
            vals = (vals + [0.0] * n)[:n]
        return vals

    st.markdown("---")
    st.markdown("#### Fleet")

    with st.expander("Add asset", expanded=len(st.session_state.assets) == 0):
        asset_type = st.selectbox("Asset type", ["pv", "battery", "flex_load", "fixed_load", "grid"])
        asset_id = st.text_input("Asset ID", value=f"{asset_type}_{len(st.session_state.assets) + 1}")

        new_asset = {"asset_id": asset_id, "asset_type": asset_type}

        if asset_type == "pv":
            profile = st.text_input("PV profile (comma kW, one per period)", key="pv_profile")
            if profile:
                new_asset["pv_profile_kw"] = parse_series(profile, time_periods)

        elif asset_type == "battery":
            c1, c2, c3 = st.columns(3)
            new_asset["capacity_kwh"] = c1.number_input("Capacity (kWh)", min_value=0.1, value=10.0)
            new_asset["p_charge_max_kw"] = c2.number_input("Max charge (kW)", min_value=0.1, value=5.0)
            new_asset["p_discharge_max_kw"] = c3.number_input("Max discharge (kW)", min_value=0.1, value=5.0)
            c4, c5, c6 = st.columns(3)
            new_asset["soc_min"] = c4.slider("Min SOC %", 0, 100, 10) / 100
            new_asset["soc_max"] = c5.slider("Max SOC %", 0, 100, 90) / 100
            new_asset["soc_initial"] = c6.number_input("Initial SOC (kWh)", min_value=0.0, value=5.0)
            eff1, eff2, deg = st.columns(3)
            new_asset["eff_charge"] = eff1.slider("Charge efficiency %", 50, 100, 95) / 100
            new_asset["eff_discharge"] = eff2.slider("Discharge efficiency %", 50, 100, 95) / 100
            new_asset["degradation_cost_per_kwh"] = deg.number_input("Degradation cost $/kWh", min_value=0.0, value=0.0)

        elif asset_type == "flex_load":
            fmode = st.radio("Mode", ["continuous", "on_off", "shiftable"], horizontal=True)
            new_asset["is_continuous"] = fmode == "continuous"
            new_asset["is_on_off"] = fmode == "on_off"
            new_asset["is_shiftable"] = fmode == "shiftable"
            tw1, tw2 = st.columns(2)
            t_start = tw1.number_input("Window start (period)", min_value=0, max_value=time_periods - 1, value=0)
            t_end = tw2.number_input(
                "Window end (period)", min_value=0, max_value=time_periods - 1, value=time_periods - 1
            )
            new_asset["time_window"] = [int(t_start), int(t_end)]
            if fmode == "continuous":
                p1, p2, p3 = st.columns(3)
                new_asset["p_min_kw"] = p1.number_input("Min power (kW)", min_value=0.0, value=0.0)
                new_asset["p_max_kw"] = p2.number_input("Max power (kW)", min_value=0.1, value=7.0)
                new_asset["energy_required_kwh"] = p3.number_input("Energy required (kWh)", min_value=0.1, value=14.0)
            elif fmode == "on_off":
                p1, p2 = st.columns(2)
                new_asset["p_on_kw"] = p1.number_input("Power when on (kW)", min_value=0.1, value=5.0)
                new_asset["energy_required_kwh"] = p2.number_input("Energy required (kWh)", min_value=0.1, value=14.0)
            else:
                profile = st.text_input("Load profile to shift (comma kW)", value="5,5,5")
                new_asset["load_profile"] = [float(x.strip()) for x in profile.split(",") if x.strip() != ""]
            new_asset["discomfort_cost_per_kwh"] = st.number_input(
                "Discomfort cost $/kWh (delay penalty)", min_value=0.0, value=0.0
            )

        elif asset_type == "fixed_load":
            profile = st.text_input("Fixed load profile (comma kW)", key="fixed_profile")
            if profile:
                new_asset["fixed_load_profile_kw"] = parse_series(profile, time_periods)
            new_asset["is_controllable"] = st.checkbox("Controllable (can be curtailed)", value=False)
            if new_asset["is_controllable"]:
                new_asset["curtailment_cost_per_kwh"] = st.number_input("Curtailment cost $/kWh", min_value=0.0, value=0.0)

        elif asset_type == "grid":
            c1, c2 = st.columns(2)
            new_asset["import_max_kw"] = c1.number_input("Max import (kW)", min_value=0.1, value=100.0)
            new_asset["export_max_kw"] = c2.number_input("Max export (kW)", min_value=0.1, value=100.0)
            use_custom_prices = st.checkbox(
                "Use custom prices for this grid asset (else use customer defaults)", value=False
            )
            if use_custom_prices:
                pb = st.text_input("Buy price (comma)", key="grid_buy")
                ps = st.text_input("Sell price (comma)", key="grid_sell")
                if pb:
                    new_asset["price_buy"] = parse_series(pb, time_periods)
                if ps:
                    new_asset["price_sell"] = parse_series(ps, time_periods)

        if st.button("Add asset"):
            st.session_state.assets.append(new_asset)
            st.rerun()

    if st.session_state.assets:
        st.markdown("#### Current fleet")
        for i, a in enumerate(st.session_state.assets):
            c1, c2 = st.columns([6, 1])
            c1.json(a, expanded=False)
            if c2.button("Remove", key=f"rm_{i}"):
                st.session_state.assets.pop(i)
                st.rerun()
    else:
        st.info("No assets yet - add one above.")

    if st.button("Run multi-asset dispatch", type="primary", disabled=not st.session_state.assets):
        config = {
            "customer_id": "dashboard_customer",
            "time_periods": int(time_periods),
            "pv_kw": parse_series(default_pv, time_periods),
            "fixed_load_kw": parse_series(default_load, time_periods),
            "price_buy": parse_series(default_price_buy, time_periods),
            "price_sell": parse_series(default_price_sell, time_periods),
            "assets": st.session_state.assets,
        }
        with st.spinner("Solving multi-asset dispatch..."):
            result = api_post(f"/dispatch/multi-asset?batt_degradation_cost={batt_degradation_cost}", config)

        if result:
            status = result["status"]
            results = result["results"]
            summary = result["summary"]

            if status.get("success"):
                st.success(f"Solved with {status.get('solver')} ({status.get('status')})")
            else:
                st.warning(f"Solver failed, showing fallback if available: {status.get('error')}")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total cost", f"{summary['total_cost']:.3f}")
            m2.metric("Assets", summary["num_assets"])
            m3.metric("Grid import (kWh)", f"{summary['grid_import_kwh']:.1f}")
            m4.metric("Grid export (kWh)", f"{summary['grid_export_kwh']:.1f}")

            t = list(range(results.get("time_periods", time_periods)))
            fig = plot_dispatch(
                t,
                price_buy=config["price_buy"],
                price_sell=config["price_sell"],
                series={"Grid": results.get("p_grid", [0.0] * len(t))},
                title="Grid power vs price",
            )
            st.plotly_chart(fig, use_container_width=True)

            st.markdown("#### Per-asset results")
            for asset_id, asset_data in results.get("assets", {}).items():
                with st.expander(f"{asset_data['type']} - {asset_id}", expanded=True):
                    asset_results = asset_data.get("results", {})
                    if asset_results:
                        plot_df = pd.DataFrame({k: v for k, v in asset_results.items() if isinstance(v, list)})
                        if not plot_df.empty:
                            st.line_chart(plot_df)
                    st.json(asset_results, expanded=False)

            with st.expander("Raw response JSON"):
                st.json(result)


# ===========================================================================
# MODE 3: Batch Dispatch
# ===========================================================================

else:
    st.subheader("Batch Dispatch")
    st.caption(
        "Upload a JSON array of customer configs (same shape as the Multi-Asset "
        "Builder's config) to dispatch several customers in parallel via POST /dispatch/batch."
    )

    example = [
        {
            "customer_id": "customer_a",
            "time_periods": 4,
            "assets": [
                {
                    "asset_id": "grid_1",
                    "asset_type": "grid",
                    "import_max_kw": 10,
                    "export_max_kw": 10,
                    "price_buy": [0.3, 0.3, 0.3, 0.3],
                    "price_sell": [0.05, 0.05, 0.05, 0.05],
                },
                {
                    "asset_id": "fixed_1",
                    "asset_type": "fixed_load",
                    "fixed_load_profile_kw": [1, 1, 1, 1],
                },
            ],
        },
        {
            "customer_id": "customer_b",
            "time_periods": 4,
            "assets": [
                {
                    "asset_id": "grid_1",
                    "asset_type": "grid",
                    "import_max_kw": 10,
                    "export_max_kw": 10,
                    "price_buy": [0.2, 0.4, 0.2, 0.4],
                    "price_sell": [0.05, 0.05, 0.05, 0.05],
                },
                {
                    "asset_id": "fixed_1",
                    "asset_type": "fixed_load",
                    "fixed_load_profile_kw": [2, 2, 2, 2],
                },
            ],
        },
    ]

    with st.expander("Show example payload"):
        st.json(example)

    uploaded = st.file_uploader("Upload customers JSON", type=["json"])
    use_example = st.checkbox("Use example payload instead", value=uploaded is None)

    customers = example if use_example else (json.load(uploaded) if uploaded else None)

    if customers and st.button("Run batch dispatch", type="primary"):
        with st.spinner(f"Solving {len(customers)} customers in parallel..."):
            result = api_post("/dispatch/batch", {"customers": customers})

        if result:
            overall = result["overall_status"]
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total customers", overall["total_customers"])
            m2.metric("Successful", overall["successful_customers"])
            m3.metric("Failed", overall["failed_customers"])
            m4.metric("Total objective", f"{overall['total_objective']:.2f}")

            for customer_id, cust_result in result["results"].items():
                status = cust_result["status"]
                res = cust_result["results"]
                icon = "OK" if status.get("success") else "FAIL"
                with st.expander(f"[{icon}] {customer_id} - objective {res.get('objective', 'n/a')}"):
                    t = list(range(res.get("time_periods", 0)))
                    if res.get("p_grid"):
                        fig = plot_dispatch(t, series={"Grid": res["p_grid"]}, title=f"{customer_id} grid power")
                        st.plotly_chart(fig, use_container_width=True)
                    st.json(cust_result, expanded=False)
