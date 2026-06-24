from pyomo.environ import ConcreteModel, RangeSet

class ModelBuilder:
    def __init__(self, assets, power_balance, objective):
        self.assets = assets
        self.power_balance = power_balance
        self.objective = objective

    def build(self, T, delta_t):
        m = ConcreteModel()

        # Time index
        m.T = RangeSet(0, T - 1)
        m.delta_t = delta_t

        # 1) Register variables for all assets
        for asset in self.assets:
            asset.register_variables(m)

        # 1b) Register power balance variables/params (p_grid, fixed_load, prices).
        #     Must happen before constraints are built so the balance rule can reference them.
        self.power_balance.register_variables_and_params(m)

        # 2) Register constraints for all assets
        for asset in self.assets:
            asset.register_constraints(m)

        # 3) Register power balance constraint
        self.power_balance.register(m)

        # 4) Register objective
        self.objective.register(m)

        return m