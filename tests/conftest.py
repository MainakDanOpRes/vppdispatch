"""Pytest fixtures for VPP Dispatch tests."""

import pytest
import numpy as np
from pyomo.environ import ConcreteModel, RangeSet
from src.vpp_dispatch.models.timeseries import CustomerTimeSeries
from src.vpp_dispatch.models.schemas import CustomerConfig, AssetConfig, AssetType
from src.vpp_dispatch.models.assets import PVAsset, BatteryAsset, FlexLoadAsset
from src.vpp_dispatch.models.constraints.power_balance import PowerBalanceConstraint
from src.vpp_dispatch.models.objectives.cost_minimisation import CostObjective
from src.vpp_dispatch.optimisation.model_builder import ModelBuilder
from src.vpp_dispatch.optimisation.solver_manager import SolverManager

# ============================================================================
# BASIC FIXTURES
# ============================================================================

@pytest.fixture
def time_periods():
    """Standard time periods for testing."""
    return 24

@pytest.fixture
def delta_t():
    """Time step duration."""
    return 1.0

@pytest.fixture
def sample_timeseries(time_periods):
    """Sample time series data."""
    t = np.linspace(0, 24, time_periods)
    return CustomerTimeSeries(
        pv_kw=[max(0, 10 * np.sin(ti * np.pi / 12)) for ti in t],
        fixed_load_kw=[5 + 3 * np.sin(ti * np.pi / 12) for ti in t],
        price_buy=[0.2 + 0.1 * np.sin(ti * np.pi / 12) for ti in t],
        price_sell=[0.1 + 0.05 * np.sin(ti * np.pi / 12) for ti in t]
    )

@pytest.fixture
def simple_timeseries():
    """Very simple time series for quick tests."""
    return CustomerTimeSeries(
        pv_kw=[0.0, 1.0, 2.0, 1.0, 0.0],
        fixed_load_kw=[1.0, 1.0, 1.0, 1.0, 1.0],
        price_buy=[0.2, 0.2, 0.2, 0.2, 0.2],
        price_sell=[0.1, 0.1, 0.1, 0.1, 0.1]
    )

@pytest.fixture
def empty_model():
    """Empty Pyomo model for testing."""
    m = ConcreteModel()
    m.T = RangeSet(0, 4)  # 5 time periods
    m.delta_t = 1.0
    return m

# ============================================================================
# ASSET FIXTURES
# ============================================================================

@pytest.fixture
def pv_asset(simple_timeseries):
    """Sample PV asset."""
    return PVAsset(
        customer_id="test_customer",
        asset_id="pv_1",
        pv_profile_kw=simple_timeseries.pv_kw
    )

@pytest.fixture
def battery_asset():
    """Sample battery asset."""
    return BatteryAsset(
        customer_id="test_customer",
        asset_id="battery_1",
        capacity_kwh=10.0,
        p_charge_max_kw=5.0,
        p_discharge_max_kw=5.0,
        soc_min=0.1,
        soc_max=0.9,
        eff_charge=0.95,
        eff_discharge=0.95,
        soc_initial=5.0
    )

@pytest.fixture
def flex_load_asset():
    """Sample flexible load asset."""
    return FlexLoadAsset(
        customer_id="test_customer",
        asset_id="flex_1",
        name="EV Charger",
        p_min_kw=0.0,
        p_max_kw=7.0,
        energy_required_kwh=14.0,
        time_window=(0, 4)  # Full time range for testing
    )

@pytest.fixture
def assets(pv_asset, battery_asset, flex_load_asset):
    """List of sample assets."""
    return [pv_asset, battery_asset, flex_load_asset]

# ============================================================================
# SCHEMA FIXTURES
# ============================================================================

@pytest.fixture
def customer_config(assets):
    """Sample customer configuration."""
    return CustomerConfig(
        customer_id="test_customer",
        time_periods=5,
        pv_kw=[0.0, 1.0, 2.0, 1.0, 0.0],
        fixed_load_kw=[1.0, 1.0, 1.0, 1.0, 1.0],
        price_buy=[0.2, 0.2, 0.2, 0.2, 0.2],
        price_sell=[0.1, 0.1, 0.1, 0.1, 0.1],
        assets=[
            AssetConfig(
                asset_id="pv_1",
                asset_type=AssetType.PV,
                pv_profile_kw=[0.0, 1.0, 2.0, 1.0, 0.0]
            ),
            AssetConfig(
                asset_id="battery_1",
                asset_type=AssetType.BATTERY,
                capacity_kwh=10.0,
                p_charge_max_kw=5.0,
                p_discharge_max_kw=5.0
            ),
            AssetConfig(
                asset_id="flex_1",
                asset_type=AssetType.FLEX_LOAD,
                p_min_kw=0.0,
                p_max_kw=7.0,
                energy_required_kwh=7.0,
                time_window=(0, 4)
            )
        ]
    )

# ============================================================================
# OPTIMIZATION FIXTURES
# ============================================================================

@pytest.fixture
def power_balance_constraint(simple_timeseries, assets):
    """Power balance constraint with assets."""
    return PowerBalanceConstraint(ts_data=simple_timeseries, assets=assets)

@pytest.fixture
def cost_objective():
    """Cost objective function."""
    return CostObjective(batt_degradation_cost_per_kwh=0.01)

@pytest.fixture
def model_builder(assets, power_balance_constraint, cost_objective):
    """Model builder with sample assets."""
    return ModelBuilder(
        assets=assets,
        power_balance=power_balance_constraint,
        objective=cost_objective
    )

@pytest.fixture
def built_model(model_builder, delta_t):
    """Fully built model."""
    return model_builder.build(T=5, delta_t=delta_t)

# ============================================================================
# MOCK FIXTURES
# ============================================================================

@pytest.fixture
def mock_solver(mocker):
    """Mock solver that always returns optimal."""
    mock = mocker.MagicMock()
    mock.solve.return_value.solver.termination_condition = "optimal"
    mock.solve.return_value.solver.status = "ok"
    return mock

@pytest.fixture(autouse=True)
def skip_solver_tests(request):
    """Skip tests that require actual solver if solver not available."""
    if "requires_solver" in request.keywords and not request.config.getoption("--run-solver-tests"):
        pytest.skip("Skipping solver tests (use --run-solver-tests to enable)")