"""
Base asset class for VPP Dispatch
"""

from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseAsset(ABC):
    """Abstract base class for all assets."""

    def __init__(self, customer_id: str, asset_id: str, 
                 objective_weight: float = 1.0):
        self.customer_id = customer_id
        self.asset_id = asset_id
        self.objective_weight = objective_weight

    @property
    def var_id(self) -> str:
        """
        Identifier used ONLY for naming Pyomo model attributes
        (Var/Param/Constraint), e.g. f'p_grid_{asset.var_id}'.
 
        Combines customer_id + asset_id so two customers reusing the same
        asset_id convention (e.g. both using "battery_1") never collide as
        attribute names on a shared model - which matters the moment more
        than one customer's assets are registered onto the same
        ConcreteModel (centralized/PCC dispatch). In single-customer
        dispatch this is a no-op in effect (still unique), so nothing
        about the existing single-customer flow changes behavior.
 
        Never use var_id for anything user-facing (to_dict, get_results,
        API responses) - asset_id is the identifier callers gave you and
        must be echoed back unchanged.
        """
        return f"{self.customer_id}_{self.asset_id}"

    @property
    def result_key(self) -> str:
        """
        Identifier used as the dict key when SAVING/merging results (e.g.
        results['assets'][asset.result_key] = {...}, or a DB row key).
 
        Same customer_id+asset_id combination as var_id, kept as a
        separate property because the two answer different questions
        (Pyomo naming vs. results storage) even though today they compute
        the same string - callers should use whichever name matches their
        intent, not assume they'll always be identical.
        """
        return f"{self.customer_id}_{self.asset_id}"

    @abstractmethod
    def register_variables(self, m):
        """Register Pyomo variables for this asset."""
        ...

    @abstractmethod
    def register_constraints(self, m):
        """Register Pyomo constraints for this asset."""
        ...

    def register_objectives(self, m):
        """Return the Pyomo expression for this asset's specific objective/cost."""
        return 0.0

    def get_results(self, m) -> Dict[str, Any]:
        """Extract results for this asset from the solved model."""
        return {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert asset configuration to dictionary."""
        return {
            'asset_id': self.asset_id,
            'customer_id': self.customer_id,
            'type': self.__class__.__name__
        }