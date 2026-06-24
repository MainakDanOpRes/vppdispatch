from pyomo.environ import (
        ConcreteModel, Set, Param, Var, Binary, NonNegativeReals,
        Constraint, Objective, minimize, value, SolverFactory
)

from .base_asset import BaseAsset

class BatteryAsset(BaseAsset):
    def __init__(
        self,
        customer_id: str,
        capacity_kwh: float,
        p_charge_max_kw: float,
        p_discharge_max_kw: float,
        soc_min: float,
        soc_max: float,
        eff_charge: float,
        eff_discharge: float,
        soc_initial: float,
    ):
        super().__init__(customer_id)
        self.capacity_kwh = capacity_kwh
        self.p_charge_max_kw = p_charge_max_kw
        self.p_discharge_max_kw = p_discharge_max_kw
        self.soc_min = soc_min
        self.soc_max = soc_max
        self.eff_charge = eff_charge
        self.eff_discharge = eff_discharge
        self.soc_initial = soc_initial

    def register_variables(self, m):

        m.p_ch  = Var(m.T, within=NonNegativeReals, doc="Charge power [kW]")
        m.p_dis = Var(m.T, within=NonNegativeReals, doc="Discharge power [kW]")
        m.u     = Var(m.T, within=Binary,           doc="1=charging, 0=discharging")
        m.soc   = Var(m.T, within=NonNegativeReals, doc="State of charge [fraction]")

    def register_constraints(self, m):
    
        def soc_lo(m, t): return m.soc[t] >= self.soc_min
        def soc_hi(m, t): return m.soc[t] <= self.soc_max
        def charge_ub(m, t): return m.p_ch[t] <= self.p_charge_max_kw * m.u[t]
        def disch_ub(m, t):  return m.p_dis[t] <= self.p_discharge_max_kw * (1 - m.u[t])

        def soc_rule(m, t):
            if t == m.T.first():
                return m.soc[t] == self.soc_initial + (
                    self.eff_charge * m.p_ch[t] * m.delta_t
                    - (1 / self.eff_discharge) * m.p_dis[t] * m.delta_t
                )
            return m.soc[t] == m.soc[t - 1] + (
                self.eff_charge * m.p_ch[t] * m.delta_t
                - (1 / self.eff_discharge) * m.p_dis[t] * m.delta_t
            )

        m.battery_soc = Constraint(m.T, rule=soc_rule)
        m.c_soc_lo = Constraint(m.T, rule=soc_lo)
        m.c_soc_hi = Constraint(m.T, rule=soc_hi)
        m.c_charge_ub = Constraint(m.T, rule=charge_ub)
        m.c_disch_ub  = Constraint(m.T, rule=disch_ub)
