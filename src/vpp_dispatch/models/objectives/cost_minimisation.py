from pyomo.environ import Objective, minimize

class CostObjective:
    def __init__(self, batt_degradation_cost_per_kwh: float = 0.0):
        self.batt_deg = batt_degradation_cost_per_kwh

    def register(self, m):
        dt = m.delta_t
        expr = sum(m.price_buy[t] * m.p_grid[t] * dt for t in m.T)

        if hasattr(m, "p_ch") and hasattr(m, "p_dis"):
            expr += self.batt_deg * sum((m.p_ch[t] + m.p_dis[t]) * dt for t in m.T)

        m.total_cost = Objective(expr=expr, sense=minimize)
