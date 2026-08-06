"""
Solver Configurations and Utilities for VPP Optimization.
Provides pre-configured solver settings and recommendations.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# SOLVER CAPABILITIES DATABASE
# ============================================================================

SOLVER_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    'highs': {
        'type': 'open_source',
        'license': 'MIT',
        'mip': True,
        'lp': True,
        'qp': False,
        'nlp': False,
        'performance': 'high',
        'recommended': True,
        'installation': 'pip install highspy',
        'notes': 'Default solver. Excellent for MIP problems. Fast and reliable.'
    },
    'glpk': {
        'type': 'open_source',
        'license': 'GPL',
        'mip': True,
        'lp': True,
        'qp': False,
        'nlp': False,
        'performance': 'medium',
        'recommended': True,
        'installation': 'pip install glpk',
        'notes': 'Good for LP and small MIP problems. GPL license may be restrictive for commercial use.'
    },
    'cbc': {
        'type': 'open_source',
        'license': 'EPL',
        'mip': True,
        'lp': True,
        'qp': True,
        'nlp': False,
        'performance': 'high',
        'recommended': True,
        'installation': 'pip install cbc',
        'notes': 'Supports quadratic objectives. EPL license is business-friendly.'
    },
    'gurobi': {
        'type': 'commercial',
        'license': 'Proprietary',
        'mip': True,
        'lp': True,
        'qp': True,
        'nlp': True,
        'performance': 'very_high',
        'recommended': False,
        'installation': 'pip install gurobipy',
        'notes': 'Best performance for large problems. Requires academic or commercial license.'
    },
    'cplex': {
        'type': 'commercial',
        'license': 'Proprietary',
        'mip': True,
        'lp': True,
        'qp': True,
        'nlp': True,
        'performance': 'very_high',
        'recommended': False,
        'installation': 'pip install cplex',
        'notes': 'Excellent performance. Requires license. Free for academic use.'
    },
    'scip': {
        'type': 'open_source',
        'license': 'Apache 2.0',
        'mip': True,
        'lp': True,
        'qp': True,
        'nlp': True,
        'performance': 'high',
        'recommended': True,
        'installation': 'pip install pyscipopt',
        'notes': 'Very powerful open-source solver. Requires SCIP installation.'
    }
}

# ============================================================================
# SOLVER RECOMMENDATIONS BY PROBLEM SIZE
# ============================================================================

SOLVER_RECOMMENDATIONS: Dict[str, Dict[str, Any]] = {
    'tiny': {
        'max_variables': 100,
        'max_constraints': 100,
        'recommended_solvers': ['highs', 'glpk', 'cbc'],
        'time_limit': 10,
        'description': 'Very small problems (e.g., single customer, few assets, <24 periods)'
    },
    'small': {
        'max_variables': 500,
        'max_constraints': 500,
        'recommended_solvers': ['highs', 'cbc', 'glpk'],
        'time_limit': 15,
        'description': 'Small problems (e.g., single customer, multiple assets, 24-48 periods)'
    },
    'medium': {
        'max_variables': 2000,
        'max_constraints': 2000,
        'recommended_solvers': ['highs', 'cbc', 'glpk'],
        'time_limit': 30,
        'description': 'Medium problems (e.g., multiple customers, many assets, 24-96 periods)'
    },
    'large': {
        'max_variables': 10000,
        'max_constraints': 10000,
        'recommended_solvers': ['highs', 'cbc', 'gurobi', 'cplex'],
        'time_limit': 60,
        'description': 'Large problems (e.g., many customers, complex assets, 96+ periods)'
    },
    'very_large': {
        'max_variables': 50000,
        'max_constraints': 50000,
        'recommended_solvers': ['gurobi', 'cplex', 'highs', 'cbc'],
        'time_limit': 120,
        'description': 'Very large problems requiring commercial solvers'
    }
}

# ============================================================================
# DEFAULT SOLVER SETTINGS
# ============================================================================

DEFAULT_SOLVER_SETTINGS: Dict[str, Dict[str, Any]] = {
    'highs': {
        'mip_gap': 0.01,
        'presolve': 'on',
        'parallel': 'on',
        'time_limit': 30
    },
    'glpk': {
        'mip_gap': 0.05,
        'presolve': True,
        'time_limit': 30
    },
    'cbc': {
        'ratioGap': 0.01,
        'preprocess': 'on',
        'threads': 4,
        'time_limit': 30
    },
    'gurobi': {
        'MIPGap': 0.01,
        'Presolve': 2,
        'Threads': 4,
        'TimeLimit': 30
    },
    'cplex': {
        'mip_tolerances_mipgap': 0.01,
        'preprocessing_presolve': True,
        'threads': 4,
        'TimeLimit': 30
    }
}

# ============================================================================
# PUBLIC FUNCTIONS
# ============================================================================

def get_solver_info(solver_name: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed information about a specific solver.

    Args:
        solver_name: Name of the solver (case-insensitive)

    Returns:
        Dictionary with solver information, or None if not found
    """
    solver_name = solver_name.lower()
    return SOLVER_CAPABILITIES.get(solver_name)

def list_available_solvers() -> List[str]:
    """
    List all configured solvers.

    Returns:
        List of solver names
    """
    return list(SOLVER_CAPABILITIES.keys())

def get_recommended_solvers(
    num_variables: int = 1000,
    num_constraints: Optional[int] = None,
    has_commercial_license: bool = False
) -> Dict[str, Any]:
    """
    Get recommended solvers based on problem size.

    Args:
        num_variables: Estimated number of variables in the model
        num_constraints: Estimated number of constraints (optional)
        has_commercial_license: Whether commercial solvers are available

    Returns:
        Dictionary with recommended solver configuration
    """
    # Determine problem size category
    size = 'very_large'
    for category, config in SOLVER_RECOMMENDATIONS.items():
        if num_variables <= config['max_variables']:
            if num_constraints is None or num_constraints <= config['max_constraints']:
                size = category
                break

    config = SOLVER_RECOMMENDATIONS[size].copy()

    # Filter out commercial solvers if not available
    if not has_commercial_license:
        config['recommended_solvers'] = [
            s for s in config['recommended_solvers']
            if SOLVER_CAPABILITIES.get(s, {}).get('type') != 'commercial'
        ]

    # Add solver info
    config['solvers_info'] = {
        s: get_solver_info(s) for s in config['recommended_solvers']
    }

    config['problem_size'] = size
    return config

def get_solver_settings(solver_name: str) -> Dict[str, Any]:
    """
    Get default settings for a specific solver.

    Args:
        solver_name: Name of the solver

    Returns:
        Dictionary with solver settings
    """
    solver_name = solver_name.lower()
    return DEFAULT_SOLVER_SETTINGS.get(solver_name, {})

def check_solver_availability(solver_name: str) -> bool:
    """
    Check if a solver is available for use.

    Args:
        solver_name: Name of the solver to check

    Returns:
        True if the solver is available, False otherwise
    """
    try:
        from pyomo.opt import SolverFactory
        solver = SolverFactory(solver_name.lower())
        return solver is not None
    except Exception:
        return False

def get_best_available_solver(
    preferred_solvers: Optional[List[str]] = None,
    has_commercial_license: bool = False
) -> Optional[str]:
    """
    Find the best available solver from a list of preferences.

    Args:
        preferred_solvers: List of solver names in order of preference
        has_commercial_license: Whether commercial solvers are available

    Returns:
        Name of the best available solver, or None if none are available
    """
    if preferred_solvers is None:
        preferred_solvers = ['highs', 'cbc', 'glpk']
        if has_commercial_license:
            preferred_solvers = ['gurobi', 'cplex', 'highs', 'cbc']

    for solver_name in preferred_solvers:
        if check_solver_availability(solver_name):
            return solver_name

    return None

def validate_solver_config(config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate a solver configuration dictionary.

    Args:
        config: Solver configuration dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(config, dict):
        return False, "Configuration must be a dictionary"

    if 'solver_name' not in config:
        return False, "Missing 'solver_name' in configuration"

    solver_name = config['solver_name'].lower()
    if solver_name not in SOLVER_CAPABILITIES:
        return False, f"Unknown solver: {solver_name}"

    if 'time_limit_sec' in config:
        if not isinstance(config['time_limit_sec'], (int, float)) or config['time_limit_sec'] <= 0:
            return False, "time_limit_sec must be a positive number"

    return True, ""