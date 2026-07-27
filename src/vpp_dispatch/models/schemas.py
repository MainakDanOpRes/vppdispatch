"""
Pydantic schemas for VPP Dispatch API
"""


from typing import Annotated, List, Optional, Tuple
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from .timeseries import CustomerTimeSeries

class AssetType(str, Enum):
    """Types of assets supported in the VPP."""
    PV = "pv"
    BATTERY = "battery"
    FLEX_LOAD = "flex_load"
    FIXED_LOAD = "fixed_load"

class AssetConfig(BaseModel):
    """configuration for a single asset"""
    asset_id: str = Field(..., description="Unique identified for the asset")
    asset_type: AssetType = Field(..., description="Type of the asset")

    # PV-specific
    pv_profile_kw: Optional[List[float]] = Field(
        default=None,
        description="PV generation profile in kW for each time period"
    )

    # Battery-specific
    capacity_kwh: Optional[float] = Field(
        default=None,
        description="Battery capacity in kWh",
        ge=0.1
    )
    p_charge_max_kw: Optional[float] = Field(
        default=None,
        description="Maximum charge power in kW",
        ge=0.1
    )
    p_discharge_max_kw: Optional[float] = Field(
        default=None,
        description="Maximum discharge power in kW",
        ge=0.1
    )
    soc_min: Optional[float] = Field(
        default=None,
        description="Minimum state of charge (fraction of capacity)",
        ge=0.0, le=1.0
    )
    soc_max: Optional[float] = Field(
        default=None,
        description="Maximum state of charge (fraction of capacity)",
        ge=0.0, le=1.0
    )
    eff_charge: Optional[float] = Field(
        default=None,
        description="Charge efficiency (0-1)",
        ge=0.5, le=1.0
    )
    eff_discharge: Optional[float] = Field(
        default=None,
        description="Discharge efficiency (0-1)",
        ge=0.5, le=1.0
    )
    soc_initial: Optional[float] = Field(
        default=None,
        description="Initial state of charge in kWh",
        ge=0.0
    )

    # Flex load-specific
    name: Optional[str] = Field(
        default=None,
        description="Human-readable name for the flexible load"
    )
    p_min_kw: Optional[float] = Field(
        default=None,
        description="Minimum power consumption in kW",
        ge=0.0
    )
    p_max_kw: Optional[float] = Field(
        default=None,
        description="Maximum power consumption in kW",
        ge=0.1
    )
    energy_required_kwh: Optional[float] = Field(
        default=None,
        description="Total energy required in kWh over the time period",
        ge=0.1
    )
    time_window: Optional[Tuple[int, int]] = Field(
        default=None,
        description="Time window (start, end) during which the load can operate"
    )

    # Fixed load-specific
    fixed_load_profile_kw: Optional[List[float]] = Field(
        default=None,
        description="Fixed load consumption profile in kW for each time period"
    )
    is_controllable: Optional[bool] = Field(
        default=None,
        description="Whether the fixed load can be controlled (turned on/off)"
    )
    priority: Optional[int] = Field(
        default=None,
        description="Priority level (higher = more critical, must be served first)",
        ge=1, le=10
    )
    operational_hours: Optional[Tuple[int, int]] = Field(
        default=None,
        description="Hours during which the fixed load operates (start, end)"
    )


    # ============================================================================
    # Validation: Ensure required parameters for each asset type are provided
    # ============================================================================
    @field_validator('pv_profile_kw')
    def validate_pv_params(cls, v, values):
        if values.get('asset_type') == AssetType.PV and v is None:
            raise ValueError("pv_profile_kw is required for PV assets")
        return v

    @field_validator('capacity_kwh')
    def validate_battery_params(cls, v, values):
        if values.get('asset_type') == AssetType.BATTERY and v is None:
            raise ValueError("capacity_kwh is required for Battery assets")
        if values.get('asset_type') == AssetType.BATTERY:
            if values.get('p_charge_max_kw') is None:
                raise ValueError("p_charge_max_kw is required for Battery assets")
            if values.get('p_discharge_max_kw') is None:
                raise ValueError("p_discharge_max_kw is required for Battery assets")
        return v

    @field_validator('p_min_kw', 'p_max_kw', 'energy_required_kwh')
    def validate_flex_load_params(cls, v, values, field):
        if values.get('asset_type') == AssetType.FLEX_LOAD:
            if field.name == 'p_min_kw' and v is None:
                raise ValueError("p_min_kw is required for Flex Load assets")
            if field.name == 'p_max_kw' and v is None:
                raise ValueError("p_max_kw is required for Flex Load assets")
            if field.name == 'energy_required_kwh' and v is None:
                raise ValueError("energy_required_kwh is required for Flex Load assets")
        return v

    @field_validator('fixed_load_profile_kw')
    def validate_fixed_load_params(cls, v, values):
        if values.get('asset_type') == AssetType.FIXED_LOAD and v is None:
            raise ValueError("fixed_load_profile_kw is required for Fixed Load assets")
        return v


class CustomerConfig(BaseModel):
    """Configuration for a single customer with multiple assets."""
    customer_id: str = Field(..., description="Unique identifier for the customer")
    assets: List[AssetConfig] = Field(..., description="List of assets for this customer")
    time_periods: int = Field(..., gt=0, description="Number of time periods")

    # Time series data (can be overridden by asset-specific profiles)
    pv_kw: Optional[List[float]] = Field(
        default=None,
        description="Default PV generation profile (used if asset doesn't specify)"
    )
    fixed_load_kw: Optional[List[float]] = Field(
        default=None,
        description="Default fixed load profile (used if asset doesn't specify)"
    )
    price_buy: Optional[List[float]] = Field(
        default=None,
        description="Electricity buy prices"
    )
    price_sell: Optional[List[float]] = Field(
        default=None,
        description="Electricity sell prices"
    )

    @field_validator('assets')
    def validate_unique_asset_ids(cls, v):
        """Ensure all asset IDs are unique."""
        asset_ids = [asset.asset_id for asset in v]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("Asset IDs must be unique within a customer")
        return v
    
    @field_validator('pv_kw', 'fixed_load_kw', 'price_buy', 'price_sell')
    def validate_time_series_length(cls, v, values, field):
        """Ensure all time series have the same length as time_periods."""
        if v is not None and values.get('time_periods') is not None:
            if len(v) != values['time_periods']:
                raise ValueError(
                    f"{field.name} length ({len(v)}) must match time_periods ({values['time_periods']})"
                )
        return v




class LiveCustomerInput(BaseModel):
    """Legacy input schema for backward compatibility."""
    customer_id: str = Field(..., description="Customer identifier")
    pv_kw: Annotated[List[float], Field(min_length=1, description="PV generation profile")]
    fixed_load_kw: Annotated[List[float], Field(min_length=1, description="Fixed load profile")]
    price_buy: Annotated[List[float], Field(min_length=1, description="Buy price profile")]
    price_sell: Annotated[List[float], Field(min_length=1, description="Sell price profile")]

    def to_timeseries(self):
        return CustomerTimeSeries(
            pv_kw=self.pv_kw,
            fixed_load_kw=self.fixed_load_kw,
            price_buy=self.price_buy,
            price_sell=self.price_sell,
        )

class BatchDispatchInput(BaseModel):
    """Input schema for batch dispatch."""
    customers: List[LiveCustomerInput] = Field(..., description="List of customer configurations")