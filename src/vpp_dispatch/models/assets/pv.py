

from pyomo.environ import Var, NonNegativeReals, Constraint, Param

from .base_asset import BaseAsset

class PVAsset(BaseAsset):
    def __init__(self, customer_id: str, pv_profile_kw):
        super().__init__(customer_id)
        self.pv_profile_kw = pv_profile_kw  # list/array length T

    def register_variables(self, m):
        # available PV as parameter
        def pv_init(m, t):
            return self.pv_profile_kw[t]
        m.pv_avail = Param(m.T, initialize=pv_init)

        # actual used PV (after curtailment)
        m.pv = Var(m.T, domain=NonNegativeReals)

    def register_constraints(self, m):
        def pv_limit_rule(m, t):
            return m.pv[t] <= m.pv_avail[t]
        m.pv_limit = Constraint(m.T, rule=pv_limit_rule)
