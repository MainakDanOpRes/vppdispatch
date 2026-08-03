from typing import List
from pyomo.environ import Objective, minimize

class CostObjective:
    """Universal cost aggregator for all VPP assets."""
    
    def __init__(self, assets: List = None, include_asset_costs: bool = True):
        self.assets = assets or []
        self.include_asset_costs = include_asset_costs

    def register(self, m):
        expr = 0.0
        
        if self.include_asset_costs:
            for asset in self.assets:
                if not hasattr(asset, 'objective_weight') or asset.objective_weight == 0.0:
                    continue 
                
                if hasattr(asset, 'get_objective_cost'):
                    asset_cost_expr = asset.get_objective_cost(m)
                    if asset_cost_expr != 0.0:
                        expr += (asset_cost_expr * asset.objective_weight)

        # Register the final aggregated objective
        m.total_cost = Objective(expr=expr, sense=minimize)