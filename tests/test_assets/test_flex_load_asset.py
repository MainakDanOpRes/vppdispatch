"""Tests for FlexLoadAsset model."""

import pytest
from pyomo.environ import ConcreteModel, RangeSet, value
from src.vpp_dispatch.models.assets.flex_load import FlexLoadAsset

class TestFlexLoadAsset:
    """Test suite for FlexLoadAsset."""

    def test_initialization(self):
        """Test FlexLoadAsset initialization."""
        flex = FlexLoadAsset(
            customer_id="cust1",
            asset_id="flex_1",
            name="EV",
            p_min_kw=0.0,
            p_max_kw=7.0,
            energy_required_kwh=14.0,
            time_window=(10, 20)
        )
        assert flex.customer_id == "cust1"
        assert flex.asset_id == "flex_1"
        assert flex.name == "EV"
        assert flex.t_start == 10
        assert flex.t_end == 20

    def test_register_variables(self, flex_load_asset, empty_model):
        """Test flex load variable registration."""
        flex_load_asset.register_variables(empty_model)
        assert hasattr(empty_model, "flex_flex_1")

    def test_register_constraints(self, flex_load_asset, empty_model):
        """Test flex load constraint registration."""
        flex_load_asset.register_variables(empty_model)
        flex_load_asset.register_constraints(empty_model)

        assert hasattr(empty_model, "flex_bounds_flex_1")
        assert hasattr(empty_model, "flex_energy_flex_1")

    def test_time_window_constraint(self, flex_load_asset, empty_model):
        """Test that flex load is zero outside time window."""
        flex_load_asset.register_variables(empty_model)
        flex_load_asset.register_constraints(empty_model)

        flex_bounds = empty_model.flex_bounds_flex_1

        # For t < t_start or t > t_end, flex should be 0
        # This is enforced by flex_bounds constraint
        for t in empty_model.T:
            constraint = flex_bounds[t]
            if t < flex_load_asset.t_start or t > flex_load_asset.t_end:
                # Equality constraint forcing flex[t] == 0
                assert value(constraint.lower) == 0
                assert value(constraint.upper) == 0
            else:
                # Bounded constraint: p_min_kw <= flex[t] <= p_max_kw
                assert value(constraint.lower) == pytest.approx(flex_load_asset.p_min_kw)
                assert value(constraint.upper) == pytest.approx(flex_load_asset.p_max_kw)


    def test_energy_requirement_constraint(self, flex_load_asset, empty_model):
        """Test total energy requirement constraint."""
        flex_load_asset.register_variables(empty_model)
        flex_load_asset.register_constraints(empty_model)

        energy_constraint = empty_model.flex_energy_flex_1
        # Should be: sum(flex[t] * delta_t for t in T) == energy_required_kwh
        assert value(energy_constraint.lower) == pytest.approx(
            flex_load_asset.energy_required_kwh
        )
        assert value(energy_constraint.upper) == pytest.approx(
            flex_load_asset.energy_required_kwh
        )

        flex_var = empty_model.flex_flex_1
        n_t = len(list(empty_model.T))
        dt = empty_model.delta_t
        per_step = flex_load_asset.energy_required_kwh / (n_t * dt)
        for t in empty_model.T:
            flex_var[t].value = per_step

        residual = value(energy_constraint.body) - value(energy_constraint.lower)
        assert abs(residual) < 1e-9

    def test_get_results(self, flex_load_asset, empty_model):
        """Test extracting flex load results."""
        flex_load_asset.register_variables(empty_model)

        for t in empty_model.T:
            empty_model.flex_flex_1[t].value = float(t) * 1.0

        results = flex_load_asset.get_results(empty_model)
        assert "flex" in results
        assert len(results["flex"]) == 5