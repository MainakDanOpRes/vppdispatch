"""
Generator Asset model for VPP Dispatch
"""

from typing import Dict, Any
from pyomo.environ import Var, Binary, NonNegativeReals, Constraint

from .base_asset import BaseAsset

class GeneratorAsset(BaseAsset):
    """Generator asset model"""
    def __init__(self, customer_id: str, asset_id: str,
                 p_max_kw: float, p_min_kw: float, min_up_time: int,
                 min_down_time: int, ramp_rate: float, 
                 marginal_cost_per_kw: float, start_up_cost: float,
                 shut_down_cost: float, objective_weight = 1):
        super().__init__(customer_id, asset_id, objective_weight)
