# src/vpp_dispatch/services/batch_dispatch.py

from concurrent.futures import ThreadPoolExecutor

from vpp_dispatch.services.dispatch_service import run_single_customer_dispatch
from vpp_dispatch.models.schemas import LiveCustomerInput

def run_batch_dispatch(payloads: list[dict], max_workers: int = 32):
    results = {}

    def worker(payload):
        data = LiveCustomerInput(**payload)
        ts = data.to_timeseries()
        res = run_single_customer_dispatch(data.customer_id, ts)
        return data.customer_id, res

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for customer_id, res in pool.map(worker, payloads):
            results[customer_id] = res

    return results
from vpp_dispatch.models.timeseries import CustomerTimeSeries
from vpp_dispatch.models.assets.pv import PVAsset
from vpp_dispatch.models.assets.battery import BatteryAsset
from vpp_dispatch.models.assets.flex_load import FlexLoadAsset
from vpp_dispatch.models.constraints.power_balance import PowerBalanceConstraint
from vpp_dispatch.models.objectives.cost_minimisation import CostObjective
from vpp_dispatch.optimisation.model_builder import ModelBuilder
from vpp_dispatch.optimisation.solver_manager import SolverManager
from vpp_dispatch.optimisation.heuristics import HeuristicFallback

def run_single_customer_dispatch(customer_id: str, ts: CustomerTimeSeries):
    T = ts.T
    delta_t = 1.0

    pv = PVAsset(customer_id, ts.pv_kw)
    battery = BatteryAsset(
        customer_id,
        capacity_kwh=10.0,
        p_charge_max_kw=5.0,
        p_discharge_max_kw=5.0,
        soc_min=1.0,
        soc_max=9.0,
        eff_charge=0.95,
        eff_discharge=0.95,
        soc_initial=5.0,
    )
    flex = FlexLoadAsset(
        customer_id,
        name="EV",
        p_min_kw=0.0,
        p_max_kw=7.0,
        energy_required_kwh=14.0,
        time_window=(10, 20),
    )

    pb = PowerBalanceConstraint(ts)
    obj = CostObjective(batt_degradation_cost_per_kwh=0.01)

    builder = ModelBuilder([pv, battery, flex], pb, obj)
    model = builder.build(T, delta_t)

    solver = SolverManager("highs", time_limit_sec=3)

    try:
        model = solver.solve(model)
        return {
            "p_grid": [model.p_grid[t].value for t in model.T],
            "p_ch": [model.p_ch[t].value for t in model.T],
            "p_dis": [model.p_dis[t].value for t in model.T],
            "soc": [model.soc[t].value for t in model.T],
            "flex_ev": [model.flex[0, t].value for t in model.T],
            "objective": model.total_cost(),
            "fallback": False,
        }
    except Exception:
        hf = HeuristicFallback()
        res = hf.run(ts, battery, flex)
        return {
            "p_grid": [],
            "p_ch": res["p_ch"],
            "p_dis": res["p_dis"],
            "soc": res["soc"],
            "flex_ev": res["flex"],
            "objective": None,
            "fallback": True,
        }
