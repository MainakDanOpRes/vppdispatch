from typing import Callable, List
from pyomo.environ import Constraint

class GenericSubsetConstraint:
    """A generalized wrapper for applying custom constraints to subsets of assets."""

    def __init__(self, name: str, assets: List, rule_func: Callable, time_dynamic: bool = True):
        """
        Args:
            name: The attribute name for the constraint on the Pyomo model.
            assets: The subset of assets this constraint applies to.
            rule_func: The callable returning a Pyomo expression.
            time_dynamic: If True, rule_func takes (m, t, assets). 
                          If False, rule_func takes (m, assets).
        """
        self.name = name
        self.assets = assets
        self.rule_func = rule_func
        self.time_dynamic = time_dynamic

    def register(self, m):
        """Registers the constraint on the Pyomo model based on its time dependency."""
        
        if self.time_dynamic:
            # Indexed constraint: evaluated for every time step 't'
            def wrapped_rule_indexed(m, t):
                return self.rule_func(m, t, self.assets)
                
            setattr(m, self.name, Constraint(m.T, rule=wrapped_rule_indexed))
            
        else:
            # Scalar constraint: evaluated exactly once
            def wrapped_rule_scalar(m):
                return self.rule_func(m, self.assets)
                
            setattr(m, self.name, Constraint(rule=wrapped_rule_scalar))