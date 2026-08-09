import pytest
from pydantic import ValidationError
from src.vpp_dispatch.models.schemas import AssetConfig, AssetType
from src.vpp_dispatch.services.asset_factory import create_asset_from_config, create_assets_from_configs

class TestAssetFactory:
    """Test suite for asset factory."""

    def test_create_pv_asset(self):
        """Test creating PV asset from config"""
        config = AssetConfig(
            asset_id = "pv_test",
            asset_type = AssetType.PV,
            pv_profile_kw = [1.0, 2.0, 3.0]
        )
        asset = create_asset_from_config(customer_id="c1",
                                         asset_config=config)
        assert asset is not None
        assert asset.__class__.__name__ == "PVAsset"
        assert asset.asset_id == "pv_test"
        assert asset.var_id == "c1_pv_test"
        assert asset.pv_profile_kw == [1.0, 2.0, 3.0]

    def test_create_battery_asset(self):
        """Test creating battery asset from config."""
        config = AssetConfig(
            asset_id="batt_test",
            asset_type=AssetType.BATTERY,
            capacity_kwh=20.0,
            p_charge_max_kw=10.0,
            p_discharge_max_kw=8.0
        )
        asset = create_asset_from_config("cust1", config)
        assert asset is not None
        assert asset.__class__.__name__ == "BatteryAsset"
        assert asset.capacity_kwh == 20.0

    def test_create_flex_load_asset(self):
        """Test creating flex load asset from config."""
        config = AssetConfig(
            asset_id="flex_test",
            asset_type=AssetType.FLEX_LOAD,
            name="Test Load",
            p_min_kw=0.0,
            p_max_kw=5.0,
            energy_required_kwh=10.0,
            time_window=(5, 15)
        )
        asset = create_asset_from_config("cust1", config)
        assert asset is not None
        assert asset.__class__.__name__ == "FlexLoadAsset"
        assert asset.name == "Test Load"

    def test_create_multiple_assets(self):
        """Test creating multiple assets from configs."""
        configs = [
            AssetConfig(asset_id="pv_1", asset_type=AssetType.PV, pv_profile_kw=[1, 2, 3]),
            AssetConfig(asset_id="batt_1", asset_type=AssetType.BATTERY, capacity_kwh=10.0,
                        p_charge_max_kw=5.0, p_discharge_max_kw=5.0),
            AssetConfig(asset_id="flex_1", asset_type=AssetType.FLEX_LOAD, 
                        is_continuous=True,is_on_off=False,
                        is_shiftable=False, p_min_kw=0.0,p_max_kw=7.0,
                        energy_required_kwh=14.0, time_window=(10, 20))
        ]
        assets = create_assets_from_configs("cust1", configs)
        assert len(assets) == 3
        assert assets[0].__class__.__name__ == "PVAsset"
        assert assets[1].__class__.__name__ == "BatteryAsset"
        assert assets[2].__class__.__name__ == "FlexLoadAsset"

    def test_invalid_asset_type(self):
        """Test handling of invalid asset type."""
        with pytest.raises(ValidationError):
            asset = create_asset_from_config("cust1", AssetConfig(
                asset_id="invalid",
                asset_type="invalid_type"
            ))

    def test_missing_required_fields(self):
        """Test handling of missing required fields."""
        with pytest.raises(ValidationError):
            asset = create_asset_from_config("cust1", AssetConfig(
                asset_id="batt_missing",
                asset_type=AssetType.BATTERY
                # Missing capacity_kwh, etc.
            ))
