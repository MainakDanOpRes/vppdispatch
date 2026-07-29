import pytest
from pyomo.environ import ConcreteModel, RangeSet, value
from src.vpp_dispatch.models.assets.pv import PVAsset

class TestPVAsset:
    """ Test suite for PVAsset"""

    def test_initialization(self, simple_timeseries):
        """Test PVAsset initialization"""

        pv = PVAsset(customer_id="customer_1",
                     asset_id="PV_roof", pv_profile_kw=simple_timeseries.pv_kw)

        assert pv.customer_id == "customer_1"
        assert pv.asset_id == "PV_roof"
        assert pv.pv_profile_kw == simple_timeseries.pv_kw

    def test_register_variables(self, pv_asset, empty_model):
        """Test that PV asset registers variable correctly"""
        pv_asset.register_variables(empty_model)

        assert hasattr(empty_model, "pv_avail_PV_roof")
        assert hasattr(empty_model, "pv_PV_roof")

        # check parameter values
        for t in empty_model.T:
            assert value(empty_model.pv_avail_PV_roof[t]) == pv_asset.pv_profile_kw[t]

    def test_register_constraints(self, pv_asset, empty_model):
        """Test that PV asset registers constraints correctly"""
        pv_asset.register_variables(empty_model)
        pv_asset.register_constraints(empty_model)

        assert hasattr(empty_model, "pv_limit_PV_roof")

        # constraint should limit PV tp avialble profile
        for t in empty_model.T:
            constraint_expr = empty_model.pv_limit_PV_roof[t].expr
            expected_expr = (
                empty_model.pv_PV_roof[t] 
                <= empty_model.pv_avail_PV_roof[t] 
            )

            assert constraint_expr.lhs == empty_model.pv_PV_roof[t]
            assert constraint_expr.rhs == empty_model.pv_avail_PV_roof[t]
            assert constraint_expr == expected_expr
             
    def test_get_results(self, pv_asset, empty_model):
        """Test extracting results from solved model."""
        pv_asset.register_variables(empty_model)

        # Manually set variable values for testing
        for t in empty_model.T:
            empty_model.pv_pv_1[t].value = float(t) * 0.5

        results = pv_asset.get_results(empty_model)
        assert "pv" in results
        assert len(results["pv"]) == 5
        assert results["pv"] == [0.0, 0.5, 1.0, 1.5, 2.0]        

    def test_to_dict(self, pv_asset):
        """Test serialization to dictionary."""
        d = pv_asset.to_dict()
        assert d["asset_id"] == "pv_1"
        assert d["customer_id"] == "test_customer"
        assert d["type"] == "PVAsset"
        assert "pv_profile_kw" in d

    def test_pv_profile_length_mismatch(self, simple_timeseries):
        """Test that PV profile length matches time periods."""
        with pytest.raises(AssertionError):
            # This should fail because profile length doesn't match
            simple_timeseries.pv_kw.append(99.0)
            PVAsset("cust1", "pv_1", simple_timeseries.pv_kw)

