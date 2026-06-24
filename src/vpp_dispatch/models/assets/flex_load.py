from typing import Tuple
from pyomo.environ import Var, NonNegativeReals, Constraint
from .base_asset import BaseAsset


class FlexLoadAsset(BaseAsset):
    def __init__(
        self,
        customer_id: str,
        name: str,
        p_min_kw: float,
        p_max_kw: float,
        energy_required_kwh: float,
        time_window: Tuple[int, int],
    ):
        super().__init__(customer_id)
        self.name = name
        self.p_min_kw = p_min_kw
        self.p_max_kw = p_max_kw
        self.energy_required_kwh = energy_required_kwh
        self.t_start, self.t_end = time_window

    def register_variables(self, m):
        # Single flex-load variable over time
        if not hasattr(m, "flex"):
            m.flex = Var(m.T, domain=NonNegativeReals)

    def register_constraints(self, m):
        dt = m.delta_t

        # Bounds in time window
        def flex_bounds_rule(m, t):
            if t < self.t_start or t > self.t_end:
                return m.flex[t] == 0
            return (self.p_min_kw, m.flex[t], self.p_max_kw)

        m.flex_bounds = Constraint(m.T, rule=flex_bounds_rule)

        # Total energy requirement
        def energy_req_rule(m):
            return sum(m.flex[t] * dt for t in m.T) == self.energy_required_kwh

        m.flex_energy = Constraint(rule=energy_req_rule)
