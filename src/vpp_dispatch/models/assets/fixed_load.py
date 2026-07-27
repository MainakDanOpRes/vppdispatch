"""
Fixed Load Asset model for VPP Dispatch
"""

from typing import List, Tuple, Dict, Any, Optional
from pyomo.environ import Var, NonNegativeReals, Constraint, Param
from .base_asset import BaseAsset

class FixedLoadAsset(BaseAsset):
    """Fixed load asset model that can be controllable or always-on."""

    def __init__(
        self,
        customer_id: str,
        asset_id: str,
        fixed_load_profile_kw: List[float],
        is_controllable: bool = False,
        priority: int = 1,
        operational_hours: Optional[Tuple[int, int]] = None
    ):
        super().__init__(customer_id, asset_id)
        self.fixed_load_profile_kw = fixed_load_profile_kw
        self.is_controllable = is_controllable
        self.priority = priority
        self.operational_hours = operational_hours

    def register_variables(self, m):
        """Register fixed load variables."""
        if self.is_controllable:
            # If controllable, create a variable for actual consumption
            setattr(m, f'fixed_{self.asset_id}', Var(m.T, domain=NonNegativeReals))
        else:
            # If not controllable, register as parameter
            def load_init(m, t):
                return self.fixed_load_profile_kw[t]
            setattr(m, f'fixed_{self.asset_id}', Param(m.T, initialize=load_init))

    def register_constraints(self, m):
        """Register fixed load constraints."""
        if self.is_controllable:
            fixed_var = getattr(m, f'fixed_{self.asset_id}')

            # Operational hours constraint
            if self.operational_hours:
                t_start, t_end = self.operational_hours

                def operational_rule(m, t):
                    if t < t_start or t >= t_end:
                        return fixed_var[t] == 0
                    return fixed_var[t] <= self.fixed_load_profile_kw[t]

                setattr(m, f'fixed_op_{self.asset_id}', Constraint(m.T, rule=operational_rule))
            else:
                # Always within profile
                def profile_rule(m, t):
                    return fixed_var[t] <= self.fixed_load_profile_kw[t]

                setattr(m, f'fixed_profile_{self.asset_id}', Constraint(m.T, rule=profile_rule))

    def get_results(self, m) -> Dict[str, Any]:
        """Extract fixed load results."""
        results = {}
        fixed_var = getattr(m, f'fixed_{self.asset_id}', None)
        if fixed_var is not None:
            if hasattr(fixed_var, '__getitem__'):  # It's a Pyomo indexed variable/param
                results['fixed_load'] = [fixed_var[t].value for t in m.T]
            else:
                results['fixed_load'] = fixed_var.value
        return results

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            **super().to_dict(),
            'type': 'FixedLoadAsset',
            'fixed_load_profile_kw': self.fixed_load_profile_kw,
            'is_controllable': self.is_controllable,
            'priority': self.priority,
            'operational_hours': self.operational_hours
        }