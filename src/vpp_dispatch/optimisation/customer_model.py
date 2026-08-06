
"""
Customer-specific model components for VPP Dispatch.
Handles customer-level constraints and objectives.
"""

from pyomo.environ import ConcreteModel, RangeSet, Var, Constraint, Param
from typing import List, Optional, Dict, Any
from ..models.timeseries import CustomerTimeSeries
from ..models.assets import PVAsset, BatteryAsset, FlexLoadAsset, FixedLoadAsset, GridAsset


class CustomerModel:
    """
    Customer level model that can be extended with customer-specific constraints.
    This class provides a foundation for building customer-specific optimization models.
    """

    def __init__(
            self,
            customer_id: str,
            ts_data: CustomerTimeSeries,
            assets: List = None,
            additional_constraints: Optional[List] = None
    ):
        """
        Initialize customer model.

        Args:
            customer_id: Unique identifier for the customer
            ts_data: Time series data
            assets: List of asset objects
            additional_constraints: List of additional constraint objects
        """

        self.customer_id = customer_id
        self.ts_data = ts_data
        self.assets = assets or []
        self.additional_constraints = additional_constraints or []

    def build_base_model(self, T: int = None, delta_t: float = 1.0) -> ConcreteModel:
        """
        Build the base pyomo model with time index and delta_t

        Args:
            T: Number of time periods (defaults to ts_data.T)
            delta_t: Time step duration in hours

        Returns:
            ConcreteModel with basic time structure
        """

        T = T or self.ts_data.T
        m = ConcreteModel()
        m.T = RangeSet(0, T-1)
        m.delta_t = delta_t
        return m 

    def add_customer_constraints(self, m):
        """
        Add customer-specific constraints to the model.
        Override this method in subclasses to add custom constraints.
        """
        # this base class does nothing - override in subclasses
        pass

    def add_customer_objective_terms(self, m) -> float:
        """
        Add customer-specific objective terms.
        Override this method in subclasses to customize the objective.

        Args:
            m: Pyomo model

        Returns:
            Expression to add to the objective function
        """
        return 0.0
    def get_asset_by_type(self, asset_type: str) -> List:
        """Get all assets of a specific type."""
        from ..models.schemas import AssetType
        return [a for a in self.assets if a.__class__.__name__ == asset_type]

    def get_asset_by_id(self, asset_id: str):
        """Get asset by ID."""
        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset
        return None