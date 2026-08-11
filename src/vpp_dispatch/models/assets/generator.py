"""
Generator Asset model for VPP Dispatch
"""

from typing import Dict, Any
from pyomo.environ import Var, Binary, NonNegativeReals, Constraint

from .base_asset import BaseAsset

class GeneratorAsset(BaseAsset):
    """Generator asset model"""
    def __init__(self, customer_id: str, asset_id: str,
                 p_max_kw: float, p_min_kw: float, min_up_time: int,
                 min_down_time: int, ramp_rate: float, 
                 marginal_cost_per_kw: float = 0.0, start_up_cost: float = 0.0,
                 shut_down_cost: float = 0.0, objective_weight = 1):
        super().__init__(customer_id, asset_id, objective_weight)

        if p_max_kw < 0 or p_min_kw < 0:
            raise ValueError(
                f"operational boundaries p_min_kw and p_max_kw cannot be negative for generator {self.var_id}"
            )

        if p_min_kw >= p_max_kw:
            raise ValueError(
                f"operational power limit is invalid for generator {self.var_id}"
            )

        if marginal_cost_per_kw < 0 or start_up_cost < 0 or shut_down_cost < 0:
            raise ValueError(
                f"cost coefficients must be non negative for generator {self.var_id}"
            )

        self.p_max_kw = p_max_kw
        self.p_min_kw = p_min_kw
        self.min_up_time = min_up_time
        self.min_down_time = min_down_time
        self.ramp_rate = ramp_rate
        self.marginal_cost_per_kw = marginal_cost_per_kw
        self.start_up_cost = start_up_cost
        self.shut_down_cost = shut_down_cost

    def register_variables(self, m):
        """Register generator variables"""
        # Power generation variable
        setattr(m, f'p_gen_{self.var_id}', Var(m.T, within=NonNegativeReals))
        # Commitment status variable (1 if on, 0 if off)
        setattr(m, f'u_gen_{self.var_id}', Var(m.T, within=Binary))
        # Start-up binary variable (1 if transitioning from off to on)
        setattr(m, f'v_gen_{self.var_id}', Var(m.T, within=Binary))
        # Shut-down binary variable (1 if transitioning from on to off)
        setattr(m, f'w_gen_{self.var_id}', Var(m.T, within=Binary))

    def register_constraints(self, m):
        """Register operational, commitment, and min up/down constraints."""
        p_gen = getattr(m, f'p_gen_{self.var_id}')
        u_gen = getattr(m, f'u_gen_{self.var_id}')
        v_gen = getattr(m, f'v_gen_{self.var_id}')
        w_gen = getattr(m, f'w_gen_{self.var_id}')

        def p_min_rule(model, t):
            return p_gen[t] >= self.p_min_kw * u_gen[t]
        setattr(m, f'gen_p_min_constraint_{self.var_id}', Constraint(m.T, rule=p_min_rule))

        def p_max_rule(model, t):
            return p_gen[t] <= self.p_max_kw * u_gen[t]
        setattr(m, f'gen_p_max_constraint_{self.var_id}', Constraint(m.T, rule=p_max_rule))
