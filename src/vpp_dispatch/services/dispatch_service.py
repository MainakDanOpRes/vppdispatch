# src/vpp_dispatch/services/dispatch_service.py

from pyomo.environ import value
from vpp_dispatch.models.timeseries import CustomerTimeSeries
from vpp_dispatch.models.assets.pv import PVAsset
from vpp_dispatch.models.assets.battery import BatteryAsset
from vpp_dispatch.models.assets.flex_load import FlexLoadAsset
from vpp_dispatch.models.constraints.power_balance import PowerBalanceConstraint
from vpp_dispatch.models.objectives.cost_minimisation import CostObjective
from vpp_dispatch.optimisation.model_builder import ModelBuilder
from vpp_dispatch.optimisation.solver_manager import SolverManager

def run_single_customer_dispatch(customer_id: str, ts: CustomerTimeSeries):
    T = len(ts.pv_kw)
    delta_t = 1.0  # hours, for example

    # assets
    pv = PVAsset(customer_id, pv_profile_kw=ts.pv_kw)
    battery = BatteryAsset(
        customer_id=customer_id,
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
        customer_id=customer_id,
        name="EV",
        p_min_kw=0.0,
        p_max_kw=7.0,
        energy_required_kwh=14.0,
        time_window=(10, 20),
    )

    # constraints + objective
    pb = PowerBalanceConstraint(ts_data=ts)
    obj = CostObjective(batt_degradation_cost_per_kwh=0.01)

    builder = ModelBuilder(assets=[pv, battery, flex], power_balance=pb, objective=obj)
    model = builder.build(T=T, delta_t=delta_t)

    solver = SolverManager(solver_name="highs", time_limit_sec=3)
    model = solver.solve(model)

    # extract results
    p_grid = [model.p_grid[t].value for t in model.T]
    p_ch = [model.p_ch[t].value for t in model.T]
    p_dis = [model.p_dis[t].value for t in model.T]
    soc = [model.soc[t].value for t in model.T]
    flex_ev = [model.flex[t].value for t in model.T]  # FlexLoadAsset is 1-D: flex[t]

    return {
        "p_grid": p_grid,
        "p_ch": p_ch,
        "p_dis": p_dis,
        "soc": soc,
        "flex_ev": flex_ev,
        "objective": value(model.total_cost),  # Pyomo Objective needs value()
    }