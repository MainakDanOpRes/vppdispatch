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
        self.objective_weight = objective_weight  # NEW

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