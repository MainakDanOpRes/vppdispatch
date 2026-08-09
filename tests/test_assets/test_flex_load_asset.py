"""Tests for FlexLoadAsset model."""

import pytest
from pyomo.environ import ConcreteModel, RangeSet, value
from src.vpp_dispatch.models.assets.flex_load import FlexLoadAsset

class TestFlexLoadAsset:
    """Test suite for unified FlexLoadAsset."""

    def test_initialization(self):
        """Test FlexLoadAsset initialization and mode validation."""
        # Valid initialization (Default: Continuous)
        flex_cont = FlexLoadAsset(
            customer_id="cust1",
            asset_id="flex_1",
            name="EV",
            is_continuous=True,
            is_shiftable=False,
            is_on_off=False,
            p_min_kw=0.0,
            p_max_kw=7.0,
            energy_required_kwh=14.0,
            time_window=(10, 20)
        )
        assert flex_cont.customer_id == "cust1"
        assert flex_cont.asset_id == "flex_1"
        assert flex_cont.is_continuous is True
        assert flex_cont.t_start == 10
        assert flex_cont.t_end == 20
        
        # Test ValueError on conflicting modes
        with pytest.raises(ValueError, match="Conflicting load types"):
            FlexLoadAsset("c1", "a1", is_continuous=True, is_shiftable=True)

        # Test ValueError on no active mode
        with pytest.raises(ValueError, match="At least one load type flag must be True"):
            FlexLoadAsset("c1", "a1", is_continuous=False, is_shiftable=False, is_on_off=False)

    def test_register_variables(self, empty_model):
        """Test flex load variable registration across modes."""
        flex = FlexLoadAsset("c1", "flex_1", is_continuous=True)
        flex.register_variables(empty_model)
        
        assert hasattr(empty_model, "flex_c1_flex_1")
        assert hasattr(empty_model, "u_flex_c1_flex_1")
        assert hasattr(empty_model, "v_start_c1_flex_1")

    def test_register_constraints_continuous(self, empty_model):
        """Test flex load constraint registration for Continuous mode."""
        flex = FlexLoadAsset("c1", "flex_1", is_continuous=True)
        flex.register_variables(empty_model)
        flex.register_constraints(empty_model)

        assert hasattr(empty_model, "flex_window_c1_flex_1")
        assert hasattr(empty_model, "flex_startup_c1_flex_1")
        assert hasattr(empty_model, "flex_min_c1_flex_1")
        assert hasattr(empty_model, "flex_max_c1_flex_1")
        assert hasattr(empty_model, "flex_energy_c1_flex_1")

    def test_register_constraints_on_off(self, empty_model):
        """Test flex load constraint registration for On/Off mode."""
        flex = FlexLoadAsset("c1", "flex_2", is_continuous=False, is_on_off=True)
        flex.register_variables(empty_model)
        flex.register_constraints(empty_model)

        assert hasattr(empty_model, "flex_window_c1_flex_2")
        assert hasattr(empty_model, "flex_startup_c1_flex_2")
        assert hasattr(empty_model, "flex_on_power_c1_flex_2")
        assert hasattr(empty_model, "flex_on_energy_c1_flex_2")
        assert hasattr(empty_model, "flex_single_act_c1_flex_2")

    def test_register_constraints_shiftable(self, empty_model):
        """Test flex load constraint registration for Shiftable mode."""
        flex = FlexLoadAsset(
            "c1", "flex_3", 
            is_continuous=False, 
            is_shiftable=True, 
            load_profile=[1.0, 2.0, 1.0]
        )
        flex.register_variables(empty_model)
        flex.register_constraints(empty_model)

        assert hasattr(empty_model, "shift_single_start_c1_flex_3")
        assert hasattr(empty_model, "shift_window_c1_flex_3")
        assert hasattr(empty_model, "shift_power_c1_flex_3")

    def test_time_window_constraint(self, empty_model):
        """Test that flex load binary state is zero outside time window."""
        flex = FlexLoadAsset("c1", "flex_1", is_continuous=True, time_window=(2, 4))
        flex.register_variables(empty_model)
        flex.register_constraints(empty_model)

        window_constraint = empty_model.flex_window_c1_flex_1

        # For t < t_start or t > t_end, u_flex should be forced to 0
        for t in empty_model.T:
            if t < flex.t_start or t > flex.t_end:
                # Equality constraint forcing u_flex[t] == 0
                assert t in window_constraint
                assert value(window_constraint[t].lower) == 0
                assert value(window_constraint[t].upper) == 0
            else:
                # Inside the window, the constraint returns Constraint.Skip
                assert t not in window_constraint

    def test_energy_requirement_constraint(self, empty_model):
        """Test total energy requirement constraint for Continuous mode."""
        flex = FlexLoadAsset("c1", "flex_1", is_continuous=True, energy_required_kwh=14.0)
        flex.register_variables(empty_model)
        flex.register_constraints(empty_model)

        energy_constraint = empty_model.flex_energy_c1_flex_1
        
        # Should be: sum(flex[t] * dt for t in T) == energy_required_kwh
        assert value(energy_constraint.lower) == pytest.approx(flex.energy_required_kwh)
        assert value(energy_constraint.upper) == pytest.approx(flex.energy_required_kwh)

        flex_var = empty_model.flex_c1_flex_1
        n_t = len(list(empty_model.T))
        dt = empty_model.delta_t
        per_step = flex.energy_required_kwh / (n_t * dt)
        
        for t in empty_model.T:
            flex_var[t].value = per_step

        residual = value(energy_constraint.body) - value(energy_constraint.lower)
        assert abs(residual) < 1e-9

    def test_get_results(self, empty_model):
        """Test extracting flex load results."""
        flex = FlexLoadAsset("c1", "flex_1", is_continuous=True)
        flex.register_variables(empty_model)

        # Mock solver values
        for t in empty_model.T:
            empty_model.flex_c1_flex_1[t].value = float(t) * 1.5
            empty_model.u_flex_c1_flex_1[t].value = 1 if t >= 2 else 0
            empty_model.v_start_c1_flex_1[t].value = 1 if t == 2 else 0

        results = flex.get_results(empty_model)
        
        assert "flex_power_kw" in results
        assert "is_on" in results
        assert "start_signal" in results
        assert len(results["flex_power_kw"]) == len(empty_model.T)
        
        # Check mocked values
        assert results["flex_power_kw"][2] == 3.0
        assert results["is_on"][2] == 1
        assert results["start_signal"][2] == 1