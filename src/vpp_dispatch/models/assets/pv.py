"""
PV Asset model for VPP Dispatch
"""

from typing import List, Dict, Any
from pyomo.environ import Var, NonNegativeReals, Constraint, Param

from .base_asset import BaseAsset

class PVAsset(BaseAsset):
    """Photovoltaic asset model."""

    def __init__(self, customer_id: str, asset_id: str, pv_profile_kw: List[float],
                 objective_weight: float = 1.0):
        super().__init__(customer_id, asset_id, objective_weight)
        self.pv_profile_kw = pv_profile_kw

    def register_variables(self, m):
        """Register PV variables and parameters."""
        def pv_init(m, t):
            return self.pv_profile_kw[t]

        setattr(m, f'pv_avail_{self.asset_id}', Param(m.T, initialize=pv_init))
        setattr(m, f'pv_{self.asset_id}', Var(m.T, domain=NonNegativeReals))

    def register_constraints(self, m):
        """Register PV constraints."""
        pv_avail = getattr(m, f'pv_avail_{self.asset_id}')
        pv_var = getattr(m, f'pv_{self.asset_id}')

        def pv_limit_rule(m, t):
            return pv_var[t] <= pv_avail[t]

        setattr(m, f'pv_limit_{self.asset_id}', Constraint(m.T, rule=pv_limit_rule))

    def register_objectives(self, m):
        """
        Calculate the pv operational cost for the objective function.
        Cost = 0 for renewable sources
        """
        return 0.0

    def get_results(self, m) -> Dict[str, Any]:
        """Extract PV results."""
        results = {}
        pv_var = getattr(m, f'pv_{self.asset_id}', None)
        if pv_var is not None:
            results['pv'] = [pv_var[t].value for t in m.T]
        return results