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

    def test_time_window_invalid(self):
        """Test invalid time window raises error"""
        with pytest.raises(ValidationError):
            AssetConfig(
                asset_id="flex_1",
                asset_type=AssetType.FLEX_LOAD,
                time_window=(25, 30)
            )

class TestCustomerConfig:
    """Tests for CustomerConfig schema."""

    def test_valid_customer_config(self):
        """Test Valid customer configuration."""
        config = CustomerConfig(
            customer_id="cust1",
            time_periods=24,
            assets=[]
        )
        assert config.customer_id == "cust1"
        assert config.time_periods == 24

    def test_time_series_length_mismatch(self):
        """Test time series length validation."""
        with pytest.raises(ValidationError):
            CustomerConfig(
                customer_id="cust1",
                time_period=24,
                pv_kw=[1.0, 2.0],
                fixed_load_kw=[1.0] * 24,
                price_buy=[0.2] * 24,
                price_sell=[0.1] * 24,
                assets=[]
            )

    def test_empty_customer_id(self):
        """Test empty customer ID raises error."""
        with pytest.raises(ValidationError):
            CustomerConfig(
                customer_id="",
                time_periods=24,
                assets=[]
            )

    def test_customer_asset_unique_id(self):
        """Test non-unique asset-ids of a customer raises error"""
        pv_1 = AssetConfig(
            asset_id="asset_1",
            asset_type=AssetType.PV,
            pv_profile_kw=[1.0] * 24
            )

        pv_2 = AssetConfig(
            asset_id="asset_1",
            asset_type=AssetType.PV,
            pv_profile_kw=[1.0] * 24
            )

        with pytest.raises(ValidationError):
            CustomerConfig(
                customer_id="customer_1",
                time_periods=24,
                assets=[pv_1, pv_2]
            )



class TestLiveCustomerInput:
    """Tests for legacy LiveCustomerInput schema."""

    def test_valid_input(self):
        """Test valid live customer input."""
        input_data = LiveCustomerInput(
            customer_id="cust1",
            pv_kw=[1.0, 2.0, 3.0],
            fixed_load_kw=[1.0, 1.0, 1.0],
            price_buy=[0.2, 0.2, 0.2],
            price_sell=[0.1, 0.1, 0.1]
        )
        assert input_data.customer_id == "cust1"

    def test_to_timeseries(self, simple_timeseries):
        """Test conversion to time series."""
        input_data = LiveCustomerInput(
            customer_id="cust1",
            pv_kw=simple_timeseries.pv_kw,
            fixed_load_kw=simple_timeseries.fixed_load_kw,
            price_buy=simple_timeseries.price_buy,
            price_sell=simple_timeseries.price_sell
        )
        ts = input_data.to_timeseries()
        assert ts.T == len(simple_timeseries.pv_kw)

    def test_empty_lists(self):
        """Test empty lists raise error."""
        with pytest.raises(ValidationError):
            LiveCustomerInput(
                customer_id="cust1",
                pv_kw=[],
                fixed_load_kw=[],
                price_buy=[],
                price_sell=[]
            )