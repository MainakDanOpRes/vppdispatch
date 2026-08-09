"""
Pydantic schemas for VPP Dispatch API
"""


from typing import Annotated, List, Optional, Tuple
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator, ValidationInfo

from .timeseries import CustomerTimeSeries

class AssetType(str, Enum):
    """Types of assets supported in the VPP."""
    PV = "pv"
    BATTERY = "battery"
    FLEX_LOAD = "flex_load"
    FIXED_LOAD = "fixed_load"
    GRID = "grid"

class AssetConfig(BaseModel):
    """configuration for a single asset"""
    asset_id: str = Field(..., description="Unique identified for the asset")
    asset_type: AssetType = Field(..., description="Type of the asset")

    objective_weight: Optional[float] = Field(
        default=1.0,
        description="Weight for this asset's specific objective. Set to 0 to disable."
    )

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
    p_charge_min_kw: Optional[float] = Field(
        default=None,
        description="Maximum charge power in kW",
        ge=0.0
    )
    p_discharge_min_kw: Optional[float] = Field(
        default=None,
        description="Maximum discharge power in kW",
        ge=0
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
    degradation_cost_per_kwh: Optional[float] = Field(
        default=0.0,
        description="Cost per kWh of battery degradation (applied to charge and discharge volume)",
        ge=0.0
    )

    # Flex load-specific
    # NOTE: is_continuous / is_shiftable / is_on_off / load_profile were already
    # referenced by services/asset_factory.py (asset_config.is_continuous, etc.)
    # but were never declared on this schema, so creating any FLEX_LOAD asset via
    # the API would raise AttributeError. Declaring them here fixes that.
    is_continuous: Optional[bool] = Field(
        default=True,
        description=(
            "Continuous flexible load mode: power can vary between p_min_kw and p_max_kw. "
            "Leave unset to auto-select: continuous unless is_shiftable or is_on_off is True."
        )
    )
    is_shiftable: Optional[bool] = Field(
        default=False,
        description="Shiftable load mode: a fixed load_profile is shifted to start at the cheapest time"
    )
    is_on_off: Optional[bool] = Field(
        default=False,
        description="On/off flexible load mode: draws a fixed p_on_kw once when turned on"
    )
    load_profile: Optional[List[float]] = Field(
        default=None,
        description="Fixed power profile (kW) to shift in time, required when is_shiftable is True"
    )
    p_on_kw: Optional[float] = Field(
        default=None,
        description="Power consumption when turned on in kW",
        ge=0.1
    )
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
    discomfort_cost_per_kwh: Optional[float] = Field(
        default=0.0,
        description="Penalty cost per kWh for shifting/delaying the flexible load"
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

    curtailment_cost_per_kwh: Optional[float] = Field(
        default=0.0,
        description="Penalty cost per kWh for curtailing the controllable fixed load"
    )

    # GRID specific
    import_max_kw: Optional[float] = Field(
        default=None,
        description="import power in kw",
        ge=0.1
    )
    export_max_kw: Optional[float] = Field(
            default=None,
            description="export power in kw",
            ge=0.1
        )
    
    price_buy: Optional[List[float]] = Field(
        default=None,
        description="Electricity buy prices for the grid asset"
    )
    price_sell: Optional[List[float]] = Field(
        default=None,
        description="Electricity sell prices for the grid asset"
    )


    # ============================================================================
    # Validation: Ensure required parameters for each asset type are provided
    #
    # NOTE: these were previously per-field `@field_validator`s that inspected
    # `info.data` for *other* fields (e.g. capacity_kwh's validator checking
    # p_charge_max_kw). In Pydantic v2, field validators run in declaration
    # order and `info.data` only contains fields validated so far, so a field
    # declared earlier in the class could never see a field declared later -
    # valid configs were being rejected. A single model-level validator that
    # runs after all fields are populated avoids that ordering trap.
    # ============================================================================
    @model_validator(mode='after')
    def validate_required_fields_for_asset_type(self):
        if self.asset_type == AssetType.PV:
            if self.pv_profile_kw is None:
                raise ValueError("pv_profile_kw is required for PV assets")

        elif self.asset_type == AssetType.BATTERY:
            if self.capacity_kwh is None:
                raise ValueError("capacity_kwh is required for Battery assets")
            if self.p_charge_max_kw is None:
                raise ValueError("p_charge_max_kw is required for Battery assets")
            if self.p_discharge_max_kw is None:
                raise ValueError("p_discharge_max_kw is required for Battery assets")

        elif self.asset_type == AssetType.FLEX_LOAD:
            if self.is_shiftable:
                if not self.load_profile:
                    raise ValueError("load_profile is required for shiftable Flex Load assets")
            elif self.is_on_off:
                if self.p_on_kw is None:
                    raise ValueError("p_on_kw is required for on/off Flex Load assets")
                if self.energy_required_kwh is None:
                    raise ValueError("energy_required_kwh is required for on/off Flex Load assets")
            else:  # continuous (default)
                if self.p_min_kw is None:
                    raise ValueError("p_min_kw is required for Flex Load assets")
                if self.p_max_kw is None:
                    raise ValueError("p_max_kw is required for Flex Load assets")
                if self.energy_required_kwh is None:
                    raise ValueError("energy_required_kwh is required for Flex Load assets")

        elif self.asset_type == AssetType.FIXED_LOAD:
            if self.fixed_load_profile_kw is None:
                raise ValueError("fixed_load_profile_kw is required for Fixed Load assets")

        # NOTE: Grid assets intentionally have no required-field check here.
        # asset_factory.py defaults price_buy/price_sell to [] when omitted, and
        # dispatch_service.run_multi_asset_dispatch() backfills them from the
        # customer-level price_buy/price_sell if still empty - so a Grid asset
        # config with no prices of its own is valid, not an error.

        return self


class CustomerConfig(BaseModel):
    """Configuration for a single customer with multiple assets."""
    customer_id: str = Field(...,min_length=1, description="Unique identifier for the customer")
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

    @field_validator('customer_id')
    @classmethod
    def validate_customer_id_not_blank(cls, v):
        if not v or not v.strip():
            raise ValueError("customer_id cannot be empty or whitespace")
        return v

    @field_validator('assets')
    @classmethod
    def validate_unique_asset_ids(cls, v, info: ValidationInfo):
        """Ensure all asset IDs are unique."""
        asset_ids = [asset.asset_id for asset in v]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("Asset IDs must be unique within a customer")
        return v
    
    @field_validator('pv_kw', 'fixed_load_kw', 'price_buy', 'price_sell')
    @classmethod
    def validate_time_series_length(cls, v, info: ValidationInfo):
        """Ensure all time series have the same length as time_periods."""
        if v is not None and info.data.get('time_periods') is not None:
            if len(v) != info.data['time_periods']:
                raise ValueError(
                    f"{info.field_name} length ({len(v)}) must match time_periods ({info.data['time_periods']})"
                )
        return v




class LiveCustomerInput(BaseModel):
    """Legacy input schema for backward compatibility."""
    customer_id: str = Field(...,min_length=1, description="Customer identifier")
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