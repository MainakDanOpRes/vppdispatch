"""Tests for BatteryAsset model."""

import pytest
from pyomo.environ import ConcreteModel, RangeSet, value
from src.vpp_dispatch.models.assets.battery import BatteryAsset

class TestBatteryAsset:
    """Test suite for BatteryAsset."""

    def test_initialization(self):
        """Test BatteryAsset initialization with defaults."""
        battery = BatteryAsset(
            customer_id="cust1",
            asset_id="batt_1",
            capacity_kwh=10.0,
            p_charge_max_kw=5.0,
            p_discharge_max_kw=5.0
        )
        assert battery.customer_id == "cust1"
        assert battery.asset_id == "batt_1"
        assert battery.capacity_kwh == 10.0
        assert battery.soc_min == 1.0  # 0.1 * 10
        assert battery.soc_max == 9.0  # 0.9 * 10
        assert battery.soc_initial == 5.0  # 0.5 * 10

    def test_custom_initialization(self):
        """Test BatteryAsset with custom parameters."""
        battery = BatteryAsset(
            customer_id="cust1",
            asset_id="batt_1",
            capacity_kwh=20.0,
            p_charge_max_kw=10.0,
            p_discharge_max_kw=8.0,
            soc_min=0.2,
            soc_max=0.8,
            eff_charge=0.9,
            eff_discharge=0.92,
            soc_initial=0.5
        )
        assert battery.soc_min == 4.0  # 0.2 * 20
        assert battery.soc_max == 16.0  # 0.8 * 20
        assert battery.soc_initial == 10.0

    def test_register_variables(self, battery_asset, empty_model):
        """Test battery variable registration."""
        battery_asset.register_variables(empty_model)

        assert hasattr(empty_model, "p_ch_battery_1")
        assert hasattr(empty_model, "p_dis_battery_1")
        assert hasattr(empty_model, "u_battery_1")
        assert hasattr(empty_model, "soc_battery_1")

    def test_register_constraints(self, battery_asset, empty_model):
        """Test battery constraint registration."""
        battery_asset.register_variables(empty_model)
        battery_asset.register_constraints(empty_model)

        assert hasattr(empty_model, "battery_soc_battery_1")
        assert hasattr(empty_model, "c_soc_lo_battery_1")
        assert hasattr(empty_model, "c_soc_hi_battery_1")
        assert hasattr(empty_model, "c_charge_ub_battery_1")
        assert hasattr(empty_model, "c_disch_ub_battery_1")

    def test_soc_dynamics(self, battery_asset, empty_model):
        """Test SOC dynamics constraint."""
        battery_asset.register_variables(empty_model)
        battery_asset.register_constraints(empty_model)

        # Assign values to the variables involved at t=0
        p_ch = empty_model.p_ch_battery_1
        p_dis = empty_model.p_dis_battery_1
        soc = empty_model.soc_battery_1

        t0 = empty_model.T.first()
        p_ch[t0].value = 2.0
        p_dis[t0].value = 1.0

        expected_soc0 = battery_asset.soc_initial + (
            battery_asset.eff_charge * p_ch[t0].value * empty_model.delta_t
            - (1 / battery_asset.eff_discharge) * p_dis[t0].value * empty_model.delta_t
        )

        soc[t0].value = expected_soc0

        # Get SOC constraint for t=0 (first time period)
        soc_constraint = empty_model.battery_soc_battery_1[t0]

        # Should be: soc[0] == soc_initial + eff_charge * p_ch[0] * delta_t
        #            - (1/eff_discharge) * p_dis[0] * delta_t
        residual = value(soc_constraint.body) - value(soc_constraint.lower)
        assert abs(residual) < 1e-9

        # Now check the recursive rule for t=1 (if it exists)
        t_list = list(empty_model.T)
        if len(t_list) > 1:
            t1 = t_list[1]
            p_ch[t1].value = 1.5
            p_dis[t1].value = 0.5
            soc[t1].value = soc[t0].value + (
                battery_asset.eff_charge * p_ch[t1].value * empty_model.delta_t
                - (1 / battery_asset.eff_discharge) * p_dis[t1].value * empty_model.delta_t
            )
            soc_constraint_t1 = empty_model.battery_soc_battery_1[t1]
            residual_t1 = value(soc_constraint_t1.body) - value(soc_constraint_t1.lower)
            assert abs(residual_t1) < 1e-9

    def test_register_objectives_no_cost(self, empty_model):
        """Test that objective returns 0.0 when degradation cost is zero."""
        battery = BatteryAsset(
            customer_id="cust1",
            asset_id="batt_1",
            capacity_kwh=10.0,
            p_charge_max_kw=5.0,
            p_discharge_max_kw=5.0,
            degradation_cost_per_kwh=0.0  # Zero cost
        )
        battery.register_variables(empty_model)
        
        # Call the objective function
        obj_expr = battery.register_objectives(empty_model)
        
        # Since cost is 0, it should return a float 0.0 directly, not a Pyomo expression
        assert obj_expr == 0.0

    def test_register_objectives_with_cost(self, empty_model):
        """Test the degradation cost calculation expression."""
        cost_per_kwh = 0.1
        battery = BatteryAsset(
            customer_id="cust1",
            asset_id="batt_1",
            capacity_kwh=10.0,
            p_charge_max_kw=5.0,
            p_discharge_max_kw=5.0,
            degradation_cost_per_kwh=cost_per_kwh
        )
        battery.register_variables(empty_model)
        
        # Get variable references
        p_ch = getattr(empty_model, "p_ch_batt_1")
        p_dis = getattr(empty_model, "p_dis_batt_1")
        
        # Assign values to simulate a scenario
        # e.g., 2kW charge and 1kW discharge for all time periods
        for t in empty_model.T:
            p_ch[t].value = 2.0
            p_dis[t].value = 1.0
            
        # Get the Pyomo expression
        obj_expr = battery.register_objectives(empty_model)
        
        # Calculate what the expected cost should be manually
        # Total power cycled per time step = 2.0 + 1.0 = 3.0 kW
        # Energy per time step = 3.0 * delta_t
        expected_energy_cycled = sum(3.0 * empty_model.delta_t for _ in empty_model.T)
        expected_cost = expected_energy_cycled * cost_per_kwh
        
        # Evaluate the Pyomo expression and compare
        assert value(obj_expr) == pytest.approx(expected_cost)

    def test_get_results(self, battery_asset, empty_model):
        """Test extracting battery results."""
        battery_asset.register_variables(empty_model)

        # Set values
        for t in empty_model.T:
            empty_model.p_ch_battery_1[t].value = float(t) * 0.5
            empty_model.p_dis_battery_1[t].value = float(t) * 0.3
            empty_model.soc_battery_1[t].value = 5.0 + float(t) * 0.2

        results = battery_asset.get_results(empty_model)
        assert "p_ch" in results
        assert "p_dis" in results
        assert "soc" in results
        assert len(results["p_ch"]) == 5

    def test_soc_bounds(self, battery_asset, empty_model):
        """Test SOC bounds constraints."""
        battery_asset.register_variables(empty_model)
        battery_asset.register_constraints(empty_model)

        for t in empty_model.T:
            # Check SOC lower bound
            lo_constraint = empty_model.c_soc_lo_battery_1[t]
            # Should be: soc[t] >= soc_min
            assert value(lo_constraint.lower) == pytest.approx(battery_asset.soc_min)


            # Check SOC upper bound
            hi_constraint = empty_model.c_soc_hi_battery_1[t]
            # Should be: soc[t] <= soc_max
            assert value(hi_constraint.upper) == pytest.approx(battery_asset.soc_max)