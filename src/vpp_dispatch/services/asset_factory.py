"""
Asset Factory for VPP Dispatch
Creates asset instances from configuration with full support for all asset types.
"""

from typing import List, Optional, Union, Tuple
import logging

from ..models.assets import (
    PVAsset, BatteryAsset, FlexLoadAsset,
    FixedLoadAsset, GridAsset, BaseAsset
)
from ..models.schemas import AssetConfig, AssetType

logger = logging.getLogger(__name__)

def create_asset_from_config(
    customer_id: str,
    asset_config: Union[AssetConfig, dict]
) -> Optional[BaseAsset]:
    """
    Create an asset object from configuration.

    Supports both AssetConfig objects and raw dictionaries for flexibility.

    Args:
        customer_id: Customer identifier
        asset_config: AssetConfig object or dictionary with asset parameters

    Returns:
        Asset instance (PVAsset, BatteryAsset, FlexLoadAsset, FixedLoadAsset, or GridAsset)
        or None if creation fails
    """
    if isinstance(asset_config, dict) and not isinstance(asset_config, AssetConfig):
        try:
            asset_config = AssetConfig(**asset_config)
        except Exception as e:
            logger.error(f"Failed to convert dict to AssetConfig: {e}")
            return None

    try:
        if hasattr(asset_config, 'time_window') and asset_config.time_window:
            if isinstance(asset_config.time_window, list):
                asset_config.time_window = tuple(asset_config.time_window)

        if hasattr(asset_config, 'operational_hours') and asset_config.operational_hours:
            if isinstance(asset_config.operational_hours, list):
                asset_config.operational_hours = tuple(asset_config.operational_hours)

        asset_type = asset_config.asset_type

        if asset_type == AssetType.PV:
            return PVAsset(
                customer_id=customer_id,
                asset_id=asset_config.asset_id,
                pv_profile_kw=asset_config.pv_profile_kw or [],
                objective_weight=asset_config.objective_weight or 1.0
            )

        elif asset_type == AssetType.BATTERY:
            return BatteryAsset(
                customer_id=customer_id,
                asset_id=asset_config.asset_id,
                capacity_kwh=asset_config.capacity_kwh or 10.0,
                p_charge_max_kw=asset_config.p_charge_max_kw or 5.0,
                p_discharge_max_kw=asset_config.p_discharge_max_kw or 5.0,
                soc_min=asset_config.soc_min or 0.1,
                soc_max=asset_config.soc_max or 0.9,
                eff_charge=asset_config.eff_charge or 0.95,
                eff_discharge=asset_config.eff_discharge or 0.95,
                soc_initial=asset_config.soc_initial or None,
                degradation_cost_per_kwh=asset_config.degradation_cost_per_kwh or 0.0,
                objective_weight=asset_config.objective_weight or 1.0
            )

        elif asset_type == AssetType.FLEX_LOAD:
            return FlexLoadAsset(
                customer_id=customer_id,
                asset_id=asset_config.asset_id,
                name=asset_config.name or "FlexLoad",
                is_continuous=asset_config.is_continuous or True,
                is_on_off=asset_config.is_on_off or False,
                is_shiftable=asset_config.is_shiftable or False,
                p_min_kw=asset_config.p_min_kw or 0.0,
                p_max_kw=asset_config.p_max_kw or 7.0,
                p_on_kw=asset_config.p_on_kw or 5.0,
                energy_required_kwh=asset_config.energy_required_kwh or 14.0,
                load_profile=asset_config.load_profile or None,
                time_window=asset_config.time_window or (0, 23),
                discomfort_cost=asset_config.discomfort_cost_per_kwh or 0.0,
                objective_weight=asset_config.objective_weight or 1.0
            )

        elif asset_type == AssetType.FIXED_LOAD:
            return FixedLoadAsset(
                customer_id=customer_id,
                asset_id=asset_config.asset_id,
                fixed_load_profile_kw=asset_config.fixed_load_profile_kw or [],
                is_controllable=asset_config.is_controllable or False,
                priority=asset_config.priority or 1,
                operational_hours=asset_config.operational_hours,
                curtailment_cost_per_kwh=asset_config.curtailment_cost_per_kwh or 0.0,
                objective_weight=asset_config.objective_weight or 1.0
            )

        elif asset_type == AssetType.GRID:
            return GridAsset(
                customer_id=customer_id,
                asset_id=asset_config.asset_id,
                import_max_kw=asset_config.import_max_kw or 100.0,
                export_max_kw=asset_config.export_max_kw or 100.0,
                price_buy=asset_config.price_buy or [],
                price_sell=asset_config.price_sell or [],
                objective_weight=asset_config.objective_weight or 1.0
            )

        else:
            logger.warning(f"Unknown asset type: {asset_type}")
            return None

    except Exception as e:
        logger.error(f"Error creating asset {getattr(asset_config, 'asset_id', 'unknown')}: {e}")
        return None

def create_assets_from_configs(
    customer_id: str,
    asset_configs: List[Union[AssetConfig, dict]]
) -> List[BaseAsset]:
    """
    Create multiple assets from a list of configurations.
    """
    assets = []
    for i, config in enumerate(asset_configs):
        asset = create_asset_from_config(customer_id, config)
        if asset:
            logger.debug(f"Created asset {i+1}/{len(asset_configs)}: {asset.__class__.__name__} ({asset.asset_id})")
            assets.append(asset)
        else:
            logger.warning(f"Failed to create asset from config {i+1}")
    logger.info(f"Created {len(assets)} out of {len(asset_configs)} assets")
    return assets

def get_asset_by_id(assets: List[BaseAsset], asset_id: str) -> Optional[BaseAsset]:
    for asset in assets:
        if asset.asset_id == asset_id:
            return asset
    return None

def get_assets_by_type(assets: List[BaseAsset], asset_type: type) -> List[BaseAsset]:
    return [a for a in assets if isinstance(a, asset_type)]

def validate_asset_configs(asset_configs: List[Union[AssetConfig, dict]]) -> Tuple[bool, List[str]]:
    errors = []
    for i, config in enumerate(asset_configs):
        try:
            if isinstance(config, dict):
                AssetConfig(**config)
        except Exception as e:
            errors.append(f"Asset {i}: {str(e)}")
    return len(errors) == 0, errors