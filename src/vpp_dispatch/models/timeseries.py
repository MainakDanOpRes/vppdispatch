
"""
Time series data model for VPP Dispatch
"""

from typing import Sequence


class CustomerTimeSeries:
    def __init__(
        self,
        pv_kw: Sequence[float],
        fixed_load_kw: Sequence[float],
        price_buy: Sequence[float],
        price_sell: Sequence[float],
    ):
        assert len(pv_kw) == len(fixed_load_kw) == len(price_buy) == len(price_sell)
        self.pv_kw = list(pv_kw)
        self.fixed_load_kw = list(fixed_load_kw)
        self.price_buy = list(price_buy)
        self.price_sell = list(price_sell)

    @property
    def T(self) -> int:
        """Number of time periods."""
        return len(self.pv_kw)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "pv_kw": self.pv_kw,
            "fixed_load_kw": self.fixed_load_kw,
            "price_buy": self.price_buy,
            "price_sell": self.price_sell,
        }
