from pyomo.opt import SolverFactory, TerminationCondition

class SolverManager:
    def __init__(self, solver_name="highs", time_limit_sec=3):
        self.solver_name = solver_name
        self.time_limit_sec = time_limit_sec

    def solve(self, model):
        opt = SolverFactory(self.solver_name)
        opt.options["time_limit"] = self.time_limit_sec

        results = opt.solve(model, tee=False)
        tc = results.solver.termination_condition

        if tc not in (TerminationCondition.optimal, TerminationCondition.feasible):
            raise RuntimeError(f"Solver termination: {tc}")

        model.solutions.load_from(results)
        return model
