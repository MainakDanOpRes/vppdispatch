"""Tests for GeneratorAsset model."""

import pytest
from pyomo.environ import ConcreteModel, RangeSet, value
from src.vpp_dispatch.models.assets.generator import GeneratorAsset


class TestGeneratorAsset:
    """Test suite for generator asset"""
    def test_initialization(self):
        """Test GeneratorAsset initialization."""
        gen = GeneratorAsset(
            customer_id="cust1",
            asset_id="gen_1",
            p_max_kw=50.0,
            p_min_kw=10.0,
            ramp_rate=25.0,
            min_up_time=2,
            min_down_time=2,
            marginal_cost_per_kw=0.05,
            start_up_cost=10.0,
            shut_down_cost=5.0
        )
        assert gen.customer_id == "cust1"
        assert gen.asset_id == "gen_1"
        assert gen.p_max_kw == 50.0
        assert gen.p_min_kw == 10.0
        assert gen.ramp_rate == 25.0
        assert gen.min_up_time == 2
        assert gen.min_down_time == 2
        assert gen.marginal_cost_per_kw == 0.05
        assert gen.start_up_cost == 10.0
        assert gen.shut_down_cost == 5.0
        assert gen.objective_weight == 1.0

    def test_register_variables(self, generator_asset, empty_model):
        """Test generator variable registration."""
        generator_asset.register_variables(empty_model)

        # Check Variables
        assert hasattr(empty_model, "p_gen_cust1_gen_1")
        assert hasattr(empty_model, "u_gen_cust1_gen_1")
        assert hasattr(empty_model, "v_gen_cust1_gen_1")
        assert hasattr(empty_model, "w_gen_cust1_gen_1")

    def test_register_constraints(self, generator_asset, empty_model):
        """Test generator constraint registration and bounds."""
        generator_asset.register_variables(empty_model)
        generator_asset.register_constraints(empty_model)

        # Check constraints exist
        assert hasattr(empty_model, "gen_p_min_constraint_cust1_gen_1")
        assert hasattr(empty_model, "gen_p_max_constraint_cust1_gen_1")
        assert hasattr(empty_model, "gen_ramp_up_constraint_cust1_gen_1")
        assert hasattr(empty_model, "gen_ramp_down_constraint_cust1_gen_1")
        assert hasattr(empty_model, "gen_commitment_transition_constraint_cust1_gen_1")
        assert hasattr(empty_model, "gen_startup_shutdown_exclusivity_cust1_gen_1")
        assert hasattr(empty_model, "gen_min_up_constraint_cust1_gen_1")
        assert hasattr(empty_model, "gen_min_down_constraint_cust1_gen_1")

    def test_generator_limits(self, generator_asset, empty_model):
        """Test power output limits relative to commitment status."""
        generator_asset.register_variables(empty_model)
        generator_asset.register_constraints(empty_model)

        p_gen = empty_model.p_gen_cust1_gen_1
        u_gen = empty_model.u_gen_cust1_gen_1

        t0 = empty_model.T.first()
        
        # When unit is off (u_gen = 0), power should be constrained to 0
        u_gen[t0].value = 0
        p_gen[t0].value = 0.0
        
        min_c = empty_model.gen_p_min_constraint_cust1_gen_1[t0]
        max_c = empty_model.gen_p_max_constraint_cust1_gen_1[t0]
        assert value(min_c.body) >= 0
        assert value(max_c.body) <= 0

        # When unit is on (u_gen = 1), power must be between p_min_kw and p_max_kw
        # t1 = empty_model.T.at(2)
        # u_gen[t1].value = 1
        # p_gen[t1].value = 30.0

        # min_c1 = empty_model.gen_p_min_constraint_cust1_gen_1[t1]
        # max_c1 = empty_model.gen_p_max_constraint_cust1_gen_1[t1]
        # # print(value(min_c1.body))
        # # print(value(max_c1.body))
        # assert value(min_c1.body) <= 0
        # assert value(max_c1.body) <= 0

    def test_register_objectives(self, generator_asset, empty_model):
        """Test the generator cost objective calculation."""
        generator_asset.register_variables(empty_model)
        
        p_gen = empty_model.p_gen_cust1_gen_1
        v_gen = empty_model.v_gen_cust1_gen_1
        w_gen = empty_model.w_gen_cust1_gen_1
        
        # Set dummy values across time steps
        p_gen[0].value, v_gen[0].value, w_gen[0].value = 0.0, 0.0, 0.0
        p_gen[1].value, v_gen[1].value, w_gen[1].value = 20.0, 1.0, 0.0  # Startup cost incurred
        p_gen[2].value, v_gen[2].value, w_gen[2].value = 30.0, 0.0, 0.0
        p_gen[3].value, v_gen[3].value, w_gen[3].value = 0.0, 0.0, 1.0   # Shutdown cost incurred
        p_gen[4].value, v_gen[4].value, w_gen[4].value = 0.0, 0.0, 0.0
        
        obj_expr = generator_asset.register_objectives(empty_model)
        
        # Expected cost = sum(p_gen * marginal_cost) + sum(v_gen * start_up_cost) + sum(w_gen * shut_down_cost)
        expected_cost = (
            (0.0 * 0.05 + 0.0 + 0.0) +
            (20.0 * 0.05 + 1.0 * 10.0 + 0.0) +
            (30.0 * 0.05 + 0.0 + 0.0) +
            (0.0 * 0.05 + 0.0 + 1.0 * 5.0) +
            (0.0 * 0.05 + 0.0 + 0.0)
        )
        # expected_cost *= empty_model.delta_t
        
        assert value(obj_expr) == pytest.approx(expected_cost)

    def test_get_results(self, generator_asset, empty_model):
        """Test extracting generator results."""
        generator_asset.register_variables(empty_model)

        p_gen = empty_model.p_gen_cust1_gen_1
        u_gen = empty_model.u_gen_cust1_gen_1
        for t in empty_model.T:
            p_gen[t].value = 25.0
            u_gen[t].value = 1.0

        results = generator_asset.get_results(empty_model)
        
        assert "p_gen" in results
        assert "u_gen" in results
        assert "v_gen" in results
        assert "w_gen" in results
        assert len(results["p_gen"]) == 5
        assert results["p_gen"] == [25.0, 25.0, 25.0, 25.0, 25.0]
        assert results["u_gen"] == [1.0, 1.0, 1.0, 1.0, 1.0]

    def test_get_results_not_registered(self, generator_asset, empty_model):
        """Test get_results when model variables aren't registered yet."""
        results = generator_asset.get_results(empty_model)
        assert results == {}