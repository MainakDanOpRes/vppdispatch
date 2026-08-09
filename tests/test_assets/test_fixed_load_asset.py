"""Tests for FixedLoadAsset model."""

import pytest
from pyomo.environ import ConcreteModel, RangeSet, Var, Param, value
from src.vpp_dispatch.models.assets.fixed_load import FixedLoadAsset


class TestFixedLoadAsset:
    """Test suite for FixedLoadAsset."""

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def test_initialization_defaults(self):
        """Test FixedLoadAsset initialization with default parameters."""
        profile = [1.0, 2.0, 3.0, 4.0, 5.0]
        load = FixedLoadAsset(
            customer_id="cust1",
            asset_id="fixed_1",
            fixed_load_profile_kw=profile,
        )
        assert load.customer_id == "cust1"
        assert load.asset_id == "fixed_1"
        assert load.fixed_load_profile_kw == profile
        assert load.is_controllable is False
        assert load.priority == 1
        assert load.operational_hours is None

    def test_initialization_custom(self):
        """Test FixedLoadAsset initialization with custom parameters."""
        profile = [0.5, 1.5, 2.5, 3.5, 4.5]
        load = FixedLoadAsset(
            customer_id="cust2",
            asset_id="fixed_2",
            fixed_load_profile_kw=profile,
            is_controllable=True,
            priority=3,
            operational_hours=(1, 4),
        )
        assert load.is_controllable is True
        assert load.priority == 3
        assert load.operational_hours == (1, 4)

    # ------------------------------------------------------------------
    # register_variables
    # ------------------------------------------------------------------

    def test_register_variables_controllable_creates_var(self, empty_model):
        """When controllable, a Var should be registered."""
        profile = [1.0, 2.0, 3.0, 4.0, 5.0]
        load = FixedLoadAsset(
            customer_id="cust1",
            asset_id="fixed_1",
            fixed_load_profile_kw=profile,
            is_controllable=True,
        )
        load.register_variables(empty_model)

        assert hasattr(empty_model, "fixed_cust1_fixed_1")
        component = getattr(empty_model, "fixed_cust1_fixed_1")
        assert isinstance(component, Var)

    def test_register_variables_noncontrollable_creates_param(self, empty_model):
        """When not controllable, a Param should be registered, initialized
        from the fixed load profile."""
        profile = [1.0, 2.0, 3.0, 4.0, 5.0]
        load = FixedLoadAsset(
            customer_id="cust1",
            asset_id="fixed_1",
            fixed_load_profile_kw=profile,
            is_controllable=False,
        )
        load.register_variables(empty_model)

        assert hasattr(empty_model, "fixed_cust1_fixed_1")
        component = getattr(empty_model, "fixed_cust1_fixed_1")
        assert isinstance(component, Param)

        for t in empty_model.T:
            assert value(component[t]) == pytest.approx(profile[t])

    # ------------------------------------------------------------------
    # register_constraints - controllable, no operational hours
    # ------------------------------------------------------------------

    def test_register_constraints_controllable_no_operational_hours(self, empty_model):
        """Without operational hours, only the profile upper-bound
        constraint should be registered."""
        profile = [1.0, 2.0, 3.0, 4.0, 5.0]
        load = FixedLoadAsset(
            customer_id="cust1",
            asset_id="fixed_1",
            fixed_load_profile_kw=profile,
            is_controllable=True,
            operational_hours=None,
        )
        load.register_variables(empty_model)
        load.register_constraints(empty_model)

        assert hasattr(empty_model, "fixed_profile_cust1_fixed_1")
        assert not hasattr(empty_model, "fixed_op_cust1_fixed_1")

        profile_constraint = empty_model.fixed_profile_cust1_fixed_1
        for t in empty_model.T:
            constraint = profile_constraint[t]
            # Should be: fixed[t] <= profile[t]
            assert constraint.upper is not None
            assert value(constraint.upper) == pytest.approx(profile[t])
            assert constraint.lower is None

    # ------------------------------------------------------------------
    # register_constraints - controllable, with operational hours
    # ------------------------------------------------------------------

    def test_register_constraints_controllable_with_operational_hours(self, empty_model):
        """With operational hours set, fixed_op constraint should force
        the load to zero outside the window and bound it inside."""
        profile = [1.0, 2.0, 3.0, 4.0, 5.0]
        t_start, t_end = 1, 4
        load = FixedLoadAsset(
            customer_id="cust1",
            asset_id="fixed_1",
            fixed_load_profile_kw=profile,
            is_controllable=True,
            operational_hours=(t_start, t_end),
        )
        load.register_variables(empty_model)
        load.register_constraints(empty_model)

        assert hasattr(empty_model, "fixed_op_cust1_fixed_1")
        assert not hasattr(empty_model, "fixed_profile_cust1_fixed_1")

        op_constraint = empty_model.fixed_op_cust1_fixed_1
        for t in empty_model.T:
            constraint = op_constraint[t]
            if t < t_start or t >= t_end:
                # Equality constraint forcing fixed[t] == 0
                assert value(constraint.lower) == 0
                assert value(constraint.upper) == 0
            else:
                # Inequality: fixed[t] <= profile[t]
                assert value(constraint.upper) == pytest.approx(profile[t])
                assert constraint.lower is None

    # ------------------------------------------------------------------
    # register_constraints - non-controllable
    # ------------------------------------------------------------------

    def test_register_constraints_noncontrollable_registers_nothing(self, empty_model):
        """Non-controllable loads shouldn't register any constraints,
        since the load is fixed via a Param."""
        profile = [1.0, 2.0, 3.0, 4.0, 5.0]
        load = FixedLoadAsset(
            customer_id="cust1",
            asset_id="fixed_1",
            fixed_load_profile_kw=profile,
            is_controllable=False,
        )
        load.register_variables(empty_model)
        load.register_constraints(empty_model)

        assert not hasattr(empty_model, "fixed_profile_cust1_fixed_1")
        assert not hasattr(empty_model, "fixed_op_cust1_fixed_1")

    # ------------------------------------------------------------------
    # get_results
    # ------------------------------------------------------------------

    def test_get_results_controllable(self, empty_model):
        """Test extracting results when the load is a controllable Var."""
        profile = [1.0, 2.0, 3.0, 4.0, 5.0]
        load = FixedLoadAsset(
            customer_id="cust1",
            asset_id="fixed_1",
            fixed_load_profile_kw=profile,
            is_controllable=True,
        )
        load.register_variables(empty_model)

        for t in empty_model.T:
            empty_model.fixed_cust1_fixed_1[t].value = float(t) * 0.5

        results = load.get_results(empty_model)
        assert "fixed_load" in results
        assert len(results["fixed_load"]) == 5
        for t in empty_model.T:
            assert results["fixed_load"][t] == pytest.approx(float(t) * 0.5)

    def test_get_results_noncontrollable(self, empty_model):
        """Test extracting results when the load is a fixed Param.

        With the fix to use pyomo.environ.value() instead of `.value`,
        this now correctly returns the underlying profile values instead
        of raising AttributeError.
        """
        profile = [1.0, 2.0, 3.0, 4.0, 5.0]
        load = FixedLoadAsset(
            customer_id="cust1",
            asset_id="fixed_1",
            fixed_load_profile_kw=profile,
            is_controllable=False,
        )
        load.register_variables(empty_model)

        results = load.get_results(empty_model)
        assert "fixed_load" in results
        assert len(results["fixed_load"]) == 5
        for t in empty_model.T:
            assert results["fixed_load"][t] == pytest.approx(profile[t])

    def test_get_results_missing_variable(self, empty_model):
        """If variables were never registered, get_results should return
        an empty dict rather than raising."""
        profile = [1.0, 2.0, 3.0, 4.0, 5.0]
        load = FixedLoadAsset(
            customer_id="cust1",
            asset_id="fixed_1",
            fixed_load_profile_kw=profile,
        )
        results = load.get_results(empty_model)
        assert results == {}

    # ------------------------------------------------------------------
    # to_dict
    # ------------------------------------------------------------------

    def test_to_dict(self):
        """Test serialization to dictionary."""
        profile = [1.0, 2.0, 3.0, 4.0, 5.0]
        load = FixedLoadAsset(
            customer_id="cust1",
            asset_id="fixed_1",
            fixed_load_profile_kw=profile,
            is_controllable=True,
            priority=2,
            operational_hours=(1, 4),
        )
        d = load.to_dict()

        assert d["type"] == "FixedLoadAsset"
        assert d["fixed_load_profile_kw"] == profile
        assert d["is_controllable"] is True
        assert d["priority"] == 2
        assert d["operational_hours"] == (1, 4)
        # Should also include base asset fields (customer_id, asset_id, etc.)
        assert d["customer_id"] == "cust1"
        assert d["asset_id"] == "fixed_1"