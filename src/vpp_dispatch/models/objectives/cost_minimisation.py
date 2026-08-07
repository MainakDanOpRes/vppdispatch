from typing import List
from pyomo.environ import Objective, minimize
import logging

logger = logging.getLogger(__name__)

class CostObjective:
    """Universal cost aggregator for all VPP assets."""
    
    def __init__(self, assets: List = None, include_asset_costs: bool = True):
        self.assets = assets or []
        self.include_asset_costs = include_asset_costs
        if include_asset_costs and not self.assets:
            # Common footgun: forgetting to pass the same `assets` list used to
            # build the rest of the model. register() below then has nothing to
            # iterate over, silently producing an always-zero, price-insensitive
            # objective (the solver will report "optimal" for any feasible point).
            logger.warning(
                "CostObjective created with include_asset_costs=True but no assets "
                "were passed in - the resulting objective will always be 0.0 "
                "regardless of price. Pass assets=<same list used to build the model>."
            )

    def register(self, m):
        expr = 0.0
        
        if self.include_asset_costs:
            for asset in self.assets:
                if not hasattr(asset, 'objective_weight') or asset.objective_weight == 0.0:
                    continue 
                
                if hasattr(asset, 'register_objectives'):
                    asset_cost_expr = asset.register_objectives(m)
                    # asset_cost_expr is a plain 0.0 float when an asset has no cost
                    # component, or a Pyomo expression once a Var is involved. Comparing
                    # a Pyomo expression with `==`/bool() raises, so only skip the
                    # plain-float case.
                    is_trivial_zero = isinstance(asset_cost_expr, (int, float)) and asset_cost_expr == 0.0
                    if asset_cost_expr is not None and not is_trivial_zero:
                        expr += (asset_cost_expr * asset.objective_weight)

        # Register the final aggregated objective
        m.total_cost = Objective(expr=expr, sense=minimize)