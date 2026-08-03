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
        from pyomo.environ import value
        
        pv_asset.register_variables(empty_model)
        
        assert hasattr(empty_model, f"pv_avail_{pv_asset.asset_id}")
        assert hasattr(empty_model, f"pv_{pv_asset.asset_id}")
        
        # Get the parameter object dynamically
        pv_avail_param = getattr(empty_model, f"pv_avail_{pv_asset.asset_id}")
        
        # check parameter values
        for t in empty_model.T:
            assert value(pv_avail_param[t]) == pv_asset.pv_profile_kw[t]
            
    def test_register_constraints(self, pv_asset, empty_model):
        """Test that PV asset registers constraints correctly"""
        pv_asset.register_variables(empty_model)
        pv_asset.register_constraints(empty_model)
        
        assert hasattr(empty_model, f"pv_limit_{pv_asset.asset_id}")
        
        # Get the constraint, variable, and parameter dynamically
        pv_limit_constraint = getattr(empty_model, f"pv_limit_{pv_asset.asset_id}")
        pv_var = getattr(empty_model, f"pv_{pv_asset.asset_id}")
        pv_avail_param = getattr(empty_model, f"pv_avail_{pv_asset.asset_id}")

        for t in empty_model.T:
            # constraint_expr = pv_limit_constraint[t].expr
            # expected_expr = (pv_var[t] <= pv_avail_param[t])

            assert pv_limit_constraint[t].body == pv_var[t]
            assert pv_limit_constraint[t].upper == pv_avail_param[t]
            assert pv_limit_constraint[t].lower == None
             
    def test_get_results(self, pv_asset, empty_model):
        """Test extracting results from solved model."""
        pv_asset.register_variables(empty_model)
        
        # Get the variable object dynamically
        pv_var = getattr(empty_model, f"pv_{pv_asset.asset_id}")
        
        # Manually set variable values for testing
        for t in empty_model.T:
            pv_var[t].value = float(t) * 0.5
            
        results = pv_asset.get_results(empty_model)
        
        # Look for the dynamic key instead of "pv"
        expected_key = f"pv_{pv_asset.asset_id}"
        assert expected_key in results
        assert results[expected_key] == [float(t) * 0.5 for t in empty_model.T]       

    def test_to_dict(self, pv_asset):
        """Test serialization to dictionary."""
        d = pv_asset.to_dict()
        assert d["asset_id"] == pv_asset.asset_id
        assert d["customer_id"] == pv_asset.customer_id
        assert d["type"] == "PVAsset"
        
        # Look for the dynamic profile key
        expected_profile_key = f"pv_{pv_asset.asset_id}_profile_kw"
        assert expected_profile_key in d
        assert d[expected_profile_key] == pv_asset.pv_profile_kw

    def test_pv_profile_length_mismatch(self, simple_timeseries, empty_model):
        """Test that PV profile length matches time periods."""
        from src.vpp_dispatch.models.assets.pv import PVAsset
        
        # Create an asset with a profile that is too short (e.g., length 2)
        bad_pv_asset = PVAsset("test_customer", "pv_short", [1.0, 2.0])
        
        # Pyomo will raise an IndexError when it tries to initialize the 
        # parameter for all time periods t in empty_model.T
        with pytest.raises(IndexError):
            bad_pv_asset.register_variables(empty_model)

