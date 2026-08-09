import pytest
from src.vpp_dispatch.models.timeseries import CustomerTimeSeries
from src.vpp_dispatch.models.schemas import CustomerConfig, AssetConfig, AssetType
from src.vpp_dispatch.services.dispatch_service import run_multi_asset_dispatch

@pytest.mark.requires_solver
class TestFullOptimizationSimple:
    """Integration tests that require actual solver."""
    def setup_method(self):
        self.time_period = 12
        self.customer_id = "C1"
        self.pv_kw = [0.0, 1.0, 2.0, 3.0, 2.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.fixed_load_kw=[1.0] * 12
        self.price_buy=[0.2] * 12
        self.price_sell=[0.1] * 12
    def test_simple_optimization(self):
        """Test simple optimization with one of each asset type."""
        config = CustomerConfig(
            customer_id = self.customer_id,
            time_periods = self.time_period,
            assets=[
                AssetConfig(
                    asset_id="pv_1",
                    asset_type=AssetType.PV,
                    pv_profile_kw = self.pv_kw
                ),
                AssetConfig(
                    asset_id="battery_1",
                    asset_type=AssetType.BATTERY,
                    capacity_kwh=10.0,
                    p_charge_max_kw=5.0,
                    p_discharge_max_kw=5.0
                ),
                AssetConfig(
                    asset_id="fixed_1",
                    asset_type=AssetType.FIXED_LOAD,
                    fixed_load_profile_kw=self.fixed_load_kw
                ),
                AssetConfig(
                    asset_id="grid_1",
                    asset_type=AssetType.GRID,
                    import_max_kw=50.0,
                    export_max_kw=50.0,
                    price_buy=self.price_buy,
                    price_sell = self.price_sell
                )
            ]
        )

        results, status = run_multi_asset_dispatch(config)
        assert status["success"] is True
        assert "p_grid" in results
        assert "assets" in results
        assert "pv_1" in results["assets"]
        assert "battery_1" in results["assets"]
        assert "objective" in results
        assert len(results["p_grid"]) == 12

class TestFullOptimizationMultiplePV:
    """Test optimization with multiple PV assets."""
    def setup_method(self):
        self.time_period = 12
        self.customer_id = "C2"
        self.pv_kw_1 = [0.0, 1.0, 2.0, 3.0, 2.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.pv_kw_2 = [0.0, 0.5, 1.0, 1.5, 1.0, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        self.fixed_load_kw=[1.0] * 12
        self.price_buy=[0.2] * 12
        self.price_sell=[0.1] * 12

    def test_simple_optimization(self):
        """Test simple optimization with one of each asset type."""
        config = CustomerConfig(
            customer_id = self.customer_id,
            time_periods = self.time_period,
            assets=[
                AssetConfig(
                    asset_id="pv_roof",
                    asset_type=AssetType.PV,
                    pv_profile_kw = self.pv_kw_1
                ),
                AssetConfig(
                    asset_id="pv_ground",
                    asset_type=AssetType.PV,
                    pv_profile_kw = self.pv_kw_2
                ),
                AssetConfig(
                    asset_id="battery_1",
                    asset_type=AssetType.BATTERY,
                    capacity_kwh=10.0,
                    p_charge_max_kw=5.0,
                    p_discharge_max_kw=5.0
                ),
                AssetConfig(
                    asset_id="fixed_1",
                    asset_type=AssetType.FIXED_LOAD,
                    fixed_load_profile_kw=self.fixed_load_kw
                ),
                AssetConfig(
                    asset_id="grid_1",
                    asset_type=AssetType.GRID,
                    import_max_kw=50.0,
                    export_max_kw=50.0,
                    price_buy=self.price_buy,
                    price_sell = self.price_sell
                )
            ]
        )

        results, status = run_multi_asset_dispatch(config)
        assert status["success"] is True
        assert "pv_roof" in results["assets"]
        assert "pv_ground" in results["assets"]

class TestFullOptimizationMultipleBatteryAsset:
    """Test optimization with multiple battery assets."""
    def setup_method(self):
        self.time_period = 12
        self.customer_id = "C3"
        self.pv_kw = [2.0] * 12
        self.fixed_load_kw=[1.0] * 12
        self.price_buy=[0.2] * 12
        self.price_sell=[0.1] * 12

    def test_multiple_batteries(self):
        config = CustomerConfig(
            customer_id = self.customer_id,
            time_periods = self.time_period,
            assets=[
                AssetConfig(
                    asset_id="pv_roof",
                    asset_type=AssetType.PV,
                    pv_profile_kw = self.pv_kw
                ),
                AssetConfig(
                    asset_id="battery_home",
                    asset_type=AssetType.BATTERY,
                    capacity_kwh=10.0,
                    p_charge_max_kw=5.0,
                    p_discharge_max_kw=5.0
                ),
                AssetConfig(
                    asset_id="battery_garage",
                    asset_type=AssetType.BATTERY,
                    capacity_kwh=5.0,
                    p_charge_max_kw=3.0,
                    p_discharge_max_kw=3.0
                ),
                AssetConfig(
                    asset_id="fixed_1",
                    asset_type=AssetType.FIXED_LOAD,
                    fixed_load_profile_kw=self.fixed_load_kw
                ),
                AssetConfig(
                    asset_id="grid_1",
                    asset_type=AssetType.GRID,
                    import_max_kw=50.0,
                    export_max_kw=50.0,
                    price_buy=self.price_buy,
                    price_sell = self.price_sell
                )
            ]
        )

        results, status = run_multi_asset_dispatch(config)
        assert status["success"] is True
        assert "pv_roof" in results["assets"]
        assert "battery_home" in results["assets"]
        assert "battery_garage" in results["assets"]