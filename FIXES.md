# VPP Dispatch — Bug Fixes, API, Dashboard & Tests

This document summarizes everything added/fixed on top of the original
`MainakDanOpRes/vppdispatch` repository.

## What was added

- **`src/vpp_dispatch/api.py`** — the FastAPI app referenced by the README and
  `Dockerfile` (`vpp_dispatch.api:app`) but never actually written. Exposes:
  - `GET /`, `GET /health`, `GET /solvers`
  - `POST /dispatch` — legacy single-customer dispatch (default fleet)
  - `POST /dispatch/multi-asset` — arbitrary asset fleet for one customer
  - `POST /dispatch/batch` — multiple customers dispatched in parallel
- **`streamlit_app.py`** (rewritten) — three-mode dashboard: Quick Dispatch,
  Multi-Asset Builder, Batch Dispatch. Talks to the API via `BACKEND_URL`.
- **`Dockerfile.streamlit`** + **`docker-compose.yml`** — run backend (8000)
  and dashboard (8501) together with `docker compose up --build`.
- **`tests/test_integration/`** — 25 new integration tests exercising real
  combinations of assets through the solver (not mocked):
  - `test_power_balance_integration.py` — builds Pyomo models directly from
    asset combinations (PV+battery+grid, all 3 flex-load modes, full 5-asset
    fleet) and checks power balance, SOC bounds, and price-sensitivity.
  - `test_dispatch_service_integration.py` — exercises the public service
    functions (`run_dispatch_from_live_input`, `run_multi_asset_dispatch`,
    `run_batch_dispatch`) end to end, including a regression test for the
    batch-dispatch deadlock.
  - `test_api_integration.py` — the same paths through the actual HTTP
    contract via FastAPI's `TestClient`.
- **`examples/*.ipynb`** — three runnable Jupyter notebooks (single-customer,
  multi-asset fleet incl. all 3 flex-load modes, batch + API). All three were
  executed end-to-end with `jupyter execute` to confirm they actually run.

## Bugs found and fixed (discovered by actually running the code)

The optimization engine did not work at all before these fixes — every
dispatch call failed. Fixed, in the order found:

1. **`models/constraints/power_balance.py`** — comparing a Pyomo expression
   with Python's `==`/`bool()` inside an `if` raised `PyomoException` on
   every call. Fixed with an `isinstance` guard.
2. **`models/constraints/power_balance.py`** — fixed loads were looked up as
   `fixed_load_{id}`, but `FixedLoadAsset` registers itself as `fixed_{id}`,
   so fixed loads were silently excluded from the power balance.
3. **`models/objectives/cost_minimisation.py`** (two places) — checked
   `hasattr(asset, 'get_objective_cost')`, a method no asset defines (they
   all define `register_objectives`). The objective was **always 0**
   regardless of price, i.e. dispatch never actually optimized for cost.
4. **`optimisation/solver_manager.py`** — `solver.set_options(dict)` isn't
   valid for this Pyomo/HiGHS version; switched to `solver.options.update()`.
5. **`optimisation/solver_manager.py`** — `results.solver.time` doesn't exist
   on this Pyomo build and raised after a successful solve; read
   `wallclock_time` defensively instead.
6. **`optimisation/solver_manager.py`** — Pyomo's HiGHS interface uses a
   shared, non-thread-safe `TeeStream`, so `batch_dispatch.py`'s
   `ThreadPoolExecutor` deadlocked/crashed whenever two customers solved
   concurrently. Serialized just the `solver.solve()` call behind a lock.
7. **`models/schemas.py`** — `AssetConfig`'s per-field validators inspected
   *other* fields via `info.data`, which in Pydantic v2 only contains fields
   validated so far (declaration order). A field declared earlier (e.g.
   `capacity_kwh`) could never see one declared later (e.g.
   `p_charge_max_kw`), so valid battery configs were rejected. Replaced with
   a single `model_validator(mode='after')`.
8. **`models/schemas.py`** — `is_continuous`/`is_shiftable`/`is_on_off`/
   `load_profile` were referenced by `asset_factory.py` but never declared
   on `AssetConfig`, so creating any `flex_load` asset via the API/config
   path raised `AttributeError`. Added the fields.
9. **`services/asset_factory.py`** — `asset_config.is_continuous or True`
   always evaluated to `True` regardless of what the caller set (`False or
   True == True` in Python), so on/off and shiftable flex loads could never
   actually be selected. Also made `is_continuous` auto-infer correctly when
   left unset alongside an explicit `is_on_off`/`is_shiftable`.
10. **`models/assets/flex_load.py`** — a stray `[cite: 2]` (apparent copy/paste
    artifact) after `d.update(...)` in `to_dict()` raised `NameError` for any
    on/off flex load.
11. **`optimisation/heuristics.py`** — `HeuristicFallback.run()` took a single
    `battery_conf` argument, but `dispatch_service.py` calls it with the
    *full asset list* (`hf.run(ts, assets)`). The solver-failure fallback
    path crashed instead of ever falling back. Rewrote `run()` to accept the
    asset list and extract battery/flex assets from it.
12. **`tests/conftest.py`** (previously-dead fixtures, now exercised) —
    `cost_objective` fixture passed a nonexistent `batt_degradation_cost_per_kwh`
    kwarg; `--run-solver-tests` was referenced but never registered via
    `pytest_addoption`, which raises the instant any test uses the
    `requires_solver` marker. Both fixed.
13. **`models/objectives/cost_minimisation.py`** — added a warning log when
    `CostObjective(include_asset_costs=True)` is constructed without
    `assets`, since this silently produces a price-insensitive, always-zero
    objective (an easy mistake — I made it myself while writing the tests
    above).

All 66 tests pass (`pytest tests/ -q`): 41 original unit tests + 25 new
integration tests, including live HiGHS solves.

## Running everything

```bash
# Backend + dashboard together
docker compose up --build
# API: http://localhost:8000/docs
# Dashboard: http://localhost:8501

# Or locally without Docker
uv sync
uv run uvicorn vpp_dispatch.api:app --reload --port 8000
BACKEND_URL=http://localhost:8000 uv run streamlit run streamlit_app.py

# Tests
uv run pytest tests/ -v

# Notebooks
uv run jupyter lab examples/
```
