from typing import List
from pyomo.environ import Constraint

class PowerBalanceConstraint:
    """Power balance constraint that dynamically aggregates all assets, including the GridAsset."""

    def __init__(self, ts_data, assets: List = None):
        """
        Initialize with time series data and list of assets.

        Args:
            ts_data: CustomerTimeSeries object (kept for backward compatibility)
            assets: List of asset objects (PVAsset, BatteryAsset, FlexLoadAsset, FixedLoadAsset, GridAsset)
        """
        self.ts_data = ts_data
        self.assets = assets or []

    def register_variables_and_params(self, m):
        """
        Variables and parameters (like grid tariffs, PV profiles, and fixed loads) 
        are now encapsulated within their respective asset classes. 
        Nothing needs to be registered globally here.
        """
        pass

    def register(self, m):
        """Register the dynamic power balance constraint."""

        def balance_rule(m, t):
            total_generation = 0.0
            total_load = 0.0

            for asset in self.assets:
                asset_class = asset.__class__.__name__

                # 1. Grid Contributions
                if asset_class == 'GridAsset':
                    p_grid = getattr(m, f'p_grid_{asset.asset_id}', None)
                    if p_grid is not None:
                        total_generation += p_grid[t]  # Positive = import (generation for the home)

                # 2. PV Contributions
                elif asset_class == 'PVAsset':
                    pv_var = getattr(m, f'pv_{asset.asset_id}', None)
                    if pv_var is not None:
                        total_generation += pv_var[t]

                # 3. Battery Contributions
                elif asset_class == 'BatteryAsset':
                    p_dis = getattr(m, f'p_dis_{asset.asset_id}', None)
                    p_ch = getattr(m, f'p_ch_{asset.asset_id}', None)
                    if p_dis is not None:
                        total_generation += p_dis[t]   # Discharge acts as generation
                    if p_ch is not None:
                        total_load += p_ch[t]          # Charge acts as load

                # 4. Flexible Load Contributions
                elif asset_class == 'FlexLoadAsset':
                    flex_var = getattr(m, f'flex_{asset.asset_id}', None)
                    if flex_var is not None:
                        total_load += flex_var[t]

                # 5. Fixed Load Contributions
                elif asset_class == 'FixedLoadAsset':
                    fixed_var = getattr(m, f'fixed_load_{asset.asset_id}', None)
                    if fixed_var is not None:
                        total_load += fixed_var[t]

            # Power balance equation: Total Generation == Total Load
            if total_generation is 0.0 and total_load is 0.0:
                return Constraint.Skip
                
            return total_generation == total_load

        m.power_balance = Constraint(m.T, rule=balance_rule)