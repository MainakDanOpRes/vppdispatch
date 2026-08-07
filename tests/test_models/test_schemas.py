"""Tests for Pydantic schemas."""

import pytest
from pydantic import ValidationError
from src.vpp_dispatch.models.schemas import (
    AssetConfig, AssetType, CustomerConfig, LiveCustomerInput, BatchDispatchInput
)

class TestAssetConfig:
    """Tests for AssetConfig schema."""
    def test_pv_asset_config(self):
        """Test PV asset configuration validation."""
        config = AssetConfig(
            asset_id="pv_1",
            asset_type=AssetType.PV,
            pv_profile_kw=[1.0, 2.0, 3.0]
        )
        assert config.asset_id == "pv_1"
        assert config.asset_type == AssetType.PV

    def test_battery_asset_config(self):
        """Test battery asset configuration validation."""
        config = AssetConfig(
            asset_id="batt_1",
            asset_type=AssetType.BATTERY,
            capacity_kwh=10.0,
            p_charge_max_kw=5.0,
            p_discharge_max_kw=5.0
        )
        assert config.capacity_kwh == 10.0
    def test_invalid_asset_type(self):
        """Test invalid asset type raises error."""
        with pytest.raises(ValidationError):
            AssetConfig(
                asset_id="test",
                asset_type="invalid_type"
            )

    def test_negative_capacity(self):
        """Test negative capacity raises error."""
        with pytest.raises(ValidationError):
            AssetConfig(
                asset_id="batt_1",
                asset_type=AssetType.BATTERY,
                capacity_kwh=-5.0
            )

    def test_soc_out_of_range(self):
        """Test SOC out of range raises error."""
        with pytest.raises(ValidationError):
            AssetConfig(
                asset_id="batt_1",
                asset_type=AssetType.BATTERY,
                capacity_kwh=10.0,
                soc_min=1.5  # > 1
            )