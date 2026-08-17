from typing import List, Dict, Any
from pyomo.environ import Var, Reals, NonNegativeReals, Constraint, Param, value, Binary
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
        setattr(m, f'p_grid_{self.var_id}', Var(m.T, domain=Reals))
        
        # Unidirectional variables for pricing
        setattr(m, f'p_grid_buy_{self.var_id}', Var(m.T, domain=NonNegativeReals))
        setattr(m, f'p_grid_sell_{self.var_id}', Var(m.T, domain=NonNegativeReals))

        # binary variables for nonsimultaneous import export
        setattr(m, f'u_grid_buy_{self.var_id}', Var(m.T, domain=Binary))
        
        # Tariffs as parameters
        setattr(m, f'price_buy_{self.var_id}', Param(m.T, initialize=lambda m, t: self.price_buy[t]))
        setattr(m, f'price_sell_{self.var_id}', Param(m.T, initialize=lambda m, t: self.price_sell[t]))

        # Import and export bounds as parameters
        setattr(m, f'import_kw_max_{self.var_id}', Param(initialize=self.import_max_kw))
        setattr(m, f'export_kw_max_{self.var_id}', Param(initialize=self.export_max_kw))

    def register_constraints(self, m):
        """Register grid constraints."""
        # Fetch variables
        p_grid = getattr(m, f'p_grid_{self.var_id}')
        p_buy = getattr(m, f'p_grid_buy_{self.var_id}')
        p_sell = getattr(m, f'p_grid_sell_{self.var_id}')
        u_buy = getattr(m, f'u_grid_buy_{self.var_id}')
        
        # Fetch bound parameters
        import_limit = getattr(m, f'import_kw_max_{self.var_id}')
        export_limit = getattr(m, f'export_kw_max_{self.var_id}')

        # 1. Grid Split Rule: p_grid = import - export
        def grid_split_rule(m, t):
            return p_grid[t] == p_buy[t] - p_sell[t]
            
        setattr(m, f'grid_split_{self.var_id}', Constraint(m.T, rule=grid_split_rule))

        # 2. Import Maximum Limit
        def import_limit_rule(m, t):
            return p_buy[t] <= import_limit*u_buy[t]
            
        setattr(m, f'import_limit_{self.var_id}', Constraint(m.T, rule=import_limit_rule))

        # 3. Export Maximum Limit
        def export_limit_rule(m, t):
            return p_sell[t] <= export_limit*(1-u_buy[t])
            
        setattr(m, f'export_limit_{self.var_id}', Constraint(m.T, rule=export_limit_rule))
        
    def register_objectives(self, m):
        """Calculate the energy cost/revenue from the grid."""
        p_buy = getattr(m, f'p_grid_buy_{self.var_id}')
        p_sell = getattr(m, f'p_grid_sell_{self.var_id}')
        price_buy = getattr(m, f'price_buy_{self.var_id}')
        price_sell = getattr(m, f'price_sell_{self.var_id}')
        
        # Cost = (Power Bought * Buy Price) - (Power Sold * Sell Price)
        return sum((price_buy[t] * p_buy[t] - price_sell[t] * p_sell[t]) * m.delta_t for t in m.T)

    def get_results(self, m) -> Dict[str, Any]:
        p_grid = getattr(m, f'p_grid_{self.var_id}', None)
        if p_grid is not None:
            return {'p_grid': [value(p_grid[t]) for t in m.T]}
        return {}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize Grid asset to dictionary."""
        d = super().to_dict()
        d.update({
            f"grid_import_max_kw": self.import_max_kw,
            f"grid_export_max_kw": self.export_max_kw,
            f"grid_price_buy": self.price_buy,
            f"grid_price_sell": self.price_sell,
        })
        return d