from ..models.assets import PVAsset, BatteryAsset, FlexLoadAsset, FixedLoadAsset, GridAsset
from ..models.schemas import AssetConfig, AssetType
import logging
logger = logging.getLogger(__name__)


def create_asset_from_config(customer_id: str, asset_config: AssetConfig) -> any:
    """Create an asset object from configuration."""
    try:
        if asset_config.asset_type == AssetType.PV:
            return PVAsset(
                customer_id=customer_id,
                asset_id=asset_config.asset_id,
                pv_profile_kw=asset_config.pv_profile_kw or [],
                objective_weight=asset_config.objective_weight or 1.0
            )

        elif asset_config.asset_type == AssetType.BATTERY:
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
                soc_initial=asset_config.soc_initial or 5.0,
                degradation_cost_per_kwh=asset_config.degradation_cost_per_kwh or 0.0,
                objective_weight=asset_config.objective_weight or 1.0
            )

        elif asset_config.asset_type == AssetType.FLEX_LOAD:
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
                discomfort_cost_per_kwh = asset_config.discomfort_cost_per_kwh or 0.0,
                objective_weight=asset_config.objective_weight or 1.0
            )

        elif asset_config.asset_type == AssetType.FIXED_LOAD:
            return FixedLoadAsset(
                customer_id=customer_id,
                asset_id=asset_config.asset_id,
                fixed_load_profile_kw=asset_config.fixed_load_profile_kw or [],
                is_controllable=asset_config.is_controllable or False,
                priority=asset_config.priority or 1,
                operational_hours=asset_config.operational_hours,
                objective_weight=asset_config.objective_weight or 1.0,
                curtailment_cost_per_kwh = asset_config.curtailment_cost_per_kwh or 0.0
            )

        elif asset_config.asset_type == AssetType.GRID:
            return GridAsset(
                customer_id=customer_id,
                asset_id=asset_config.asset_id,
                import_max_kw=asset_config.import_max_kw,
                export_max_kw=asset_config.export_max_kw,
                price_buy=asset_config.price_buy,
                price_sell=asset_config.price_sell,
                objective_weight=asset_config.objective_weight or 1.0
            )

        else:
            logger.warning(f"Unknown asset type: {asset_config.asset_type}")
            return None

    except Exception as e:
        logger.error(f"Error creating asset {asset_config.asset_id}: {e}")
        return None


