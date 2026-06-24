from pyomo.environ import Var, Reals, Constraint, Param

class PowerBalanceConstraint:
    def __init__(self, ts_data):
        self.ts_data = ts_data

    def register_variables_and_params(self, m):
        m.pv_profile = Param(m.T, initialize=lambda m, t: self.ts_data.pv_kw[t])
        m.fixed_load = Param(m.T, initialize=lambda m, t: self.ts_data.fixed_load_kw[t])
        m.price_buy = Param(m.T, initialize=lambda m, t: self.ts_data.price_buy[t])
        m.price_sell = Param(m.T, initialize=lambda m, t: self.ts_data.price_sell[t])
        if not hasattr(m, "p_grid"):
            m.p_grid = Var(m.T, domain=Reals)

    def register(self, m):
        def balance_rule(m, t):
            pv_term = m.pv[t] if hasattr(m, "pv") else m.pv_profile[t]

            flex_sum = 0
            # FlexLoadAsset registers m.flex as a 1-D Var indexed only by T
            if hasattr(m, "flex"):
                flex_sum += m.flex[t]
            # FlexLoadOnOffAsset registers m.flex_on indexed by (idx, T)
            if hasattr(m, "flex_on_index"):
                flex_sum += sum(
                    m.flex_on[idx, t] * m.flex_on_meta[idx].p_on_kw
                    for idx in m.flex_on_index
                )

            return pv_term + m.p_grid[t] == m.fixed_load[t] + flex_sum + m.p_ch[t] - m.p_dis[t]

        m.power_balance = Constraint(m.T, rule=balance_rule)