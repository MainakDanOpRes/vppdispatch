"""
Flexible Load Asset model for VPP Dispatch
"""

from typing import Tuple, Dict, Any
from pyomo.environ import Var, NonNegativeReals, Constraint

from .base_asset import BaseAsset

class FlexLoadAsset(BaseAsset):
    """Flexible load asset model."""

    def __init__(
        self,
        customer_id: str,
        asset_id: str,
        name: str = "FlexLoad",
        p_min_kw: float = 0.0,
        p_max_kw: float = 7.0,
        energy_required_kwh: float = 14.0,
        time_window: Tuple[int, int] = (0, 23),
    ):
        super().__init__(customer_id, asset_id)
        self.name = name
        self.p_min_kw = p_min_kw
        self.p_max_kw = p_max_kw
        self.energy_required_kwh = energy_required_kwh
        self.t_start, self.t_end = time_window

    def register_variables(self, m):
        """Register flexible load variables."""
        if not hasattr(m, f'flex_{self.asset_id}'):
            setattr(m, f'flex_{self.asset_id}', Var(m.T, domain=NonNegativeReals))

    def register_constraints(self, m):
        """Register flexible load constraints."""
        flex_var = getattr(m, f'flex_{self.asset_id}')
        dt = m.delta_t

        def flex_bounds_rule(m, t):
            if t < self.t_start or t > self.t_end:
                return flex_var[t] == 0
            return (self.p_min_kw, flex_var[t], self.p_max_kw)

        def energy_req_rule(m):
            return sum(flex_var[t] * dt for t in m.T) == self.energy_required_kwh

        setattr(m, f'flex_bounds_{self.asset_id}', Constraint(m.T, rule=flex_bounds_rule))
        setattr(m, f'flex_energy_{self.asset_id}', Constraint(rule=energy_req_rule))

    def get_results(self, m) -> Dict[str, Any]:
        """Extract flexible load results."""
        results = {}
        flex_var = getattr(m, f'flex_{self.asset_id}', None)
        if flex_var is not None:
            results['flex'] = [flex_var[t].value for t in m.T]
        return results