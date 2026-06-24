

from fastapi import FastAPI
from vpp_dispatch.models.schemas import LiveCustomerInput, BatchDispatchInput
from vpp_dispatch.services.dispatch_service import run_single_customer_dispatch

app = FastAPI(
    title="VPP Dispatch API",
    description="Real-time optimisation API for Virtual Power Plant dispatch.",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "message": "VPP Dispatch API is running",
        "endpoints": ["/dispatch"],
    }


@app.post("/dispatch")
def dispatch_customer(payload: LiveCustomerInput):
    """
    Run a single-customer optimisation.

    Request body:
    {
      "customer_id": "C1",
      "pv_kw": [...],
      "fixed_load_kw": [...],
      "price_buy": [...],
      "price_sell": [...]
    }
    """
    ts = payload.to_timeseries()
    result = run_single_customer_dispatch(payload.customer_id, ts)
    print(result)
    return result

@app.post("/dispatch/batch")
def dispatch_batch(payload: BatchDispatchInput):
    results = {}
    for customer in payload.customers:
        ts = customer.to_timeseries()
        results[customer.customer_id] = run_single_customer_dispatch(customer.customer_id, ts)
    return results
