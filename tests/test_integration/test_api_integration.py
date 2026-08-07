"""
Integration tests for src/vpp_dispatch/api.py using FastAPI's TestClient.

These exercise the full HTTP contract (request validation, response shape,
status codes) on top of the same dispatch_service functions covered in
test_dispatch_service_integration.py.
"""

import pytest
from fastapi.testclient import TestClient

from src.vpp_dispatch.api import app

pytestmark = [pytest.mark.integration, pytest.mark.requires_solver]

client = TestClient(app)


class TestHealthAndInfo:
    def test_root(self):
        r = client.get("/")
        assert r.status_code == 200
        body = r.json()
        assert body["service"] == "VPP Dispatch API"
        assert body["status"] == "ok"

    def test_health(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "healthy"}

    def test_solvers(self):
        r = client.get("/solvers")
        assert r.status_code == 200
        body = r.json()
        assert "highs" in body["available"]
        assert body["primary"] == "highs"


class TestLegacyDispatchEndpoint:
    def test_dispatch_returns_full_schedule(self):
        T = 24
        payload = {
            "customer_id": "api_customer",
            "pv_kw": [max(0, 5 * ((h - 6) / 12) * (1 - abs((h - 6) / 12))) for h in range(T)],
            "fixed_load_kw": [1.0] * T,
            "price_buy": [0.15 + 0.35 * (((h - 18) % 24) / 24) ** 2 for h in range(T)],
            "price_sell": [0.05] * T,
        }
        r = client.post("/dispatch", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["status"]["success"] is True
        for key in ("p_grid", "p_ch", "p_dis", "soc", "flex_ev", "pv_1"):
            assert len(body[key]) == T

    def test_dispatch_rejects_missing_field(self):
        r = client.post("/dispatch", json={"customer_id": "bad"})
        assert r.status_code == 422  # FastAPI/Pydantic validation error


class TestMultiAssetEndpoint:
    def test_multi_asset_dispatch_success(self):
        config = {
            "customer_id": "api_multi",
            "time_periods": 6,
            "assets": [
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
        }
        r = client.post("/dispatch/multi-asset", json=config)
        assert r.status_code == 200
        body = r.json()
        assert body["status"]["success"] is True
        assert body["summary"]["num_assets"] == 4
        assert set(body["results"]["assets"].keys()) == {"pv_1", "battery_1", "fixed_1", "grid_1"}

    def test_multi_asset_dispatch_invalid_config_returns_422(self):
        config = {
            "customer_id": "api_bad",
            "time_periods": 4,
            "assets": [{"asset_id": "battery_1", "asset_type": "battery", "capacity_kwh": 10}],
        }
        r = client.post("/dispatch/multi-asset", json=config)
        assert r.status_code == 422

    def test_multi_asset_respects_degradation_cost_query_param(self):
        config = {
            "customer_id": "api_degradation",
            "time_periods": 4,
            "assets": [
                {
                    "asset_id": "battery_1", "asset_type": "battery",
                    "capacity_kwh": 10, "p_charge_max_kw": 5, "p_discharge_max_kw": 5,
                    "soc_initial": 5,
                },
                {"asset_id": "fixed_1", "asset_type": "fixed_load", "fixed_load_profile_kw": [1] * 4},
                {
                    "asset_id": "grid_1", "asset_type": "grid",
                    "import_max_kw": 20, "export_max_kw": 20,
                    "price_buy": [0.3, 0.1, 0.3, 0.1], "price_sell": [0.05] * 4,
                },
            ],
        }
        r_no_deg = client.post("/dispatch/multi-asset?batt_degradation_cost=0.0", json=config)
        r_high_deg = client.post("/dispatch/multi-asset?batt_degradation_cost=5.0", json=config)
        assert r_no_deg.status_code == 200 and r_high_deg.status_code == 200
        # A very high degradation cost should discourage cycling relative to zero cost,
        # so total cost should be no lower with the high degradation cost applied.
        assert r_high_deg.json()["results"]["objective"] >= r_no_deg.json()["results"]["objective"]


class TestBatchEndpoint:
    def test_batch_dispatch_two_customers(self):
        payload = {
            "customers": [
                {
                    "customer_id": "a",
                    "time_periods": 4,
                    "assets": [
                        {
                            "asset_id": "grid_1", "asset_type": "grid",
                            "import_max_kw": 10, "export_max_kw": 10,
                            "price_buy": [0.3] * 4, "price_sell": [0.05] * 4,
                        },
                        {"asset_id": "fixed_1", "asset_type": "fixed_load", "fixed_load_profile_kw": [1] * 4},
                    ],
                },
                {
                    "customer_id": "b",
                    "time_periods": 4,
                    "assets": [
                        {
                            "asset_id": "grid_1", "asset_type": "grid",
                            "import_max_kw": 10, "export_max_kw": 10,
                            "price_buy": [0.2, 0.4, 0.2, 0.4], "price_sell": [0.05] * 4,
                        },
                        {"asset_id": "fixed_1", "asset_type": "fixed_load", "fixed_load_profile_kw": [2] * 4},
                    ],
                },
            ]
        }
        r = client.post("/dispatch/batch", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["overall_status"]["successful_customers"] == 2
        assert set(body["results"].keys()) == {"a", "b"}
