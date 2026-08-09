"""
Battery Asset model for VPP Dispatch
"""

from typing import Dict, Any
from pyomo.environ import Var, Binary, NonNegativeReals, Constraint

from .base_asset import BaseAsset

class BatteryAsset(BaseAsset):
    """Battery storage asset model."""

    def __init__(
        self,
        customer_id: str,
        asset_id: str,
        capacity_kwh: float,
        p_charge_max_kw: float,
        p_discharge_max_kw: float,
        soc_min: float = 0.1,
        soc_max: float = 0.9,
        eff_charge: float = 0.95,
        eff_discharge: float = 0.95,
        p_charge_min_kw: float = 0,
        p_discharge_min_kw: float = 0,
        soc_initial: float = None,
        degradation_cost_per_kwh: float = 0.0,
        objective_weight: float = 1.0,
    ):
        super().__init__(customer_id, asset_id, objective_weight)

        # Sanity check on the arguments
        if capacity_kwh <= 0:
            raise ValueError(
                f"capacity_kwh must be > 0, but got {capacity_kwh}"
                )

        if soc_min > 1 or soc_min < 0:
            raise ValueError(
                f"soc_min should be between 0 and 1, but currently at {soc_min}"
                )

        if soc_max > 1 or soc_max < 0:
            raise ValueError(
                f"soc_max should be between 0 and 1, but currently at {soc_max}"
                )

        if soc_max < soc_min:
            raise ValueError(
                f"soc_min ({soc_min}) cannot be greater than "
                f"soc_max ({soc_max})"
                )

        if soc_initial is not None and not 0 <= soc_initial <= 1:
            raise ValueError(
                f"soc_initial should be between 0 and 1, but got {soc_initial}"
            )

        if not 0 < eff_charge <= 1:
            raise ValueError(
                f"eff_charge should be in (0, 1], but got {eff_charge}"
                )

        if not 0 < eff_discharge <= 1:
            raise ValueError(
                f"eff_discharge should be in (0, 1], but got {eff_discharge}"
                )

        if p_charge_max_kw < 0:
            raise ValueError(
                f"p_charge_max_kw must be >= 0, but got {p_charge_max_kw}"
            )

        if p_discharge_max_kw < 0:
            raise ValueError(
                f"p_discharge_max_kw must be >= 0, but got {p_discharge_max_kw}"
            )

        if p_charge_min_kw < 0:
            raise ValueError(
                f"p_charge_min_kw must be >= 0, but got {p_charge_min_kw}"
            )
        
        if p_discharge_min_kw < 0:
            raise ValueError(
                f"p_discharge_min_kw must be >= 0, but got {p_discharge_min_kw}"
            )

        self.capacity_kwh = capacity_kwh
        self.p_charge_max_kw = p_charge_max_kw
        self.p_discharge_max_kw = p_discharge_max_kw
        self.p_charge_min_kw = p_charge_min_kw
        self.p_discharge_min_kw = p_discharge_min_kw
        self.soc_min = soc_min * capacity_kwh
        self.soc_max = soc_max * capacity_kwh
        self.eff_charge = eff_charge
        self.eff_discharge = eff_discharge
        self.soc_initial = (
            soc_initial * capacity_kwh 
            if soc_initial is not None
            else 0.5 * capacity_kwh
            )
        self.degradation_cost_per_kwh = degradation_cost_per_kwh

    def register_variables(self, m):
        """Register battery variables."""
        setattr(m, f'p_ch_{self.var_id}', Var(m.T, within=NonNegativeReals))
        setattr(m, f'p_dis_{self.var_id}', Var(m.T, within=NonNegativeReals))
        setattr(m, f'u_{self.var_id}', Var(m.T, within=Binary))
        setattr(m, f'soc_{self.var_id}', Var(m.T, within=NonNegativeReals))

    def register_constraints(self, m):
        """Register battery constraints."""
        p_ch = getattr(m, f'p_ch_{self.var_id}')
        p_dis = getattr(m, f'p_dis_{self.var_id}')
        u = getattr(m, f'u_{self.var_id}')
        soc = getattr(m, f'soc_{self.var_id}')

        def soc_lo(m, t): return soc[t] >= self.soc_min
        def soc_hi(m, t): return soc[t] <= self.soc_max
        def charge_ub(m, t): return p_ch[t] <= self.p_charge_max_kw * u[t]
        def disch_ub(m, t): return p_dis[t] <= self.p_discharge_max_kw * (1 - u[t])
        def charge_lb(m, t): return p_ch[t] >= self.p_charge_min_kw * u[t]
        def disch_lb(m, t): return p_dis[t] >= self.p_discharge_min_kw * (1 - u[t])

        def soc_rule(m, t):
            if t == m.T.first():
                return soc[t] == self.soc_initial + (
                    self.eff_charge * p_ch[t] * m.delta_t
                    - (1 / self.eff_discharge) * p_dis[t] * m.delta_t
                )
            return soc[t] == soc[t - 1] + (
                self.eff_charge * p_ch[t] * m.delta_t
                - (1 / self.eff_discharge) * p_dis[t] * m.delta_t
            )

        setattr(m, f'battery_soc_{self.var_id}', Constraint(m.T, rule=soc_rule))
        setattr(m, f'c_soc_lo_{self.var_id}', Constraint(m.T, rule=soc_lo))
        setattr(m, f'c_soc_hi_{self.var_id}', Constraint(m.T, rule=soc_hi))
        setattr(m, f'c_charge_ub_{self.var_id}', Constraint(m.T, rule=charge_ub))
        setattr(m, f'c_disch_ub_{self.var_id}', Constraint(m.T, rule=disch_ub))
        setattr(m, f'c_charge_lb_{self.var_id}', Constraint(m.T, rule=charge_lb))
        setattr(m, f'c_disch_lb_{self.var_id}', Constraint(m.T, rule=disch_lb))

    def register_objectives(self, m):
        """
        Calculate the battery degradation cost for the objective function.
        Cost = degradation_rate * total_energy_cycled
        """
        # If there is no cost associated with degradation, return 0.0
        if self.degradation_cost_per_kwh <= 0:
            return 0.0
            
        # Dynamically fetch this specific battery's variables from the Pyomo model
        p_ch = getattr(m, f'p_ch_{self.var_id}')
        p_dis = getattr(m, f'p_dis_{self.var_id}')
        
        # Calculate total energy cycled: sum of (Charge Power + Discharge Power) * delta_t
        # Multiply by the degradation cost per kWh
        degradation_expr = self.degradation_cost_per_kwh * sum(
            (p_ch[t] + p_dis[t]) * m.delta_t for t in m.T
        )
        
        return degradation_expr

    def get_results(self, m) -> Dict[str, Any]:
        """Extract battery results."""
        results = {}
        for var_name in ['p_ch', 'p_dis', 'soc']:
            var = getattr(m, f'{var_name}_{self.var_id}', None)
            if var is not None:
                results[var_name] = [var[t].value for t in m.T]
        return results

    def to_dict(self) -> Dict[str, Any]:
        """Serialize Battery asset to dictionary."""
        d = super().to_dict()
        d.update({
            "capacity_kwh": self.capacity_kwh,
            "p_charge_max_kw": self.p_charge_max_kw,
            "p_discharge_max_kw": self.p_discharge_max_kw,
            "soc_min": self.soc_min,
            "soc_max": self.soc_max,
            "eff_charge": self.eff_charge,
            "eff_discharge": self.eff_discharge,
            "soc_initial": self.soc_initial,
            "degradation_cost_per_kwh": self.degradation_cost_per_kwh
        })
        return d