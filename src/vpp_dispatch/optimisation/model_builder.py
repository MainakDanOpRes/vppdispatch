"""
Model Builder for VPP Dispatch Optimization
Builds Pyomo optimization models from asset configurations.
"""

from typing import List, Optional
from pyomo.environ import ConcreteModel, Set, RangeSet
import logging

from ..models.assets.base_asset import BaseAsset
from ..models.constraints.power_balance import PowerBalanceConstraint
from ..models.objectives.cost_minimisation import CostObjective

logger = logging.getLogger(__name__)

class ModelBuilder:
    """
    Builds Pyomo optimization models for VPP dispatch.
    Supports dynamic asset registration and objective aggregation.
    """

    def __init__(self, 
                 assets: List[BaseAsset], 
                 power_balance: PowerBalanceConstraint, 
                 objective: CostObjective,
                 delta_t: float = 1.0):

        """
        Initialize model builder.

        Args:
            assets: List of asset objects (PVAsset, BatteryAsset, etc.)
            power_balance: PowerBalanceConstraint object
            objective: Objective function object
            delta_t: Time step duration in hours (default: 1.0)
        """

        self.assets = assets
        self.power_balance = power_balance
        self.objective = objective
        self.delta_t = delta_t

    def build(self, T: int, delta_t: Optional[float] = None) -> ConcreteModel:
        """
        Build the optimization model.

        Args:
            T: Number of time periods
            delta_t: Time step duration in hours

        Returns:
            ConcreteModel: Built Pyomo model ready for solving
        """
        if delta_t is not None:
            self.delta_t = delta_t

        m = ConcreteModel()

        # Time index
        m.T = RangeSet(0, T - 1)
        m.delta_t = self.delta_t

        

        # Register variables for all assets
        for asset in self.assets:
            try: 
                asset.register_variables(m)
                logger.debug(f"Registered variables for {asset.__class__.__name__} ({asset.asset_id})")
            except Exception as e:
                logger.error(f"Error registering variables for asset {asset.asset_id}: {e}")
                raise

        # register constraints from all assets
        for asset in self.assets:
            try:
                asset.register_constraints(m)
                logger.debug(f"Registered constraints for {asset.__class__.__name__}({asset.asset_id})")
            except Exception as e:
                logger.error(f"Error registering constraints for {asset.asset_id}: {e}")
                raise
        # Register power balance variables and parameters
        # Must happen before constraints so balance rule can reference them
        try:
            self.power_balance.register_variables_and_params(m)
        except Exception as e:
            logger.error(f"Error registering power balance variables: {e}")
            raise


        # Register power balance constraint
        try:
            self.power_balance.register(m)
        except Exception as e:
            logger.error(f"Error registering power balance constraint: {e}")
            raise

        # Register objective function
        try:
            self.objective.register(m)
            logger.debug("Registered objective function")
        except Exception as e:
            logger.error(f"Error registering objective function: {e}")
            raise

        logger.info(f"Model built successfully with {len(self.assets)} assets and {T} time periods")
        return m