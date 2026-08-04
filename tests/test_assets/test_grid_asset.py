"""Tests for GridAsset model."""

import pytest
from pyomo.environ import ConcreteModel, RangeSet, value
from src.vpp_dispatch.models.assets.grid import GridAsset


class TestGridAsset:
    """Test stuite for grid asset"""
    def test_initialization(self):
        """Test GridAsset initialization."""
        grid = GridAsset(
            customer_id="cust1",
            asset_id="grid_1",
            import_max_kw=100.0,
            export_max_kw=50.0,
            price_buy=[0.1, 0.2],
            price_sell=[0.05, 0.1]
        )
        assert grid.customer_id == "cust1"
        assert grid.asset_id == "grid_1"
        assert grid.import_max_kw == 100.0
        assert grid.export_max_kw == 50.0
        assert grid.price_buy == [0.1, 0.2]
        assert grid.price_sell == [0.05, 0.1]
        assert grid.objective_weight == 1.0

    def test_register_variables(self, grid_asset, empty_model):
        """Test grid variable and parameter registration."""
        grid_asset.register_variables(empty_model)

        # Check Variables
        assert hasattr(empty_model, "p_grid_grid_1")
        assert hasattr(empty_model, "p_grid_buy_grid_1")
        assert hasattr(empty_model, "p_grid_sell_grid_1")

        # Check Parameters
        assert hasattr(empty_model, "price_buy_grid_1")
        assert hasattr(empty_model, "price_sell_grid_1")
        assert hasattr(empty_model, "import_kw_grid_1")
        assert hasattr(empty_model, "export_kw_grid_1")

        # Verify Parameter Values
        assert value(empty_model.import_kw_grid_1) == 100.0
        assert value(empty_model.export_kw_grid_1) == 50.0
        assert value(empty_model.price_buy_grid_1[0]) == 0.15
        assert value(empty_model.price_sell_grid_1[2]) == 0.08

    def test_register_constraints(self, grid_asset, empty_model):
        """Test grid constraint registration and bounds."""
        grid_asset.register_variables(empty_model)
        grid_asset.register_constraints(empty_model)

        # Check constraints exist
        assert hasattr(empty_model, "grid_split_grid_1")
        assert hasattr(empty_model, "import_limit_grid_1")
        assert hasattr(empty_model, "export_limit_grid_1")

        for t in empty_model.T:
            # Import limit check: p_buy[t] - u_buy[t] * import_limit -<= 0
            import_c = empty_model.import_limit_grid_1[t]
            assert value(import_c.upper) == 0.0
            # assert import_c.body

            # Export limit check: p_sell[t] - (1 - u_buy[t]) * export_limit <= 0
            export_c = empty_model.export_limit_grid_1[t]
            assert value(export_c.upper) == 0.0

    def test_grid_split_logic(self, grid_asset, empty_model):
        """Test the logic of the grid split constraint (p_grid = buy - sell)."""
        grid_asset.register_variables(empty_model)
        grid_asset.register_constraints(empty_model)

        p_grid = empty_model.p_grid_grid_1
        p_buy = empty_model.p_grid_buy_grid_1
        p_sell = empty_model.p_grid_sell_grid_1

        t0 = empty_model.T.first()
        
        # Simulate buying 20 kW and selling 0 kW
        p_buy[t0].value = 20.0
        p_sell[t0].value = 0.0
        p_grid[t0].value = 20.0  
        
        constraint_t0 = empty_model.grid_split_grid_1[t0]
        # Body is (p_grid - p_buy + p_sell), should equal 0
        residual = value(constraint_t0.body) - value(constraint_t0.lower)
        assert abs(residual) < 1e-9

        # Simulate buying 0 kW and selling 15 kW
        t1 = empty_model.T.at(2) # Second time step
        p_buy[t1].value = 0.0
        p_sell[t1].value = 15.0
        p_grid[t1].value = -15.0  # Net export is negative
        
        constraint_t1 = empty_model.grid_split_grid_1[t1]
        residual_t1 = value(constraint_t1.body) - value(constraint_t1.lower)
        assert abs(residual_t1) < 1e-9

    def test_register_objectives(self, grid_asset, empty_model):
        """Test the grid cost/revenue objective calculation."""
        grid_asset.register_variables(empty_model)
        
        p_buy = empty_model.p_grid_buy_grid_1
        p_sell = empty_model.p_grid_sell_grid_1
        u_buy = empty_model.u_grid_buy_grid_1
        
        # Set dummy values: 
        # t=0: buy 10 kW @ 0.15 (Cost: 1.5)
        # t=1: buy 10 kW @ 0.15 (Cost: 1.5)
        # t=2: sell 20 kW @ 0.08 (Rev: -1.6)
        # t=3: sell 20 kW @ 0.08 (Rev: -1.6)
        
        p_buy[0].value, p_sell[0].value, u_buy[0].value = 10.0, 0.0, 1
        p_buy[1].value, p_sell[1].value, u_buy[1].value = 10.0, 0.0, 1
        p_buy[2].value, p_sell[2].value, u_buy[2].value = 0.0, 20.0, 0
        p_buy[3].value, p_sell[3].value, u_buy[3].value = 0.0, 20.0, 0
        p_buy[4].value, p_sell[4].value, u_buy[4].value = 0.0, 20.0, 0
        
        obj_expr = grid_asset.register_objectives(empty_model)
        
        expected_cost = (10*0.15 + 10*0.15) - (20*0.08 + 20*0.08 + 20*0.07)
        # multiply by delta_t (which is 1.0 in this fixture)
        expected_cost *= empty_model.delta_t
        
        assert value(obj_expr) == pytest.approx(expected_cost)

    def test_get_results(self, grid_asset, empty_model):
        """Test extracting grid results."""
        grid_asset.register_variables(empty_model)

        # Set values for the bidirectional p_grid variable
        p_grid = empty_model.p_grid_grid_1
        for t in empty_model.T:
            # Alternating import and export
            p_grid[t].value = 10.0 if t % 2 == 0 else -5.0

        results = grid_asset.get_results(empty_model)
        
        assert "p_grid" in results
        assert len(results["p_grid"]) == 5
        assert results["p_grid"] == [10.0, -5.0, 10.0, -5.0, 10.0]

    def test_get_results_not_registered(self, grid_asset, empty_model):
        """Test get_results when model variables aren't registered yet."""
        # Skipping register_variables to simulate error state or early extraction
        results = grid_asset.get_results(empty_model)
        
        assert results == {}