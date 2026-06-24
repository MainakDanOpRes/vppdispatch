from typing import Annotated, List

from pydantic import BaseModel, Field

from .timeseries import CustomerTimeSeries


class LiveCustomerInput(BaseModel):
    customer_id: str
    pv_kw: Annotated[List[float], Field(min_length=1)]
    fixed_load_kw: Annotated[List[float], Field(min_length=1)]
    price_buy: Annotated[List[float], Field(min_length=1)]
    price_sell: Annotated[List[float], Field(min_length=1)]

    def to_timeseries(self) -> CustomerTimeSeries:
        return CustomerTimeSeries(
            pv_kw=self.pv_kw,
            fixed_load_kw=self.fixed_load_kw,
            price_buy=self.price_buy,
            price_sell=self.price_sell,
        )
class BatchDispatchInput(BaseModel):
    customers: List[LiveCustomerInput]