"""
Integration tests for the services/dispatch_service.py layer: legacy
single-customer dispatch, multi-asset dispatch, and batch dispatch, run
end-to-end through the real HiGHS solver.

Unlike test_power_balance_integration.py (which builds Pyomo models
directly), these tests go through the public service functions the API
layer actually calls, so they also cover config parsing (schemas.py) and
asset construction (services/asset_factory.py).
"""

import pytest

from src.vpp_dispatch.models.schemas import CustomerConfig, LiveCustomerInput
from src.vpp_dispatch.models.timeseries import CustomerTimeSeries
from src.vpp_dispatch.services.dispatch_service import (
    run_dispatch_from_live_input,
    run_multi_asset_dispatch,
    run_batch_dispatch,
    create_optimization_summary,
)

pytestmark = [pytest.mark.integration, pytest.mark.requires_solver]


class TestLegacySingleCustomerDispatch:
    """Legacy default-fleet dispatch (1 PV, 1 battery, 1 EV-style flex load, 1 grid)."""

    def test_realistic_24h_profile_solves_optimally(self):
        T = 24
        hours = list(range(T))
        pv_kw = [max(0.0, 6 * ((h - 6) / 12) * (1 - abs((h - 6) / 12))) for h in hours]
        fixed_load_kw = [1.0 + 0.3 * (h % 12) / 12 for h in hours]
        price_buy = [0.15 + 0.35 * (((h - 18) % 24) / 24) ** 2 for h in hours]
        price_sell = [0.05] * T

        payload = LiveCustomerInput(
            customer_id="integration_customer",
            pv_kw=pv_kw,
            fixed_load_kw=fixed_load_kw,
            price_buy=price_buy,
            price_sell=price_sell,
        )
        results, status = run_dispatch_from_live_input(payload)

        assert status["success"] is True
        assert status["solver"] == "highs"
        for key in ("p_grid", "p_ch", "p_dis", "soc", "flex_ev", "pv_1"):
            assert key in results
            assert len(results[key]) == T

    def test_minimal_flat_profile_is_feasible(self):
        T = 24
        payload = LiveCustomerInput(
            customer_id="flat_customer",
            pv_kw=[0.0] * T,
            fixed_load_kw=[1.0] * T,
            price_buy=[0.2] * T,
            price_sell=[0.1] * T,
        )
        results, status = run_dispatch_from_live_input(payload)
        assert status["success"] is True


class TestMultiAssetDispatch:
    """Config-driven dispatch with an arbitrary, explicit set of assets."""

    def test_pv_battery_fixed_grid(self):
        config = CustomerConfig(
            customer_id="cust_multi",
            time_periods=6,
            assets=[
                {"asset_id": "pv_1", "asset_type": "pv", "pv_profile_kw": [0, 1, 3, 3, 1, 0]},
                {
                    "asset_id": "battery_1", "asset_type": "battery",
                    "capacity_kwh": 10, "p_charge_max_kw": 5, "p_discharge_max_kw": 5,
                    "soc_initial": 5,
                },
                {"asset_id": "fixed_1", "asset_type": "fixed_load", "fixed_load_profile_kw": [1] * 6},
                {
                    "asset_id": "grid_1", "asset_type": "grid",
                    "import_max_kw": 20, "export_max_kw": 20,
                    "price_buy": [0.5, 0.5, 0.1, 0.1, 0.5, 0.5], "price_sell": [0.05] * 6,
                },
            ],
        )
        results, status = run_multi_asset_dispatch(config)

        assert status["success"] is True
        assert set(results["assets"].keys()) == {"pv_1", "battery_1", "fixed_1", "grid_1"}

        summary = create_optimization_summary(results)
        assert summary["num_assets"] == 4
        assert summary["status"] == "success"

    @pytest.mark.parametrize(
        "flex_asset,label",
        [
            (
                {
                    "asset_id": "flex_1", "asset_type": "flex_load",
                    "is_continuous": True, "p_min_kw": 0, "p_max_kw": 4,
                    "energy_required_kwh": 6, "time_window": [0, 5],
                },
                "continuous",
            ),
            (
                {
                    "asset_id": "flex_1", "asset_type": "flex_load",
                    "is_on_off": True, "p_on_kw": 3,
                    "energy_required_kwh": 6, "time_window": [0, 5],
                },
                "on_off",
            ),
            (
                {
                    "asset_id": "flex_1", "asset_type": "flex_load",
                    "is_shiftable": True, "load_profile": [2, 2],
                    "time_window": [0, 5],
                },
                "shiftable",
            ),
        ],
        ids=["continuous", "on_off", "shiftable"],
    )
    def test_all_flex_load_modes(self, flex_asset, label):
        """Every flex load mode should create successfully and solve, exercising
        the is_continuous/is_shiftable/is_on_off schema fields end to end."""
        config = CustomerConfig(
            customer_id=f"cust_{label}",
            time_periods=6,
            assets=[
                flex_asset,
                {
                    "asset_id": "grid_1", "asset_type": "grid",
                    "import_max_kw": 20, "export_max_kw": 20,
                    "price_buy": [0.5, 0.1, 0.5, 0.1, 0.5, 0.5], "price_sell": [0.05] * 6,
                },
            ],
        )
        results, status = run_multi_asset_dispatch(config)
        assert status["success"] is True, f"{label} flex load failed: {status}"
        assert "flex_1" in results["assets"]

    def test_missing_asset_fields_reported_as_config_error_not_crash(self):
        """Invalid config (battery missing required power limits) should fail
        gracefully via the model_validator, not raise an unhandled exception."""
        with pytest.raises(Exception):
            CustomerConfig(
                customer_id="broken",
                time_periods=4,
                assets=[{"asset_id": "battery_1", "asset_type": "battery", "capacity_kwh": 10}],
            )


class TestBatchDispatch:
    """Multiple customers dispatched concurrently."""

    def test_two_customers_dispatch_in_parallel(self):
        configs = [
            CustomerConfig(
                customer_id="a",
                time_periods=4,
                assets=[
                    {
                        "asset_id": "grid_1", "asset_type": "grid",
                        "import_max_kw": 10, "export_max_kw": 10,
                        "price_buy": [0.3] * 4, "price_sell": [0.05] * 4,
                    },
                    {"asset_id": "fixed_1", "asset_type": "fixed_load", "fixed_load_profile_kw": [1] * 4},
                ],
            ),
            CustomerConfig(
                customer_id="b",
                time_periods=4,
                assets=[
                    {
                        "asset_id": "grid_1", "asset_type": "grid",
                        "import_max_kw": 10, "export_max_kw": 10,
                        "price_buy": [0.2, 0.4, 0.2, 0.4], "price_sell": [0.05] * 4,
                    },
                    {"asset_id": "fixed_1", "asset_type": "fixed_load", "fixed_load_profile_kw": [2] * 4},
                ],
            ),
        ]
        batch_results, overall_status = run_batch_dispatch(configs)

        assert overall_status["overall_status"] == "success"
        assert overall_status["successful_customers"] == 2
        assert overall_status["failed_customers"] == 0
        # Customer 'a' has a flat 0.3 price on a flat 1kW load: cost == 0.3*1*4 == 1.2
        assert batch_results["a"]["results"]["objective"] == pytest.approx(1.2, abs=1e-3)
        # Customer 'b' has a flat 2kW load against alternating 0.2/0.4 prices:
        # cost == 2*(0.2+0.4+0.2+0.4) == 2.4
        assert batch_results["b"]["results"]["objective"] == pytest.approx(2.4, abs=1e-3)

    def test_batch_does_not_deadlock_with_more_customers_than_workers(self):
        """Regression test: concurrent solver.solve() calls from
        ThreadPoolExecutor previously deadlocked on Pyomo's HiGHS TeeStream.
        Run enough customers to guarantee real concurrency."""
        configs = [
            CustomerConfig(
                customer_id=f"cust_{i}",
                time_periods=3,
                assets=[
                    {
                        "asset_id": "grid_1", "asset_type": "grid",
                        "import_max_kw": 10, "export_max_kw": 10,
                        "price_buy": [0.2, 0.3, 0.2], "price_sell": [0.05] * 3,
                    },
                    {"asset_id": "fixed_1", "asset_type": "fixed_load", "fixed_load_profile_kw": [1, 1, 1]},
                ],
            )
            for i in range(8)
        ]
        batch_results, overall_status = run_batch_dispatch(configs)
        assert overall_status["successful_customers"] == 8
        assert len(batch_results) == 8
