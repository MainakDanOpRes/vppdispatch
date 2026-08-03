from typing import List, Dict, Any
from pyomo.environ import Var, Reals, NonNegativeReals, Constraint, Param, value
from .base_asset import BaseAsset

class GridAsset(BaseAsset):
    """Grid connection asset modeling imports, exports, and tariffs."""

    def __init__(
        self, 
        customer_id: str, 
        asset_id: str,
        import_max_kw: float,
        export_max_kw: float, 
        price_buy: List[float], 
        price_sell: List[float],
        objective_weight: float = 1.0
    ):
        super().__init__(customer_id, asset_id, objective_weight)
        self.export_max_kw = export_max_kw
        self.import_max_kw = import_max_kw
        self.price_buy = price_buy
        self.price_sell = price_sell

    def register_variables(self, m):
        """Register grid variables and tariff parameters."""
        # Main bidirectional grid power (Positive = Import, Negative = Export)
        setattr(m, f'p_grid_{self.asset_id}', Var(m.T, domain=Reals))
        
        # Unidirectional variables for pricing
        setattr(m, f'p_grid_buy_{self.asset_id}', Var(m.T, domain=NonNegativeReals))
        setattr(m, f'p_grid_sell_{self.asset_id}', Var(m.T, domain=NonNegativeReals))
        
        # Tariffs as parameters
        setattr(m, f'price_buy_{self.asset_id}', Param(m.T, initialize=lambda m, t: self.price_buy[t]))
        setattr(m, f'price_sell_{self.asset_id}', Param(m.T, initialize=lambda m, t: self.price_sell[t]))

        # Import and export bounds as parameters
        setattr(m, f'import_kw_{self.asset_id}', Param(initialize=self.import_max_kw))
        setattr(m, f'export_kw_{self.asset_id}', Param(initialize=self.export_max_kw))

    def register_constraints(self, m):
        """Register grid constraints."""
        # Fetch variables
        p_grid = getattr(m, f'p_grid_{self.asset_id}')
        p_buy = getattr(m, f'p_grid_buy_{self.asset_id}')
        p_sell = getattr(m, f'p_grid_sell_{self.asset_id}')
        
        # Fetch bound parameters
        import_limit = getattr(m, f'import_kw_{self.asset_id}')
        export_limit = getattr(m, f'export_kw_{self.asset_id}')

        # 1. Grid Split Rule: p_grid = import - export
        def grid_split_rule(m, t):
            return p_grid[t] == p_buy[t] - p_sell[t]
            
        setattr(m, f'grid_split_{self.asset_id}', Constraint(m.T, rule=grid_split_rule))

        # 2. Import Maximum Limit
        def import_limit_rule(m, t):
            return p_buy[t] <= import_limit
            
        setattr(m, f'import_limit_{self.asset_id}', Constraint(m.T, rule=import_limit_rule))

        # 3. Export Maximum Limit
        def export_limit_rule(m, t):
            return p_sell[t] <= export_limit
            
        setattr(m, f'export_limit_{self.asset_id}', Constraint(m.T, rule=export_limit_rule))
        
    def register_objectives(self, m):
        """Calculate the energy cost/revenue from the grid."""
        p_buy = getattr(m, f'p_grid_buy_{self.asset_id}')
        p_sell = getattr(m, f'p_grid_sell_{self.asset_id}')
        price_buy = getattr(m, f'price_buy_{self.asset_id}')
        price_sell = getattr(m, f'price_sell_{self.asset_id}')
        
        # Cost = (Power Bought * Buy Price) - (Power Sold * Sell Price)
        return sum((price_buy[t] * p_buy[t] - price_sell[t] * p_sell[t]) * m.delta_t for t in m.T)

    def get_results(self, m) -> Dict[str, Any]:
        p_grid = getattr(m, f'p_grid_{self.asset_id}', None)
        if p_grid is not None:
            return {'p_grid': [value(p_grid[t]) for t in m.T]}
        return {}