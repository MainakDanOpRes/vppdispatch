"""
VPP Dispatch API
-----------------
FastAPI application exposing the vpp_dispatch optimization engine
(Pyomo + HiGHS) over HTTP.

Endpoints:
    GET  /                      Service info
    GET  /health                Health check
    GET  /solvers                Available/configured solvers
    POST /dispatch               Legacy single-customer dispatch (default asset set)
    POST /dispatch/multi-asset   Full multi-asset dispatch for one customer
    POST /dispatch/batch         Multi-asset dispatch for several customers in parallel

Run locally:
    uvicorn vpp_dispatch.api:app --reload --port 8000
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .models.schemas import CustomerConfig, LiveCustomerInput
from .optimisation.solver_manager import SolverManager
from .services.dispatch_service import (
    run_dispatch_from_live_input,
    run_multi_asset_dispatch,
    run_batch_dispatch,
    create_optimization_summary,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="VPP Dispatch API",
    description="Optimal dispatch scheduling for Virtual Power Plant assets "
                 "(PV, battery, flexible/fixed load, grid) via Pyomo + HiGHS.",
    version="0.2.0",
)

# Wide-open CORS so the Streamlit dashboard (running on a different origin/port,
# and in Docker on a different host entirely) can call this API directly from
# the browser as well as from the Streamlit server process itself.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class LegacyDispatchResponse(BaseModel):
    p_grid: List[float]
    p_ch: List[float]
    p_dis: List[float]
    soc: List[float]
    flex_ev: List[float]
    pv_1: List[float]
    objective: float
    status: Dict[str, Any]


class MultiAssetDispatchResponse(BaseModel):
    results: Dict[str, Any]
    status: Dict[str, Any]
    summary: Dict[str, Any]


class BatchDispatchRequest(BaseModel):
    customers: List[CustomerConfig] = Field(..., description="One config per customer")
    batt_degradation_cost: float = Field(0.01, ge=0.0)


class BatchDispatchResponse(BaseModel):
    results: Dict[str, Any]
    overall_status: Dict[str, Any]


# ---------------------------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------------------------


@app.get("/")
def root():
    return {
        "service": "VPP Dispatch API",
        "status": "ok",
        "docs": "/docs",
        "endpoints": [
            "/dispatch",
            "/dispatch/multi-asset",
            "/dispatch/batch",
            "/solvers",
            "/health",
        ],
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/solvers")
def list_solvers():
    """Report which optimization solvers are actually available in this environment."""
    manager = SolverManager()
    available = manager.get_available_solvers()
    return {
        "available": available,
        "primary": "highs",
        "fallback_order": manager.fallback_solvers,
    }


# ---------------------------------------------------------------------------
# Legacy single-customer dispatch
# ---------------------------------------------------------------------------


@app.post("/dispatch", response_model=LegacyDispatchResponse)
def dispatch(payload: LiveCustomerInput):
    """
    Legacy single-customer dispatch with a DEFAULT asset fleet
    (1 PV, 1 battery, 1 EV-style flex load, 1 grid connection).

    Matches the historical contract used by the original streamlit_app.py:
    input  = {customer_id, pv_kw, fixed_load_kw, price_buy, price_sell}
    output = {p_grid, p_ch, p_dis, soc, flex_ev, pv_1, objective}
    """
    try:
        results, status = run_dispatch_from_live_input(payload)
    except Exception as e:
        logger.exception("Legacy dispatch failed")
        raise HTTPException(status_code=500, detail=str(e))

    if not results:
        raise HTTPException(status_code=422, detail=status.get("error", "Dispatch failed"))

    return LegacyDispatchResponse(
        p_grid=results.get("p_grid", []),
        p_ch=results.get("p_ch", []),
        p_dis=results.get("p_dis", []),
        soc=results.get("soc", []),
        flex_ev=results.get("flex_ev", []),
        pv_1=results.get("pv_1", []),
        objective=results.get("objective", 0.0),
        status=status,
    )


# ---------------------------------------------------------------------------
# Multi-asset dispatch (main endpoint)
# ---------------------------------------------------------------------------


@app.post("/dispatch/multi-asset", response_model=MultiAssetDispatchResponse)
def dispatch_multi_asset(
    config: CustomerConfig,
    batt_degradation_cost: float = 0.01,
):
    """
    Full multi-asset dispatch for a single customer with an arbitrary set of
    PV / battery / flexible load / fixed load / grid assets.
    """
    try:
        results, status = run_multi_asset_dispatch(
            customer_config=config,
            batt_degradation_cost=batt_degradation_cost,
        )
    except Exception as e:
        logger.exception("Multi-asset dispatch failed")
        raise HTTPException(status_code=500, detail=str(e))

    if not results:
        raise HTTPException(status_code=422, detail=status.get("error", "Dispatch failed"))

    summary = create_optimization_summary(results)
    return MultiAssetDispatchResponse(results=results, status=status, summary=summary)


# ---------------------------------------------------------------------------
# Batch dispatch
# ---------------------------------------------------------------------------


@app.post("/dispatch/batch", response_model=BatchDispatchResponse)
def dispatch_batch(payload: BatchDispatchRequest):
    """
    Run multi-asset dispatch for several customers in parallel.
    """
    try:
        batch_results, overall_status = run_batch_dispatch(
            customer_configs=payload.customers,
            batt_degradation_cost=payload.batt_degradation_cost,
        )
    except Exception as e:
        logger.exception("Batch dispatch failed")
        raise HTTPException(status_code=500, detail=str(e))

    return BatchDispatchResponse(results=batch_results, overall_status=overall_status)