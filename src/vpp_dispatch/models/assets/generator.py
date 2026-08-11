"""
Generator Asset model for VPP Dispatch
"""

from typing import Dict, Any
from pyomo.environ import Var, Binary, NonNegativeReals, Constraint

from .base_asset import BaseAsset

class GeneratorAsset(BaseAsset):
    """Generator asset model"""
    def __init__(self, customer_id: str, asset_id: str,
                 p_max_kw: float, p_min_kw: float, ramp_rate: float = None,
                 min_up_time: int = None, min_down_time: int = None, 
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

        if ramp_rate is not None:
            if ramp_rate <= 0 or ramp_rate <= p_min_kw:
                raise ValueError (f"invalid ramp rate for generator {self.var_id},"
                                  f" as it is either less than 0 or p_min_kw")

        if marginal_cost_per_kw < 0 or start_up_cost < 0 or shut_down_cost < 0:
            raise ValueError(
                f"cost coefficients must be non negative for generator {self.var_id}"
            )

        if min_up_time <= 0:
            raise ValueError(
                f"invalid min_up_time for generator {self.var_id}"
            )

        if min_down_time <= 0:
            raise ValueError(
                f"invalid min_down_time for generator {self.var_id}"
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

        def p_min_rule(m, t):
            return p_gen[t] >= self.p_min_kw * u_gen[t]
        setattr(m, f'gen_p_min_constraint_{self.var_id}', 
                Constraint(m.T, rule=p_min_rule))

        def p_max_rule(m, t):
            return p_gen[t] <= self.p_max_kw * u_gen[t]
        setattr(m, f'gen_p_max_constraint_{self.var_id}', 
                Constraint(m.T, rule=p_max_rule))

        def ramp_up_rule(m, t):
            if t == m.T.first():
                return Constraint.Skip
            return p_gen[t] - p_gen[t-1] <= self.ramp_rate
        setattr(m, f'gen_ramp_up_constraint_{self.var_id}', 
                Constraint(m.T, rule=ramp_up_rule))

        def ramp_down_rule(m, t):
            if t == m.T.first():
                return Constraint.Skip
            return p_gen[t] - p_gen[t-1] >= -self.ramp_rate
        setattr(m, f'gen_ramp_down_constraint_{self.var_id}', 
                Constraint(m.T, rule=ramp_down_rule))

        def startup_shutdown_rule(m, t):
            if t == m.T.first():
                # No previous commitment state is available.
                return Constraint.Skip
            return u_gen[t] - u_gen[t - 1] == v_gen[t] - w_gen[t]
        setattr(m,f'gen_commitment_transition_constraint_{self.var_id}',
                Constraint(m.T, rule=startup_shutdown_rule)
                )

        def startup_shutdown_exclusivity_rule(m, t):
            return w_gen[t] + v_gen[t] <= 1
        setattr(m,f'gen_startup_shutdown_exclusivity_{self.var_id}',
                Constraint(m.T, rule=startup_shutdown_exclusivity_rule))

        def min_up_rule(m, t):
            if t == m.T.first():
                return Constraint.Skip

            periods = list(m.T)
            start_idx = periods.index(t)
            end_idx = min(
                start_idx + self.min_up_time,
                len(periods)
            )

            window = periods[start_idx:end_idx]

            return sum(u_gen[k] for k in window) >= len(window) * v_gen[t]

        setattr(m, f'gen_min_up_constraint_{self.var_id}',
                Constraint(m.T, rule=min_up_rule)
                )

        def min_down_rule(m, t):
            if t == m.T.first():
                return Constraint.Skip

            periods = list(m.T)
            start_idx = periods.index(t)
            end_idx = min(
                start_idx + self.min_down_time,
                len(periods)
            )

            window = periods[start_idx:end_idx]

            return sum(u_gen[k] for k in window) <= len(window) * (1 - w_gen[t])

        setattr(m,f'gen_min_down_constraint_{self.var_id}',
                Constraint(m.T, rule=min_down_rule)
                )

    def register_objectives(self, m):
        """Return total cost expression including generation, startup, and shutdown costs"""
        p_gen = getattr(m, f'p_gen_{self.var_id}')
        v_gen = getattr(m, f'v_gen_{self.var_id}')
        w_gen = getattr(m, f'w_gen_{self.var_id}')

        cost_expr = sum(
            self.objective_weight * (
                p_gen[t] * self.marginal_cost_per_kw +
                v_gen[t] * self.start_up_cost +
                w_gen[t] * self.shut_down_cost
            )
            for t in m.T
        )
        return cost_expr

    def get_results(self, m) -> Dict[str, Any]:
        """Extract generator results."""
        results = {}
        for var_name in ['p_gen', 'u_gen', 'v_gen', 'w_gen']:
            var = getattr(m, f'{var_name}_{self.var_id}', None)
            if var is not None:
                results[var_name] = [var[t].value for t in m.T]
        return results

    def to_dict(self) -> Dict[str, Any]:
        """Serialize Generator asset to dictionary."""
        d = super().to_dict()
        d.update({
            "p_max_kw": self.p_max_kw,
            "p_min_kw": self.p_min_kw,
            "min_up_time": self.min_up_time,
            "min_down_time": self.min_down_time,
            "ramp_rate": self.ramp_rate,
            "marginal_cost_per_kw": self.marginal_cost_per_kw,
            "start_up_cost": self.start_up_cost,
            "shut_down_cost": self.shut_down_cost
        })
        return d