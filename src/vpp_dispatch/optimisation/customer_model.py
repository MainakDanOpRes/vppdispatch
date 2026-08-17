"""
Customer Model for VPP Optimization
Encapsulates customer-specific optimization logic and constraints.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging
from pyomo.environ import value

from ..models.timeseries import CustomerTimeSeries
from ..models.schemas import CustomerConfig, AssetConfig
from ..models.assets import BaseAsset, PVAsset, BatteryAsset, FlexLoadAsset, FixedLoadAsset, GridAsset
from ..models.constraints.power_balance import PowerBalanceConstraint
from ..models.objectives.cost_minimisation import CostObjective
from .model_builder import ModelBuilder
from .solver_manager import SolverManager
from .heuristics import HeuristicFallback
from ..services.asset_factory import create_assets_from_configs

logger = logging.getLogger(__name__)

class CustomerModel:
    """
    Encapsulates the optimization model for a single customer.

    This class provides a high-level interface for:
    - Building the optimization model for a customer
    - Solving the model
    - Extracting and processing results
    - Managing customer-specific constraints and objectives

    Features:
    - Dynamic asset configuration
    - Automatic fallback to heuristics
    - Result caching and reuse
    - Customer-specific constraint management
    """

    def __init__(
        self,
        customer_config: CustomerConfig,
        batt_degradation_cost: float = 0.01,
        solver_name: str = "highs",
        time_limit_sec: int = 30
    ):
        """
        Initialize the customer model.

        Args:
            customer_config: Customer configuration with assets and time series data
            batt_degradation_cost: Battery degradation cost per kWh
            solver_name: Name of the solver to use
            time_limit_sec: Time limit for solving in seconds
        """
        self.customer_config = customer_config
        self.customer_id = customer_config.customer_id
        self.batt_degradation_cost = batt_degradation_cost
        self.solver_name = solver_name
        self.time_limit_sec = time_limit_sec

        # Initialize model components
        self.ts: Optional[CustomerTimeSeries] = None
        self.assets: List[BaseAsset] = []
        self.pb: Optional[PowerBalanceConstraint] = None
        self.obj: Optional[CostObjective] = None
        self.builder: Optional[ModelBuilder] = None

        # Results
        self.model = None
        self.results: Dict[str, Any] = {}
        self.status: Dict[str, Any] = {}
        self.solved = False
        self.use_fallback = True

    def build(self) -> bool:
        """
        Build the optimization model for this customer.

        Returns:
            True if model was built successfully, False otherwise
        """
        try:
            logger.info(f"Building model for customer {self.customer_id}")

            # Create time series
            self.ts = CustomerTimeSeries(
                pv_kw=self.customer_config.pv_kw or [0.0] * self.customer_config.time_periods,
                fixed_load_kw=self.customer_config.fixed_load_kw or [0.0] * self.customer_config.time_periods,
                price_buy=self.customer_config.price_buy or [0.2] * self.customer_config.time_periods,
                price_sell=self.customer_config.price_sell or [0.1] * self.customer_config.time_periods,
            )

            # Create assets
            self.assets = create_assets_from_configs(
                self.customer_id,
                self.customer_config.assets
            )

            if not self.assets:
                logger.error(f"No assets created for customer {self.customer_id}")
                return False

            # Update asset profiles from time series if not set
            self._update_asset_profiles()

            # Create constraints and objective
            self.pb = PowerBalanceConstraint(ts_data=self.ts, assets=self.assets)
            self.obj = CostObjective(assets=self.assets, include_asset_costs=True)

            # Create model builder
            self.builder = ModelBuilder(
                assets=self.assets,
                power_balance=self.pb,
                objective=self.obj
            )

            logger.info(f"Model built successfully for customer {self.customer_id} with {len(self.assets)} assets")
            return True

        except Exception as e:
            logger.error(f"Error building model for customer {self.customer_id}: {e}")
            return False

    def _update_asset_profiles(self) -> None:
        """Update asset profiles from time series data if not set."""
        for asset in self.assets:
            if isinstance(asset, PVAsset) and not asset.pv_profile_kw:
                asset.pv_profile_kw = self.ts.pv_kw
            if isinstance(asset, GridAsset):
                if not asset.price_buy:
                    asset.price_buy = self.ts.price_buy
                if not asset.price_sell:
                    asset.price_sell = self.ts.price_sell
            if isinstance(asset, BatteryAsset):
                asset.degradation_cost_per_kwh = self.batt_degradation_cost

    def solve(self) -> bool:
        """
        Solve the optimization model.

        Returns:
            True if solution was found (either optimal or fallback), False otherwise
        """
        if not self.builder:
            if not self.build():
                return False

        try:
            T = self.ts.T
            delta_t = 1.0

            # Build the model
            model = self.builder.build(T=T, delta_t=delta_t)
            self.model = model

            # Solve with primary solver
            solver = SolverManager(
                solver_name=self.solver_name,
                time_limit_sec=self.time_limit_sec,
                use_fallback=self.use_fallback
            )
            model, self.status = solver.solve(model)
            self.model = model

            if self.status.get('success', False):
                self.solved = True
                self.results = self._extract_results()
                logger.info(f"Solved successfully for customer {self.customer_id}")
                return True
            elif self.use_fallback:
                # Try heuristic fallback
                logger.warning(f"Primary solver failed, trying fallback for customer {self.customer_id}")
                return self._try_fallback()
            else:
                logger.error(f"Failed to solve for customer {self.customer_id}")
                return False

        except Exception as e:
            logger.error(f"Error solving model for customer {self.customer_id}: {e}")
            return False

    def _try_fallback(self) -> bool:
        """Try heuristic fallback when optimization fails."""
        try:
            if not self.ts or not self.assets:
                return False

            hf = HeuristicFallback()
            heuristic_results = hf.run(self.ts, self.assets)

            # Store fallback results
            self.results = self._create_fallback_results(heuristic_results)
            self.status = {
                'success': True,
                'solver': 'heuristic_fallback',
                'status': 'fallback',
                'fallback': True
            }
            self.solved = True

            logger.info(f"Fallback succeeded for customer {self.customer_id}")
            return True

        except Exception as e:
            logger.error(f"Fallback failed for customer {self.customer_id}: {e}")
            return False

    def _extract_results(self) -> Dict[str, Any]:
        """Extract results from the solved model."""
        if not self.model or not self.assets:
            return {}

        T = self.ts.T
        results = {
            'objective': value(self.model.total_cost) if hasattr(self.model, 'total_cost') else 0.0,
            'assets': {},
            'time_periods': T,
            'fallback': False
        }

        # Extract grid power
        grid_assets = [a for a in self.assets if isinstance(a, GridAsset)]
        if grid_assets:
            grid = grid_assets[0]
            p_grid_var = getattr(self.model, f'p_grid_{grid.var_id}', None)
            if p_grid_var is not None:
                results['p_grid'] = [value(p_grid_var[t]) for t in self.model.T]
            else:
                results['p_grid'] = [0.0] * T
        else:
            results['p_grid'] = [0.0] * T

        # Extract results for each asset
        for asset in self.assets:
            try:
                asset_results = asset.get_results(self.model)
                results['assets'][asset.asset_id] = {
                    'type': asset.__class__.__name__,
                    'config': asset.to_dict(),
                    'results': asset_results
                }
            except Exception as e:
                logger.error(f"Error extracting results for asset {asset.asset_id}: {e}")
                results['assets'][asset.asset_id] = {
                    'type': asset.__class__.__name__,
                    'config': asset.to_dict(),
                    'results': {},
                    'error': str(e)
                }

        # Add metadata
        results['_metadata'] = {
            'customer_id': self.customer_id,
            'num_assets': len(self.assets),
            'time_periods': T,
            'status': 'success',
            'fallback': False,
            'solver': self.status.get('solver', 'unknown'),
            'solve_time_seconds': self.status.get('time_seconds', 0)
        }

        return results

    def _create_fallback_results(self, heuristic_results: Dict[str, Any]) -> Dict[str, Any]:
        """Create results dictionary from heuristic fallback."""
        T = self.ts.T
        results = {
            'p_grid': heuristic_results.get('p_grid', [0.0] * T),
            'objective': heuristic_results.get('objective', 0.0),
            'assets': {},
            'time_periods': T,
            'fallback': True,
            '_metadata': {
                'customer_id': self.customer_id,
                'num_assets': len(self.assets),
                'time_periods': T,
                'status': 'fallback_success',
                'fallback': True
            }
        }

        for asset in self.assets:
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

    def get_results(self) -> Dict[str, Any]:
        """Get the optimization results."""
        return self.results

    def get_status(self) -> Dict[str, Any]:
        """Get the solver status."""
        return self.status

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the optimization."""
        if not self.results:
            return {}

        summary = {
            'customer_id': self.customer_id,
            'total_cost': self.results.get('objective', 0.0),
            'time_periods': self.results.get('time_periods', 0),
            'num_assets': len(self.results.get('assets', {})),
            'asset_types': {},
            'grid_import_kwh': 0.0,
            'grid_export_kwh': 0.0,
            'fallback': self.results.get('fallback', False),
            'solved': self.solved,
            'solver': self.status.get('solver', 'unknown')
        }

        # Count asset types
        for asset_id, asset_data in self.results.get('assets', {}).items():
            asset_type = asset_data.get('type', 'Unknown')
            summary['asset_types'][asset_type] = summary['asset_types'].get(asset_type, 0) + 1

        # Calculate grid import/export
        p_grid = self.results.get('p_grid', [])
        for power in p_grid:
            if power > 0:
                summary['grid_import_kwh'] += power
            else:
                summary['grid_export_kwh'] += abs(power)

        return summary

    def add_asset(self, asset_config: Union[AssetConfig, dict]) -> bool:
        """
        Add an asset to this customer's configuration.

        Args:
            asset_config: Asset configuration to add

        Returns:
            True if asset was added successfully
        """
        try:
            if isinstance(asset_config, dict) and not isinstance(asset_config, AssetConfig):
                asset_config = AssetConfig(**asset_config)

            self.customer_config.assets.append(asset_config)
            self.assets = create_assets_from_configs(
                self.customer_id,
                self.customer_config.assets
            )
            logger.info(f"Added asset {asset_config.asset_id} to customer {self.customer_id}")
            return True

        except Exception as e:
            logger.error(f"Error adding asset to customer {self.customer_id}: {e}")
            return False

    def remove_asset(self, asset_id: str) -> bool:
        """
        Remove an asset from this customer's configuration.

        Args:
            asset_id: ID of the asset to remove

        Returns:
            True if asset was removed successfully
        """
        try:
            self.customer_config.assets = [
                ac for ac in self.customer_config.assets
                if ac.asset_id != asset_id
            ]
            self.assets = create_assets_from_configs(
                self.customer_id,
                self.customer_config.assets
            )
            logger.info(f"Removed asset {asset_id} from customer {self.customer_id}")
            return True

        except Exception as e:
            logger.error(f"Error removing asset {asset_id} from customer {self.customer_id}: {e}")
            return False

    def update_asset(self, asset_id: str, updates: dict) -> bool:
        """
        Update an asset's configuration.

        Args:
            asset_id: ID of the asset to update
            updates: Dictionary of updates to apply

        Returns:
            True if asset was updated successfully
        """
        try:
            for ac in self.customer_config.assets:
                if ac.asset_id == asset_id:
                    for key, value in updates.items():
                        if hasattr(ac, key):
                            setattr(ac, key, value)
                    break

            self.assets = create_assets_from_configs(
                self.customer_id,
                self.customer_config.assets
            )
            logger.info(f"Updated asset {asset_id} for customer {self.customer_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating asset {asset_id} for customer {self.customer_id}: {e}")
            return False