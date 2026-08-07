"""
Solver Manager for VPP Optimization
Manages solver selection, configuration, and fallback mechanisms.
"""

from typing import Dict, Any, Optional, Tuple, List
from threading import Lock
from pyomo.environ import SolverFactory, SolverStatus, TerminationCondition
from pyomo.opt import SolverResults
import logging

logger = logging.getLogger(__name__)

# Pyomo's solver interfaces (in particular the legacy HiGHS interface) capture
# stdout/stderr via a shared TeeStream that is not safe to use from multiple
# threads at once. batch_dispatch.py solves several customers concurrently via
# ThreadPoolExecutor, which without this lock reliably deadlocks or raises
# "Captured output does not match sys.stdout" / TeeStream errors. Model
# building and result extraction are pure Python and stay concurrent; only the
# actual solver.solve() call is serialized.
_SOLVE_LOCK = Lock()

# Pre-configured solver settings optimized for VPP dispatch problems
SOLVER_CONFIGS = {
    'highs': {
        'time_limit': 30,
        'options': {
            'mip_gap': 0.01,
            'presolve': 'on',
            'parallel': 'on'
        },
        'type': 'open_source',
        'priority': 1
    },
    'glpk': {
        'time_limit': 30,
        'options': {
            'mip_gap': 0.05,
            'presolve': True
        },
        'type': 'open_source',
        'priority': 2
    },
    'cbc': {
        'time_limit': 30,
        'options': {
            'ratioGap': 0.01,
            'preprocess': 'on',
            'threads': 4
        },
        'type': 'open_source',
        'priority': 3
    },
    'gurobi': {
        'time_limit': 30,
        'options': {
            'MIPGap': 0.01,
            'Presolve': 2,
            'Threads': 4
        },
        'type': 'commercial',
        'priority': 4
    },
    'cplex': {
        'time_limit': 30,
        'options': {
            'mip_tolerances_mipgap': 0.01,
            'preprocessing_presolve': True,
            'threads': 4
        },
        'type': 'commercial',
        'priority': 5
    }
}

# Fallback solver chain (in order of preference)
FALLBACK_SOLVERS = ['highs', 'cbc', 'glpk']

class SolverManager:
    """
    Manages solver selection, configuration, and automatic fallback mechanisms.

    Features:
    - Primary solver with configurable time limit
    - Automatic fallback to alternative solvers if primary fails
    - Detailed status reporting
    - Solver availability checking
    """

    def __init__(
        self,
        solver_name: str = "highs",
        time_limit_sec: int = 30,
        use_fallback: bool = True,
        fallback_solvers: Optional[List[str]] = None
    ):
        """
        Initialize the solver manager.

        Args:
            solver_name: Name of the primary solver to use (default: 'highs')
            time_limit_sec: Time limit in seconds for each solver attempt (default: 30)
            use_fallback: Whether to use fallback solvers if primary fails (default: True)
            fallback_solvers: List of fallback solver names in priority order.
                             If None, uses FALLBACK_SOLVERS default.
        """
        self.solver_name = solver_name.lower()
        self.time_limit_sec = time_limit_sec
        self.use_fallback = use_fallback
        self.fallback_solvers = fallback_solvers or FALLBACK_SOLVERS
        self.last_solver_used = None
        self.last_error = None

    def _get_solver_options(self, solver_name: str) -> Dict[str, Any]:
        """Get solver-specific options."""
        config = SOLVER_CONFIGS.get(solver_name, {})
        options = config.get('options', {})

        # Set time limit based on solver type
        if solver_name == 'highs':
            options['time_limit'] = self.time_limit_sec
        elif solver_name == 'glpk':
            options['tm_lim'] = self.time_limit_sec * 1000  # milliseconds
        elif solver_name == 'cbc':
            options['sec'] = self.time_limit_sec
        elif solver_name in ['gurobi', 'cplex']:
            options['TimeLimit'] = self.time_limit_sec

        return options

    def _create_solver(self, solver_name: str) -> Optional[object]:
        """Create a solver instance."""
        try:
            solver = SolverFactory(solver_name)
            if solver is None:
                logger.warning(f"Solver '{solver_name}' not available")
                return None

            # Configure solver options
            options = self._get_solver_options(solver_name)
            if hasattr(solver, 'options') and options:
                solver.options.update(options)

            logger.debug(f"Created solver '{solver_name}' with options: {options}")
            return solver

        except Exception as e:
            logger.warning(f"Failed to create solver '{solver_name}': {e}")
            return None

    def solve(self, model) -> Tuple[object, Dict[str, Any]]:
        """
        Solve the model using the configured solver(s).

        Args:
            model: Pyomo model to solve

        Returns:
            Tuple of (model, status_dict) where status_dict contains:
            - success: bool indicating if a solution was found
            - solver: name of the solver that succeeded (or None)
            - status: 'optimal', 'feasible', or 'failed'
            - termination_condition: solver's termination condition
            - time_seconds: solving time in seconds
            - tried_solvers: list of solvers attempted
            - error: error message if all solvers failed
        """
        tried_solvers = []
        self.last_error = None
        self.last_solver_used = None

        # Build list of solvers to try (primary first, then fallbacks)
        solvers_to_try = []

        # Add primary solver if it's not already in fallback list
        if self.solver_name not in self.fallback_solvers:
            solvers_to_try.append(self.solver_name)

        # Add fallback solvers (excluding primary if it was added above)
        for s in self.fallback_solvers:
            if s != self.solver_name and s not in solvers_to_try:
                solvers_to_try.append(s)

        # If primary is in fallback list but not at the front, reorder
        if self.solver_name in self.fallback_solvers and self.solver_name not in solvers_to_try:
            solvers_to_try.insert(0, self.solver_name)

        # If no solvers specified, use all available
        if not solvers_to_try:
            solvers_to_try = list(SOLVER_CONFIGS.keys())

        logger.info(f"Attempting to solve with solvers: {solvers_to_try}")

        for solver_name in solvers_to_try:
            solver = self._create_solver(solver_name)
            if solver is None:
                continue

            tried_solvers.append(solver_name)
            self.last_solver_used = solver_name

            try:
                logger.info(f"Solving with {solver_name}...")
                with _SOLVE_LOCK:
                    results = solver.solve(model, tee=False)

                # Check solution status
                solver_status = results.solver.status
                termination_condition = results.solver.termination_condition
                try:
                    solve_time = results.solver.wallclock_time
                    solve_time = float(solve_time)
                except (AttributeError, TypeError, ValueError):
                    solve_time = 0.0

                if solver_status == SolverStatus.ok:
                    if termination_condition == TerminationCondition.optimal:
                        logger.info(f"Solver {solver_name} found optimal solution in {solve_time:.2f}s")
                        return model, {
                            'success': True,
                            'solver': solver_name,
                            'status': 'optimal',
                            'termination_condition': str(termination_condition),
                            'time_seconds': solve_time,
                            'tried_solvers': tried_solvers
                        }
                    elif termination_condition == TerminationCondition.feasible:
                        logger.info(f"Solver {solver_name} found feasible solution in {solve_time:.2f}s")
                        return model, {
                            'success': True,
                            'solver': solver_name,
                            'status': 'feasible',
                            'termination_condition': str(termination_condition),
                            'time_seconds': solve_time,
                            'tried_solvers': tried_solvers
                        }

                # Solution not optimal/feasible, continue to next solver
                self.last_error = f"Solver {solver_name}: {termination_condition}"
                logger.warning(self.last_error)

            except Exception as e:
                self.last_error = f"Solver {solver_name} error: {str(e)}"
                logger.error(self.last_error)

        # All solvers failed
        logger.error(f"All solvers failed. Last error: {self.last_error}")
        return model, {
            'success': False,
            'solver': None,
            'status': 'failed',
            'error': self.last_error or 'All solvers failed to find a solution',
            'tried_solvers': tried_solvers
        }

    def get_available_solvers(self) -> List[str]:
        """
        Get list of available solvers on this system.

        Returns:
            List of solver names that are available
        """
        available = []
        for solver_name in SOLVER_CONFIGS.keys():
            solver = self._create_solver(solver_name)
            if solver is not None:
                available.append(solver_name)
        return available

    def check_solver(self, solver_name: str) -> Dict[str, Any]:
        """
        Check if a specific solver is available and get its info.

        Args:
            solver_name: Name of the solver to check

        Returns:
            Dictionary with solver info and availability
        """
        config = SOLVER_CONFIGS.get(solver_name.lower(), {})
        solver = self._create_solver(solver_name.lower())

        return {
            'name': solver_name,
            'available': solver is not None,
            'type': config.get('type', 'unknown'),
            'priority': config.get('priority', 999),
            'options': config.get('options', {})
        }