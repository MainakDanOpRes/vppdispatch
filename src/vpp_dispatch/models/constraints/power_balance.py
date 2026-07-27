"""
Power Balance Constraint for VPP Dispatch
Handles multiple assets of the same type properly
"""

from typing import List
from pyomo.environ import Var, Reals, Constraint, Param

class PowerBalanceConstraint:
    """Power balance constraint that works with multiple assets of same type."""

    def __init__(self, ts_data, assets: List = None):
        """
        Initialize with time series data and list of assets.

        Args:
            ts_data: CustomerTimeSeries object
            assets: List of asset objects (PVAsset, BatteryAsset, FlexLoadAsset)
        """
        self.ts_data = ts_data
        self.assets = assets or []

    def register_variables_and_params(self, m):
        """Register time series parameters and grid power variable."""
        # Time series data as parameters
        m.pv_profile = Param(m.T, initialize=lambda m, t: self.ts_data.pv_kw[t])
        m.fixed_load = Param(m.T, initialize=lambda m, t: self.ts_data.fixed_load_kw[t])
        m.price_buy = Param(m.T, initialize=lambda m, t: self.ts_data.price_buy[t])
        m.price_sell = Param(m.T, initialize=lambda m, t: self.ts_data.price_sell[t])

        # Grid power (can be positive or negative)
        if not hasattr(m, "p_grid"):
            m.p_grid = Var(m.T, domain=Reals)

    def register(self, m):
        """Register the power balance constraint."""

        def balance_rule(m, t):
            # Start with grid power
            generation = m.p_grid[t]  # Positive = import from grid

            # Add PV generation from all PV assets
            pv_generation = 0
            for asset in self.assets:
                if asset.__class__.__name__ == 'PVAsset':
                    pv_var = getattr(m, f'pv_{asset.asset_id}', None)
                    if pv_var is not None:
                        pv_generation += pv_var[t]

            # Add battery contributions (discharge - charge)
            battery_power = 0
            for asset in self.assets:
                if asset.__class__.__name__ == 'BatteryAsset':
                    p_dis = getattr(m, f'p_dis_{asset.asset_id}', None)
                    p_ch = getattr(m, f'p_ch_{asset.asset_id}', None)
                    if p_dis is not None:
                        battery_power += p_dis[t]  # Discharge adds to generation
                    if p_ch is not None:
                        battery_power -= p_ch[t]  # Charge subtracts from generation

            # Add flexible loads
            flex_load = 0
            for asset in self.assets:
                if asset.__class__.__name__ == 'FlexLoadAsset':
                    flex_var = getattr(m, f'flex_{asset.asset_id}', None)
                    if flex_var is not None:
                        flex_load += flex_var[t]

            # Power balance equation:
            # Generation (PV + Grid + Battery Discharge) = Load (Fixed + Flex + Battery Charge)
            # Rearranged: PV + Grid + Battery_Discharge - Battery_Charge = Fixed_Load + Flex_Load
            return (m.pv_profile[t] + m.p_grid[t] + battery_power ==
                    m.fixed_load[t] + flex_load)

        m.power_balance = Constraint(m.T, rule=balance_rule)