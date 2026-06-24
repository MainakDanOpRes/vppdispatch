

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from vpp_dispatch.models.schemas import LiveCustomerInput, BatchDispatchInput
from vpp_dispatch.services.dispatch_service import run_single_customer_dispatch
import logging
logger = logging.getLogger("uvicorn")

app = FastAPI(
    title="VPP Dispatch API",
    description="Real-time optimisation API for Virtual Power Plant dispatch.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)


@app.get("/")
def root():
    return {
        "message": "VPP Dispatch API is running",
        "endpoints": ["/dispatch"],
    }


@app.get("/dispatch")
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
    logger.info(f"Dispatch result for {payload.customer_id}: {result}")
    return result

@app.get("/dispatch/batch")
@app.post("/dispatch/batch")
def dispatch_batch(payload: BatchDispatchInput):
    results = {}
    for customer in payload.customers:
        ts = customer.to_timeseries()
        results[customer.customer_id] = run_single_customer_dispatch(customer.customer_id, ts)
    return results

@app.get("/dispatch/test")
def test_dispatch():
    # Provide dummy data here to see if the engine runs
    dummy_payload = LiveCustomerInput(
        customer_id="TEST",
        pv_kw=[0.0] * 12,
        fixed_load_kw=[1.0] * 12,
        price_buy=[0.2] * 12,
        price_sell=[0.1] * 12
    )
    ts = dummy_payload.to_timeseries()
    result = run_single_customer_dispatch(dummy_payload.customer_id, ts)
    return result