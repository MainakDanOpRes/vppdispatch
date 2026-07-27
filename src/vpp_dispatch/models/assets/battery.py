"""
Battery Asset model for VPP Dispatch
"""

from typing import Dict, Any
from pyomo.environ import Var, Binary, NonNegativeReals, Constraint

from .base_asset import BaseAsset

class BatteryAsset(BaseAsset):
    """Battery storage asset model."""

    def __init__(
        self,
        customer_id: str,
        asset_id: str,
        capacity_kwh: float,
        p_charge_max_kw: float,
        p_discharge_max_kw: float,
        soc_min: float = 0.1,
        soc_max: float = 0.9,
        eff_charge: float = 0.95,
        eff_discharge: float = 0.95,
        soc_initial: float = None,
    ):
        super().__init__(customer_id, asset_id)
        self.capacity_kwh = capacity_kwh
        self.p_charge_max_kw = p_charge_max_kw
        self.p_discharge_max_kw = p_discharge_max_kw
        self.soc_min = soc_min * capacity_kwh
        self.soc_max = soc_max * capacity_kwh
        self.eff_charge = eff_charge
        self.eff_discharge = eff_discharge
        self.soc_initial = soc_initial if soc_initial is not None else (0.5 * capacity_kwh)

    def register_variables(self, m):
        """Register battery variables."""
        setattr(m, f'p_ch_{self.asset_id}', Var(m.T, within=NonNegativeReals))
        setattr(m, f'p_dis_{self.asset_id}', Var(m.T, within=NonNegativeReals))
        setattr(m, f'u_{self.asset_id}', Var(m.T, within=Binary))
        setattr(m, f'soc_{self.asset_id}', Var(m.T, within=NonNegativeReals))

    def register_constraints(self, m):
        """Register battery constraints."""
        p_ch = getattr(m, f'p_ch_{self.asset_id}')
        p_dis = getattr(m, f'p_dis_{self.asset_id}')
        u = getattr(m, f'u_{self.asset_id}')
        soc = getattr(m, f'soc_{self.asset_id}')

        def soc_lo(m, t): return soc[t] >= self.soc_min
        def soc_hi(m, t): return soc[t] <= self.soc_max
        def charge_ub(m, t): return p_ch[t] <= self.p_charge_max_kw * u[t]
        def disch_ub(m, t): return p_dis[t] <= self.p_discharge_max_kw * (1 - u[t])

        def soc_rule(m, t):
            if t == m.T.first():
                return soc[t] == self.soc_initial + (
                    self.eff_charge * p_ch[t] * m.delta_t
                    - (1 / self.eff_discharge) * p_dis[t] * m.delta_t
                )
            return soc[t] == soc[t - 1] + (
                self.eff_charge * p_ch[t] * m.delta_t
                - (1 / self.eff_discharge) * p_dis[t] * m.delta_t
            )

        setattr(m, f'battery_soc_{self.asset_id}', Constraint(m.T, rule=soc_rule))
        setattr(m, f'c_soc_lo_{self.asset_id}', Constraint(m.T, rule=soc_lo))
        setattr(m, f'c_soc_hi_{self.asset_id}', Constraint(m.T, rule=soc_hi))
        setattr(m, f'c_charge_ub_{self.asset_id}', Constraint(m.T, rule=charge_ub))
        setattr(m, f'c_disch_ub_{self.asset_id}', Constraint(m.T, rule=disch_ub))

    def get_results(self, m) -> Dict[str, Any]:
        """Extract battery results."""
        results = {}
        for var_name in ['p_ch', 'p_dis', 'soc']:
            var = getattr(m, f'{var_name}_{self.asset_id}', None)
            if var is not None:
                results[var_name] = [var[t].value for t in m.T]
        return results