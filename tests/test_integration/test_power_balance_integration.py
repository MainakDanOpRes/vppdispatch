"""
Integration tests: model_builder + power_balance + cost_objective + solver,
exercised together across combinations of real assets (PV, battery,
flex load, fixed load, grid).

These go one level below dispatch_service - they build and solve the Pyomo
model directly - to pin down exactly how assets interact through the shared
power balance constraint and objective. dispatch_service-level integration
lives in test_dispatch_service_integration.py.

All tests here actually invoke HiGHS, so they're marked `requires_solver`.
"""

import pytest

from src.vpp_dispatch.models.timeseries import CustomerTimeSeries
from src.vpp_dispatch.models.assets import (
    PVAsset,
    BatteryAsset,
    FlexLoadAsset,
    FixedLoadAsset,
    GridAsset,
    GeneratorAsset
)
from src.vpp_dispatch.models.constraints.power_balance import PowerBalanceConstraint
from src.vpp_dispatch.models.objectives.cost_minimisation import CostObjective
from src.vpp_dispatch.optimisation.model_builder import ModelBuilder
from src.vpp_dispatch.optimisation.solver_manager import SolverManager
from pyomo.environ import value as pyo_value

pytestmark = [pytest.mark.integration, pytest.mark.requires_solver]


def _solve(assets, ts, T, delta_t=1.0):
    power_balance = PowerBalanceConstraint(ts_data=ts, assets=assets)
    objective = CostObjective(assets=assets, include_asset_costs=True)
    builder = ModelBuilder(assets=assets, power_balance=power_balance, objective=objective)
    model = builder.build(T=T, delta_t=delta_t)

    manager = SolverManager()
    results, status = manager.solve(model)
    return model, results, status


def _grid_var(model, grid_asset):
    return getattr(model, f"p_grid_{grid_asset.var_id}")


class TestPVBatteryGridIntegration:
    """PV + battery + grid: the battery should arbitrage against price_buy."""

    def test_battery_charges_cheap_discharges_expensive(self):
        T = 6
        ts = CustomerTimeSeries(
            pv_kw=[0, 0, 0, 0, 0, 0],
            fixed_load_kw=[1, 1, 1, 1, 1, 1],
            price_buy=[0.5, 0.5, 0.05, 0.05, 0.5, 0.5],
            price_sell=[0.01] * T,
        )
        battery = BatteryAsset(
            customer_id="c1", asset_id="battery_1",
            capacity_kwh=10, p_charge_max_kw=5, p_discharge_max_kw=5,
            soc_min=0.0, soc_max=1.0, eff_charge=0.95, eff_discharge=0.95,
            soc_initial=0.2,
        )
        grid = GridAsset(
            customer_id="c1", asset_id="grid_1",
            import_max_kw=20, export_max_kw=20,
            price_buy=ts.price_buy, price_sell=ts.price_sell,
        )
        fixed = FixedLoadAsset(customer_id="c1", asset_id="fixed_1", fixed_load_profile_kw=ts.fixed_load_kw)
        assets = [battery, fixed, grid]

        model, results, status = _solve(assets, ts, T)
        assert status["success"] is True

        p_ch = [pyo_value(getattr(model, "p_ch_c1_battery_1")[t]) for t in range(T)]
        p_dis = [pyo_value(getattr(model, "p_dis_c1_battery_1")[t]) for t in range(T)]

        # Cheapest periods (index 2, 3) should see charging; expensive periods
        # (index 0, 1, 4, 5) should never see net charging outweigh discharge.
        assert p_ch[2] > 0 or p_ch[3] > 0
        assert p_dis[0] + p_dis[1] + p_dis[4] + p_dis[5] > 0

    def test_power_balance_holds_exactly(self):
        """For every period, grid import/export must exactly offset load - generation - battery net."""
        T = 5
        ts = CustomerTimeSeries(
            pv_kw=[0, 2, 4, 2, 0],
            fixed_load_kw=[1, 1, 1, 1, 1],
            price_buy=[0.3, 0.3, 0.1, 0.1, 0.3],
            price_sell=[0.05] * T,
        )
        pv = PVAsset(customer_id="c1", asset_id="pv_1", pv_profile_kw=ts.pv_kw)
        battery = BatteryAsset(
            customer_id="c1", asset_id="battery_1",
            capacity_kwh=8, p_charge_max_kw=4, p_discharge_max_kw=4,
            soc_min=0.1, soc_max=0.9, eff_charge=0.9, eff_discharge=0.9,
            soc_initial=0.4,
        )
        fixed = FixedLoadAsset(customer_id="c1", asset_id="fixed_1", fixed_load_profile_kw=ts.fixed_load_kw)
        grid = GridAsset(
            customer_id="c1", asset_id="grid_1",
            import_max_kw=50, export_max_kw=50,
            price_buy=ts.price_buy, price_sell=ts.price_sell,
        )
        generator = GeneratorAsset(
            customer_id="c1", asset_id="gen_1",
            p_min_kw=0, p_max_kw=50, ramp_rate=20,
            min_up_time=3, min_down_time=3,
            marginal_cost_per_kw=1
        )
        assets = [pv, battery, fixed, grid, generator]

        model, results, status = _solve(assets, ts, T)
        assert status["success"] is True

        for t in range(T):
            pv_t = pyo_value(getattr(model, "pv_c1_pv_1")[t])
            fixed_t = pyo_value(getattr(model, "fixed_c1_fixed_1")[t])
            ch_t = pyo_value(getattr(model, "p_ch_c1_battery_1")[t])
            dis_t = pyo_value(getattr(model, "p_dis_c1_battery_1")[t])
            grid_t = pyo_value(getattr(model, "p_grid_c1_grid_1")[t])
            gen_t = pyo_value(getattr(model, "p_gen_c1_gen_1")[t])

            # generation + discharge + grid_import == load + charge (+ grid_export folded into grid_t sign)
            balance = pv_t + gen_t + dis_t + grid_t - fixed_t - ch_t
            assert abs(balance) < 1e-4, f"Power balance violated at t={t}: {balance}"

    def test_battery_soc_stays_within_bounds(self):
        T = 8
        ts = CustomerTimeSeries(
            pv_kw=[0, 1, 3, 5, 3, 1, 0, 0],
            fixed_load_kw=[2] * T,
            price_buy=[0.4, 0.4, 0.1, 0.1, 0.1, 0.4, 0.4, 0.4],
            price_sell=[0.05] * T,
        )
        battery = BatteryAsset(
            customer_id="c1", asset_id="battery_1",
            capacity_kwh=10, p_charge_max_kw=6, p_discharge_max_kw=6,
            soc_min=0.15, soc_max=0.85, eff_charge=0.9, eff_discharge=0.9,
            soc_initial=0.5,
        )
        pv = PVAsset(customer_id="c1", asset_id="pv_1", pv_profile_kw=ts.pv_kw)
        fixed = FixedLoadAsset(customer_id="c1", asset_id="fixed_1", fixed_load_profile_kw=ts.fixed_load_kw)
        grid = GridAsset(
            customer_id="c1", asset_id="grid_1",
            import_max_kw=50, export_max_kw=50,
            price_buy=ts.price_buy, price_sell=ts.price_sell,
        )
        assets = [pv, battery, fixed, grid]

        model, results, status = _solve(assets, ts, T)
        assert status["success"] is True

        # BatteryAsset.__init__ already converts the soc_min/soc_max fraction
        # arguments to kWh internally, so battery.soc_min/soc_max are already
        # absolute kWh bounds here (not fractions to be multiplied again).
        soc_min_kwh = battery.soc_min
        soc_max_kwh = battery.soc_max
        for t in range(T):
            soc_t = pyo_value(getattr(model, "soc_c1_battery_1")[t])
            assert soc_min_kwh - 1e-6 <= soc_t <= soc_max_kwh + 1e-6


class TestFlexLoadIntegration:
    """Flex load (continuous mode) combined with grid + price signal."""

    def test_continuous_flex_load_meets_energy_requirement(self):
        T = 6
        ts = CustomerTimeSeries(
            pv_kw=[0] * T,
            fixed_load_kw=[0] * T,
            price_buy=[0.5, 0.1, 0.5, 0.1, 0.5, 0.5],
            price_sell=[0.01] * T,
        )
        flex = FlexLoadAsset(
            customer_id="c1", asset_id="flex_1",
            is_continuous=True, p_min_kw=0.0, p_max_kw=4.0,
            energy_required_kwh=6.0, time_window=(0, T - 1),
        )
        grid = GridAsset(
            customer_id="c1", asset_id="grid_1",
            import_max_kw=20, export_max_kw=20,
            price_buy=ts.price_buy, price_sell=ts.price_sell,
        )
        assets = [flex, grid]

        model, results, status = _solve(assets, ts, T)
        assert status["success"] is True

        flex_power = [pyo_value(getattr(model, "flex_c1_flex_1")[t]) for t in range(T)]
        total_energy = sum(flex_power) * 1.0  # delta_t = 1.0
        assert total_energy == pytest.approx(6.0, abs=1e-3)

        # Cheapest periods (index 1, 3) should absorb the bulk of the energy
        assert flex_power[1] + flex_power[3] > flex_power[0] + flex_power[2] + flex_power[4]

    def test_on_off_flex_load_draws_fixed_power_when_on(self):
        T = 6
        ts = CustomerTimeSeries(
            pv_kw=[0] * T,
            fixed_load_kw=[0] * T,
            price_buy=[0.5, 0.1, 0.1, 0.5, 0.5, 0.5],
            price_sell=[0.01] * T,
        )
        flex = FlexLoadAsset(
            customer_id="c1", asset_id="flex_1",
            is_continuous=False, is_on_off=True, p_on_kw=3.0,
            energy_required_kwh=6.0, time_window=(0, T - 1),
        )
        grid = GridAsset(
            customer_id="c1", asset_id="grid_1",
            import_max_kw=20, export_max_kw=20,
            price_buy=ts.price_buy, price_sell=ts.price_sell,
        )
        assets = [flex, grid]

        model, results, status = _solve(assets, ts, T)
        assert status["success"] is True

        flex_power = [pyo_value(getattr(model, "flex_c1_flex_1")[t]) for t in range(T)]
        # When on, power should be exactly p_on_kw (0 otherwise) - never a partial value.
        for p in flex_power:
            assert p == pytest.approx(0.0, abs=1e-4) or p == pytest.approx(3.0, abs=1e-4)
        assert sum(flex_power) == pytest.approx(6.0, abs=1e-3)


class TestFullFleetIntegration:
    """All five asset types together: PV + battery + flex load + fixed load + grid."""

    def test_full_fleet_solves_and_balances(self):
        T = 10
        ts = CustomerTimeSeries(
            pv_kw=[0, 0, 1, 3, 5, 5, 3, 1, 0, 0],
            fixed_load_kw=[1.5] * T,
            price_buy=[0.4, 0.4, 0.3, 0.15, 0.1, 0.1, 0.15, 0.3, 0.4, 0.45],
            price_sell=[0.05] * T,
        )
        pv = PVAsset(customer_id="c1", asset_id="pv_1", pv_profile_kw=ts.pv_kw)
        battery = BatteryAsset(
            customer_id="c1", asset_id="battery_1",
            capacity_kwh=10, p_charge_max_kw=5, p_discharge_max_kw=5,
            soc_min=0.1, soc_max=0.9, eff_charge=0.92, eff_discharge=0.92,
            soc_initial=0.3,
        )
        flex = FlexLoadAsset(
            customer_id="c1", asset_id="flex_1",
            is_continuous=True, p_min_kw=0.0, p_max_kw=3.0,
            energy_required_kwh=8.0, time_window=(0, T - 1),
        )
        fixed = FixedLoadAsset(customer_id="c1", asset_id="fixed_1", fixed_load_profile_kw=ts.fixed_load_kw)
        grid = GridAsset(
            customer_id="c1", asset_id="grid_1",
            import_max_kw=50, export_max_kw=50,
            price_buy=ts.price_buy, price_sell=ts.price_sell,
        )
        assets = [pv, battery, flex, fixed, grid]

        model, results, status = _solve(assets, ts, T)
        assert status["success"] is True
        assert status["solver"] == "highs"

        for t in range(T):
            pv_t = pyo_value(getattr(model, "pv_c1_pv_1")[t])
            fixed_t = pyo_value(getattr(model, "fixed_c1_fixed_1")[t])
            flex_t = pyo_value(getattr(model, "flex_c1_flex_1")[t])
            ch_t = pyo_value(getattr(model, "p_ch_c1_battery_1")[t])
            dis_t = pyo_value(getattr(model, "p_dis_c1_battery_1")[t])
            grid_t = pyo_value(_grid_var(model, grid)[t])

            balance = pv_t + dis_t + grid_t - fixed_t - flex_t - ch_t
            assert abs(balance) < 1e-4, f"Power balance violated at t={t}: {balance}"

    def test_cost_objective_reflects_price_signal(self):
        """A cheaper, flatter price profile should always cost no more than
        the same load/generation shape with a spikier, higher price profile,
        confirming the objective genuinely depends on price (regression test
        for the 'objective always 0' bug)."""
        T = 6
        pv_kw = [0, 0, 0, 0, 0, 0]
        fixed_load_kw = [1, 1, 1, 1, 1, 1]

        def build_and_solve(price_buy):
            ts = CustomerTimeSeries(
                pv_kw=pv_kw, fixed_load_kw=fixed_load_kw,
                price_buy=price_buy, price_sell=[0.02] * T,
            )
            fixed = FixedLoadAsset(customer_id="c1", asset_id="fixed_1", fixed_load_profile_kw=fixed_load_kw)
            pv = PVAsset(customer_id="c1", asset_id="pv_1", pv_profile_kw=pv_kw)
            grid = GridAsset(
                customer_id="c1", asset_id="grid_1",
                import_max_kw=20, export_max_kw=20,
                price_buy=price_buy, price_sell=ts.price_sell,
            )
            model, _, status = _solve([pv, fixed, grid], ts, T)
            return status, model.total_cost()

        cheap_status, cheap_cost = build_and_solve([0.05] * T)
        expensive_status, expensive_cost = build_and_solve([0.05, 0.05, 0.9, 0.9, 0.05, 0.05])

        assert cheap_status["success"] and expensive_status["success"]
        # Both scenarios have identical physical import needs, so the more
        # expensive price profile must strictly cost more - this is a
        # regression test for the "objective always 0" bug, where the
        # solution would be price-insensitive and these would be equal.
        assert expensive_cost > cheap_cost
