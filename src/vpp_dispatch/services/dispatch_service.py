"""
Dispatch Service for VPP Optimization
Main service for running optimization with dynamic asset configuration.
"""

from typing import Dict, Any, List, Optional, Tuple, Union
from pyomo.environ import value
import logging
from datetime import datetime

from ..models.timeseries import CustomerTimeSeries
from ..models.schemas import CustomerConfig, AssetConfig, AssetType, LiveCustomerInput
from ..models.assets import PVAsset, BatteryAsset, FlexLoadAsset, FixedLoadAsset, GridAsset, BaseAsset, GeneratorAsset
from ..models.constraints.power_balance import PowerBalanceConstraint
from ..models.objectives.cost_minimisation import CostObjective
from ..optimisation.model_builder import ModelBuilder
from ..optimisation.solver_manager import SolverManager
from ..optimisation.heuristics import HeuristicFallback
from .asset_factory import create_assets_from_configs, create_asset_from_config

logger = logging.getLogger(__name__)

# ============================================================================
# SINGLE CUSTOMER DISPATCH (Legacy - Backward Compatible)
# ============================================================================

def run_single_customer_dispatch(
    customer_id: str,
    ts: CustomerTimeSeries
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Run optimization for a single customer with DEFAULT asset configuration.

    This is the legacy function for backward compatibility with existing integrations.
    Creates default assets (PV, Battery, FixedLoad, Grid) and runs optimization.

    Args:
        customer_id: Customer identifier
        ts: Time series data with pv_kw, fixed_load_kw, price_buy, price_sell

    Returns:
        Tuple of (results_dict, status_dict)
    """
    T = ts.T
    delta_t = 1.0  # hours

    logger.info(f"Running legacy dispatch for customer {customer_id} with {T} time periods")

    # Create default assets (backward compatible)
    assets = []

    # PV Asset
    pv = PVAsset(
        customer_id=customer_id,
        asset_id="pv_1",
        pv_profile_kw=ts.pv_kw,
        objective_weight=1.0
    )
    assets.append(pv)

    # Battery Asset
    battery = BatteryAsset(
        customer_id=customer_id,
        asset_id="battery_1",
        capacity_kwh=10.0,
        p_charge_max_kw=5.0,
        p_discharge_max_kw=5.0,
        soc_min=0.1,
        soc_max=0.9,
        eff_charge=0.95,
        eff_discharge=0.95,
        soc_initial=None,  # Will default to 50% of capacity
        degradation_cost_per_kwh=0.01,
        objective_weight=1.0
    )
    assets.append(battery)

    # Flex Load Asset
    flex = FlexLoadAsset(
        customer_id=customer_id,
        asset_id="flex_1",
        name="EV",
        p_min_kw=0.0,
        p_max_kw=7.0,
        energy_required_kwh=14.0,
        time_window=(10, 20),
        objective_weight=1.0
    )
    assets.append(flex)

    # Grid Asset
    grid = GridAsset(
        customer_id=customer_id,
        asset_id="grid_1",
        import_max_kw=100.0,
        export_max_kw=100.0,
        price_buy=ts.price_buy,
        price_sell=ts.price_sell,
        objective_weight=1.0
    )
    assets.append(grid)

    fixed_load = FixedLoadAsset(
        customer_id=customer_id,
        asset_id="fixed_1",
        fixed_load_profile_kw=ts.fixed_load_kw,
        objective_weight=1.0
    )
    assets.append(fixed_load)

    # Create constraints and objective
    pb = PowerBalanceConstraint(ts_data=ts, assets=assets)
    obj = CostObjective(assets=assets, include_asset_costs=True)

    # Build and solve model
    builder = ModelBuilder(assets=assets, power_balance=pb, objective=obj)
    model = builder.build(T=T, delta_t=delta_t)

    solver = SolverManager(solver_name="highs", time_limit_sec=10)
    model, status = solver.solve(model)

    # Extract results (legacy format)
    results = _extract_legacy_results(model, assets, T)

    logger.info(f"Legacy dispatch completed for customer {customer_id}")
    return results, status

def _extract_legacy_results(
    model,
    assets: List[BaseAsset],
    T: int
) -> Dict[str, Any]:
    """Extract results in legacy format for backward compatibility."""
    results = {
        "p_grid": [0.0] * T,
        "p_ch": [0.0] * T,
        "p_dis": [0.0] * T,
        "soc": [5.0] * T,
        "flex_ev": [0.0] * T,
        "pv_1": [0.0] * T,
        "objective": 0.0
    }

    try:
        # Extract grid power
        grid_assets = [a for a in assets if isinstance(a, GridAsset)]
        if grid_assets:
            grid = grid_assets[0]
            p_grid_var = getattr(model, f'p_grid_{grid.var_id}', None)
            if p_grid_var is not None:
                results["p_grid"] = [value(p_grid_var[t]) for t in model.T]

        # Extract battery variables
        battery_assets = [a for a in assets if isinstance(a, BatteryAsset)]
        if battery_assets:
            battery = battery_assets[0]
            results["p_ch"] = [value(getattr(model, f'p_ch_{battery.var_id}', [0.0]*T)[t]) for t in model.T]
            results["p_dis"] = [value(getattr(model, f'p_dis_{battery.var_id}', [0.0]*T)[t]) for t in model.T]
            results["soc"] = [value(getattr(model, f'soc_{battery.var_id}', [5.0]*T)[t]) for t in model.T]

        # Extract flex load
        flex_assets = [a for a in assets if isinstance(a, FlexLoadAsset)]
        if flex_assets:
            flex = flex_assets[0]
            results["flex_ev"] = [value(getattr(model, f'flex_{flex.var_id}', [0.0]*T)[t]) for t in model.T]

        # Extract PV
        pv_assets = [a for a in assets if isinstance(a, PVAsset)]
        if pv_assets:
            pv = pv_assets[0]
            results["pv_1"] = [value(getattr(model, f'pv_{pv.var_id}', [0.0]*T)[t]) for t in model.T]

        # Extract objective
        if hasattr(model, 'total_cost'):
            results["objective"] = value(model.total_cost)

    except Exception as e:
        logger.warning(f"Error extracting legacy results: {e}")

    return results

# ============================================================================
# SINGLE CUSTOMER DISPATCH (From Live Input)
# ============================================================================

def run_dispatch_from_live_input(
    live_input: LiveCustomerInput
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Run optimization from live customer input (backward compatible).

    Args:
        live_input: LiveCustomerInput object with customer_id and time series data

    Returns:
        Tuple of (results_dict, status_dict)
    """
    ts = live_input.to_timeseries()
    return run_single_customer_dispatch(live_input.customer_id, ts)

# ============================================================================
# MULTI-ASSET DISPATCH (Main Function)
# ============================================================================

def run_multi_asset_dispatch(
    customer_config: Union[CustomerConfig, dict],
    batt_degradation_cost: float = 0.01
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Run optimization for a customer with CUSTOM asset configuration.

    This is the main dispatch function that supports any number of assets of any type:
    - PV (Photovoltaic)
    - Battery (Storage)
    - FlexLoad (Flexible Load - Continuous, Shiftable, or On/Off)
    - FixedLoad (Fixed Load - Controllable or Always-On)
    - Grid (Grid Connection with Import/Export)

    Features:
    - Dynamic asset configuration via CustomerConfig
    - Automatic fallback to heuristic solution if optimization fails
    - Comprehensive result extraction for all asset types
    - Metadata tracking (timing, asset counts, etc.)

    Args:
        customer_config: CustomerConfig with assets and time series data
        batt_degradation_cost: Battery degradation cost per kWh (default: 0.01)

    Returns:
        Tuple of (results_dict, status_dict) where:
        - results_dict: Optimization results with asset details
        - status_dict: Solver status information
    """
    start_time = datetime.now()

    # Convert dict to CustomerConfig if needed
    if isinstance(customer_config, dict):
        try:
            customer_config = CustomerConfig(**customer_config)
        except Exception as e:
            logger.error(f"Failed to parse customer config: {e}")
            return {}, {'status': 'failed', 'error': str(e), 'success': False}

    customer_id = customer_config.customer_id
    logger.info(f"Running multi-asset dispatch for customer {customer_id} with {len(customer_config.assets)} assets")

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
            error_msg = 'No valid assets created from configuration'
            logger.error(error_msg)
            return {}, {'status': 'failed', 'error': error_msg, 'success': False}

        logger.debug(f"Created {len(assets)} assets: {[a.__class__.__name__ for a in assets]}")

        # Update asset profiles from customer config if not set
        for asset in assets:
            if isinstance(asset, PVAsset) and not asset.pv_profile_kw:
                asset.pv_profile_kw = ts.pv_kw
            if isinstance(asset, GridAsset):
                if not asset.price_buy:
                    asset.price_buy = ts.price_buy
                if not asset.price_sell:
                    asset.price_sell = ts.price_sell
            if isinstance(asset, BatteryAsset):
                asset.degradation_cost_per_kwh = batt_degradation_cost

        # Create constraints with asset list
        pb = PowerBalanceConstraint(ts_data=ts, assets=assets)
        obj = CostObjective(assets=assets, include_asset_costs=True)

        # Build and solve model
        builder = ModelBuilder(assets=assets, power_balance=pb, objective=obj)
        model = builder.build(T=T, delta_t=delta_t)

        solver = SolverManager(solver_name="highs", time_limit_sec=30)
        model, status = solver.solve(model)

        if not status.get('success', False):
            # Try heuristic fallback
            logger.warning(f"Optimization failed, trying heuristic fallback: {status.get('error', 'Unknown error')}")
            try:
                hf = HeuristicFallback()
                res = hf.run(ts, assets)
                fallback_results = _create_fallback_results(res, assets, T)
                fallback_results['_metadata'] = {
                    'timestamp': datetime.now().isoformat(),
                    'duration_seconds': (datetime.now() - start_time).total_seconds(),
                    'customer_id': customer_id,
                    'num_assets': len(assets),
                    'time_periods': T,
                    'status': 'fallback_success',
                    'fallback': True,
                    'solver': status.get('solver', 'none'),
                    'tried_solvers': status.get('tried_solvers', [])
                }
                logger.info(f"Heuristic fallback succeeded for customer {customer_id}")
                return fallback_results, status
            except Exception as e:
                logger.error(f"Heuristic fallback failed for customer {customer_id}: {e}")
                return {}, status

        # Extract results for all assets
        results = _extract_results_from_model(model, assets, T)

        # Add metadata
        results['_metadata'] = {
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': (datetime.now() - start_time).total_seconds(),
            'customer_id': customer_id,
            'num_assets': len(assets),
            'time_periods': T,
            'status': 'success',
            'fallback': False,
            'solver': status.get('solver', 'unknown'),
            'solve_time_seconds': status.get('time_seconds', 0)
        }

        logger.info(f"Multi-asset dispatch completed successfully for customer {customer_id}")
        return results, status

    except Exception as e:
        logger.error(f"Error in multi-asset dispatch for customer {customer_id}: {e}", exc_info=True)
        return {}, {'status': 'failed', 'error': str(e), 'success': False}

def _create_fallback_results(
    heuristic_results: Dict[str, Any],
    assets: List[BaseAsset],
    T: int
) -> Dict[str, Any]:
    """Create results dictionary from heuristic fallback."""
    results = {
        'p_grid': heuristic_results.get('p_grid', [0.0] * T),
        'objective': heuristic_results.get('objective', 0.0),
        'assets': {},
        'time_periods': T,
        'fallback': True
    }

    for asset in assets:
        asset_id = asset.asset_id
        asset_type = asset.__class__.__name__

        if isinstance(asset, BatteryAsset):
            results['assets'][asset_id] = {
                'type': asset_type,
                'config': asset.to_dict(),
                'results': {
                    'p_ch': heuristic_results.get('p_ch', [0.0] * T),
                    'p_dis': heuristic_results.get('p_dis', [0.0] * T),
                    'soc': heuristic_results.get('soc', [asset.soc_initial] * T)
                }
            }
        elif isinstance(asset, FlexLoadAsset):
            results['assets'][asset_id] = {
                'type': asset_type,
                'config': asset.to_dict(),
                'results': {
                    'flex_power_kw': heuristic_results.get('flex', [0.0] * T)
                }
            }
        elif isinstance(asset, PVAsset):
            results['assets'][asset_id] = {
                'type': asset_type,
                'config': asset.to_dict(),
                'results': {
                    'pv_power_kw': heuristic_results.get('pv', asset.pv_profile_kw)
                }
            }
        elif isinstance(asset, GridAsset):
            results['assets'][asset_id] = {
                'type': asset_type,
                'config': asset.to_dict(),
                'results': {
                    'p_grid': heuristic_results.get('p_grid', [0.0] * T)
                }
            }
        elif isinstance(asset, FixedLoadAsset):
            results['assets'][asset_id] = {
                'type': asset_type,
                'config': asset.to_dict(),
                'results': {
                    'fixed_load': heuristic_results.get('fixed_load', asset.fixed_load_profile_kw)
                }
            }

    return results

def _extract_results_from_model(
    model,
    assets: List[BaseAsset],
    T: int
) -> Dict[str, Any]:
    """
    Extract results from the solved model for all assets.

    Args:
        model: Solved Pyomo model
        assets: List of asset objects
        T: Number of time periods

    Returns:
        Dictionary with all results organized by asset
    """
    results = {
        'objective': value(model.total_cost) if hasattr(model, 'total_cost') else 0.0,
        'assets': {},
        'time_periods': T,
        'fallback': False
    }

    # Extract grid power if available
    grid_assets = [a for a in assets if isinstance(a, GridAsset)]
    if grid_assets:
        grid = grid_assets[0]  # Use first grid asset for backward compatibility
        p_grid_var = getattr(model, f'p_grid_{grid.var_id}', None)
        if p_grid_var is not None:
            results['p_grid'] = [value(p_grid_var[t]) for t in model.T]
        else:
            results['p_grid'] = [0.0] * T
    else:
        results['p_grid'] = [0.0] * T

    # Extract results for each asset
    for asset in assets:
        try:
            asset_results = asset.get_results(model)
            results['assets'][asset.asset_id] = {
                'type': asset.__class__.__name__,
                'config': asset.to_dict(),
                'results': asset_results
            }
            logger.debug(f"Extracted results for {asset.__class__.__name__} ({asset.asset_id})")
        except Exception as e:
            logger.error(f"Error extracting results for asset {asset.asset_id}: {e}")
            results['assets'][asset.asset_id] = {
                'type': asset.__class__.__name__,
                'config': asset.to_dict(),
                'results': {},
                'error': str(e)
            }

    return results

# ============================================================================
# BATCH DISPATCH
# ============================================================================

def run_batch_dispatch(
    customer_configs: List[Union[CustomerConfig, dict]],
    batt_degradation_cost: float = 0.01
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Run optimization for multiple customers.

    This is a convenience function that calls the batch dispatch service.

    Args:
        customer_configs: List of CustomerConfig objects or dictionaries
        batt_degradation_cost: Battery degradation cost per kWh

    Returns:
        Tuple of (batch_results, overall_status)
    """
    from .batch_dispatch import run_batch_dispatch as parallel_batch_dispatch, get_batch_summary

    batch_results = parallel_batch_dispatch(
        customer_configs=customer_configs,
        max_workers=4,
        batt_degradation_cost=batt_degradation_cost
    )

    # Generate summary
    summary = get_batch_summary(batch_results)

    # Build overall status
    total = len(customer_configs)
    successful = summary['successful']

    overall_status = {
        'total_customers': total,
        'successful_customers': successful,
        'fallback_customers': summary['fallback'],
        'failed_customers': summary['failed'],
        'overall_status': summary['overall_status'],
        'total_objective': summary['total_objective'],
        'average_objective': summary['average_objective'],
        'asset_type_counts': summary['asset_type_counts']
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
        'grid_export_kwh': 0.0,
        'fallback': results.get('fallback', False),
        'status': results.get('_metadata', {}).get('status', 'unknown')
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

def get_asset_results(
    results: Dict[str, Any],
    asset_id: str
) -> Optional[Dict[str, Any]]:
    """
    Get results for a specific asset from optimization results.

    Args:
        results: Optimization results dictionary
        asset_id: ID of the asset to get results for

    Returns:
        Asset results dictionary, or None if not found
    """
    assets = results.get('assets', {})
    return assets.get(asset_id)

def get_asset_time_series(
    results: Dict[str, Any],
    asset_id: str,
    variable_name: str
) -> Optional[List[float]]:
    """
    Get a specific time series variable for an asset.

    Args:
        results: Optimization results dictionary
        asset_id: ID of the asset
        variable_name: Name of the variable (e.g., 'p_ch', 'p_dis', 'soc')

    Returns:
        List of values for the variable across all time periods, or None if not found
    """
    asset_results = get_asset_results(results, asset_id)
    if asset_results:
        return asset_results.get('results', {}).get(variable_name)
    return None