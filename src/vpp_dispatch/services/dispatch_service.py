"""
Dispatch Service for VPP Optimization
Handles single and multi-asset dispatch with dynamic asset configuration.
"""

from typing import Dict, Any, List, Optional, Tuple
from pyomo.environ import value
import logging
from datetime import datetime

from ..models.timeseries import CustomerTimeSeries
from ..models.schemas import CustomerConfig, AssetConfig, AssetType
from ..models.assets import PVAsset, BatteryAsset, FlexLoadAsset, FixedLoadAsset
from ..models.constraints.power_balance import PowerBalanceConstraint
from ..models.objectives.cost_minimisation import CostObjective
from ..optimisation.model_builder import ModelBuilder
from ..optimisation.solver_manager import SolverManager
from .asset_factory import create_assets_from_configs

logger = logging.getLogger(__name__)

# ============================================================================
# SINGLE CUSTOMER DISPATCH (Legacy - Backward Compatible)
# ============================================================================

def run_single_customer_dispatch(customer_id: str, ts: CustomerTimeSeries) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Run optimization for a single customer with DEFAULT asset configuration.
    This is the legacy function for backward compatibility.

    Args:
        customer_id: Customer identifier
        ts: Time series data

    Returns:
        Tuple of (results_dict, status_dict)
    """
    T = ts.T
    delta_t = 1.0  # hours

    # Create default assets (backward compatible)
    pv = PVAsset(customer_id=customer_id, asset_id="pv_1", pv_profile_kw=ts.pv_kw)
    battery = BatteryAsset(
        customer_id=customer_id,
        asset_id="battery_1",
        capacity_kwh=10.0,
        p_charge_max_kw=5.0,
        p_discharge_max_kw=5.0,
        soc_min=1.0,
        soc_max=9.0,
        eff_charge=0.95,
        eff_discharge=0.95,
        soc_initial=5.0,
    )
    flex = FlexLoadAsset(
        customer_id=customer_id,
        asset_id="flex_1",
        name="EV",
        p_min_kw=0.0,
        p_max_kw=7.0,
        energy_required_kwh=14.0,
        time_window=(10, 20),
    )

    # Create constraints and objective
    pb = PowerBalanceConstraint(ts_data=ts, assets=[pv, battery, flex])
    obj = CostObjective(batt_degradation_cost_per_kwh=0.01)

    # Build and solve model
    builder = ModelBuilder(assets=[pv, battery, flex], power_balance=pb, objective=obj)
    model = builder.build(T=T, delta_t=delta_t)

    solver = SolverManager(solver_name="highs", time_limit_sec=10)
    model, status = solver.solve(model)

    # Extract results (legacy format)
    results = {
        "p_grid": [model.p_grid[t].value for t in model.T],
        "p_ch": [model.p_ch_battery_1[t].value for t in model.T] if hasattr(model, 'p_ch_battery_1') else [0.0] * T,
        "p_dis": [model.p_dis_battery_1[t].value for t in model.T] if hasattr(model, 'p_dis_battery_1') else [0.0] * T,
        "soc": [model.soc_battery_1[t].value for t in model.T] if hasattr(model, 'soc_battery_1') else [5.0] * T,
        "flex_ev": [model.flex_flex_1[t].value for t in model.T] if hasattr(model, 'flex_flex_1') else [0.0] * T,
        "objective": value(model.total_cost) if hasattr(model, 'total_cost') else 0.0,
    }

    return results, status

# ============================================================================
# MULTI-ASSET DISPATCH 
# ============================================================================

def run_multi_asset_dispatch(
    customer_config: CustomerConfig,
    batt_degradation_cost: float = 0.01
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Run optimization for a customer with CUSTOM asset configuration.
    This is the main dispatch function that supports any number of assets of any type.

    Args:
        customer_config: CustomerConfig with assets and time series data
        batt_degradation_cost: Battery degradation cost per kWh

    Returns:
        Tuple of (results_dict, status_dict)
    """
    start_time = datetime.now()

    try:
        # Create time series from config
        ts = CustomerTimeSeries(
            pv_kw=customer_config.pv_kw or [0.0] * customer_config.time_periods,
            fixed_load_kw=customer_config.fixed_load_kw or [0.0] * customer_config.time_periods,
            price_buy=customer_config.price_buy or [0.2] * customer_config.time_periods,
            price_sell=customer_config.price_sell or [0.1] * customer_config.time_periods,
        )

        T = ts.T
        delta_t = 1.0

        # Create assets from configuration
        assets = create_assets_from_configs(customer_config.customer_id, customer_config.assets)

        if not assets:
            return {}, {'status': 'failed', 'error': 'No valid assets created', 'success': False}

        # Create constraints with asset list (IMPORTANT: pass assets to PowerBalanceConstraint)
        pb = PowerBalanceConstraint(ts_data=ts, assets=assets)
        obj = CostObjective(batt_degradation_cost_per_kwh=batt_degradation_cost)

        # Build and solve model
        builder = ModelBuilder(assets=assets, power_balance=pb, objective=obj)
        model = builder.build(T=T, delta_t=delta_t)

        solver = SolverManager(solver_name="highs", time_limit_sec=30)
        model, status = solver.solve(model)

        if not status.get('success', False):
            return {}, status

        # Extract results for all assets
        results = _extract_results_from_model(model, assets, T)

        # Add metadata
        results['_metadata'] = {
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': (datetime.now() - start_time).total_seconds(),
            'customer_id': customer_config.customer_id,
            'num_assets': len(assets),
            'time_periods': T,
            'status': 'success'
        }

        return results, status

    except Exception as e:
        logger.error(f"Error in multi-asset dispatch: {e}")
        return {}, {'status': 'failed', 'error': str(e), 'success': False}

def _extract_results_from_model(
    model,
    assets: List,
    T: int
) -> Dict[str, Any]:
    """
    Extract results from the solved model for all assets.

    Args:
        model: Solved Pyomo model
        assets: List of asset objects
        T: Number of time periods

    Returns:
        Dictionary with all results
    """
    results = {
        'p_grid': [model.p_grid[t].value for t in model.T],
        'objective': value(model.total_cost) if hasattr(model, 'total_cost') else 0.0,
        'assets': {},
        'time_periods': T
    }

    # Extract results for each asset
    for asset in assets:
        asset_results = asset.get_results(model)
        results['assets'][asset.asset_id] = {
            'type': asset.__class__.__name__,
            'config': asset.to_dict(),
            'results': asset_results
        }

    return results

# ============================================================================
# BATCH DISPATCH
# ============================================================================

def run_batch_dispatch(
    customer_configs: List[CustomerConfig],
    batt_degradation_cost: float = 0.01
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Run optimization for multiple customers.

    Args:
        customer_configs: List of CustomerConfig objects
        batt_degradation_cost: Battery degradation cost per kWh

    Returns:
        Tuple of (batch_results, overall_status)
    """
    batch_results = {}
    total = len(customer_configs)
    successful = 0

    for config in customer_configs:
        try:
            results, status = run_multi_asset_dispatch(config, batt_degradation_cost)
            batch_results[config.customer_id] = {
                'results': results,
                'status': status
            }
            if status.get('success', False):
                successful += 1
        except Exception as e:
            batch_results[config.customer_id] = {
                'results': {},
                'status': {'status': 'failed', 'error': str(e), 'success': False}
            }

    overall_status = {
        'total_customers': total,
        'successful_customers': successful,
        'overall_status': 'success' if successful == total else 'partial_failure' if successful > 0 else 'failed'
    }

    return batch_results, overall_status

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def create_optimization_summary(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a summary of optimization results.

    Args:
        results: Optimization results dictionary

    Returns:
        Summary dictionary with key metrics
    """
    summary = {
        'total_cost': results.get('objective', 0.0),
        'time_periods': results.get('time_periods', 0),
        'num_assets': len(results.get('assets', {})),
        'asset_types': {},
        'grid_import_kwh': 0.0,
        'grid_export_kwh': 0.0
    }

    # Count asset types
    for asset_id, asset_data in results.get('assets', {}).items():
        asset_type = asset_data.get('type', 'Unknown')
        summary['asset_types'][asset_type] = summary['asset_types'].get(asset_type, 0) + 1

    # Calculate grid import/export
    p_grid = results.get('p_grid', [])
    for power in p_grid:
        if power > 0:
            summary['grid_import_kwh'] += power
        else:
            summary['grid_export_kwh'] += abs(power)

    return summary