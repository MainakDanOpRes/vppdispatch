from typing import Tuple
from pyomo.environ import Var, Binary, Constraint
from .base_asset import BaseAsset

class FlexLoadOnOffAsset(BaseAsset):
    def __init__(
        self,
        customer_id: str,
        name: str,
        p_on_kw: float,
        energy_required_kwh: float,
        time_window: Tuple[int, int],
    ):
        super().__init__(customer_id)
        self.name = name
        self.p_on_kw = p_on_kw
        self.energy_required_kwh = energy_required_kwh
        self.t_start, self.t_end = time_window

    def register_variables(self, m):
        if not hasattr(m, "flex_on_index"):
            m.flex_on_index = []
        idx = len(m.flex_on_index)
        m.flex_on_index.append(idx)

        if not hasattr(m, "flex_on"):
            m.flex_on = Var(m.flex_on_index, m.T, domain=Binary)

        if not hasattr(m, "flex_on_meta"):
            m.flex_on_meta = {}
        m.flex_on_meta[idx] = self

    def register_constraints(self, m):
        dt = m.delta_t

        for idx, asset in m.flex_on_meta.items():
            def onoff_window_rule(m, t, idx=idx, asset=asset):
                if t < asset.t_start or t > asset.t_end:
                    return m.flex_on[idx, t] == 0
                return Constraint.Skip
            setattr(m, f"flex_on_window_{idx}", Constraint(m.T, rule=onoff_window_rule))

            def energy_req_rule(m, idx=idx, asset=asset):
                return sum(m.flex_on[idx, t] * asset.p_on_kw * dt for t in m.T) == asset.energy_required_kwh
            setattr(m, f"flex_on_energy_{idx}", Constraint(rule=energy_req_rule))
