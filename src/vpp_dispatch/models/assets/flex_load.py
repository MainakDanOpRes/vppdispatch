from typing import Tuple, Dict, Any, List
from pyomo.environ import Var, NonNegativeReals, Binary, Constraint, value

from .base_asset import BaseAsset

class FlexLoadAsset(BaseAsset):
    """Unified Flexible Load Asset Model supporting Continuous, Shiftable, and On/Off modes."""

    def __init__(
        self,
        customer_id: str,
        asset_id: str,
        name: str = "FlexLoad",
        is_continuous: bool = True,
        is_shiftable: bool = False,
        is_on_off: bool = False,
        p_min_kw: float = 0.0,
        p_max_kw: float = 7.0,
        p_on_kw: float = 5.0,
        energy_required_kwh: float = 14.0,
        load_profile: List[float] = None,
        time_window: Tuple[int, int] = (0, 23),
        objective_weight: float = 1.0,
        discomfort_cost: float = 0.0,
    ):
        super().__init__(customer_id, asset_id, objective_weight)
        
        # Check if multiple/all binary options are True
        active_modes = sum([is_continuous, is_shiftable, is_on_off])
        if active_modes > 1:
            raise ValueError(
                f"Asset {asset_id}: Conflicting load types. Only one of 'is_continuous', "
                f"'is_shiftable', or 'is_on_off' can be True."
            )
        if active_modes == 0:
            raise ValueError(f"Asset {asset_id}: At least one load type flag must be True.")

        self.name = name
        self.is_continuous = is_continuous
        self.is_shiftable = is_shiftable
        self.is_on_off = is_on_off
        
        self.p_min_kw = p_min_kw
        self.p_max_kw = p_max_kw
        self.p_on_kw = p_on_kw
        self.energy_required_kwh = energy_required_kwh
        self.load_profile = load_profile if load_profile is not None else []
        self.profile_length = len(self.load_profile)
        self.t_start, self.t_end = time_window
        self.discomfort_cost = discomfort_cost

    def register_variables(self, m):
        """Register flexible load variables."""
        # Continuous power variable used by the wider VPP dispatch (common to all)
        if not hasattr(m, f'flex_{self.asset_id}'):
            setattr(m, f'flex_{self.asset_id}', Var(m.T, domain=NonNegativeReals))
        
        # Binary state variable (Needed for Continuous and On/Off)
        if self.is_continuous or self.is_on_off:
            setattr(m, f'u_flex_{self.asset_id}', Var(m.T, domain=Binary))
                
        # Start-up transition tracker (Needed for all modes)
        setattr(m, f'v_start_{self.asset_id}', Var(m.T, domain=Binary))
        
    def register_constraints(self, m):
        """Register flexible load constraints based on the active mode."""
        flex_var = getattr(m, f'flex_{self.asset_id}')
        v_start = getattr(m, f'v_start_{self.asset_id}')
        dt = m.delta_t

        if self.is_continuous or self.is_on_off:
            u_flex = getattr(m, f'u_flex_{self.asset_id}')

            # Common: Time Window Rule
            def time_window_rule(m, t):
                if t < self.t_start or t > self.t_end:
                    return u_flex[t] == 0
                return Constraint.Skip
            setattr(m, f'flex_window_{self.asset_id}', Constraint(m.T, rule=time_window_rule))

            # Common: Start-up tracker
            def startup_rule(m, t):
                t_list = list(m.T)
                t_idx = t_list.index(t)
                if t_idx == 0:
                    return v_start[t] >= u_flex[t]
                prev_t = t_list[t_idx - 1]
                return v_start[t] >= u_flex[t] - u_flex[prev_t]
            setattr(m, f'flex_startup_{self.asset_id}', Constraint(m.T, rule=startup_rule))

            # Specifics for Continuous
            if self.is_continuous:
                def flex_min_rule(m, t):
                    return flex_var[t] >= self.p_min_kw * u_flex[t]
                def flex_max_rule(m, t):
                    return flex_var[t] <= self.p_max_kw * u_flex[t]
                def energy_req_rule(m):
                    return sum(flex_var[t] * dt for t in m.T) == self.energy_required_kwh
                
                setattr(m, f'flex_min_{self.asset_id}', Constraint(m.T, rule=flex_min_rule))
                setattr(m, f'flex_max_{self.asset_id}', Constraint(m.T, rule=flex_max_rule))
                setattr(m, f'flex_energy_{self.asset_id}', Constraint(rule=energy_req_rule))

            # Specifics for On/Off
            if self.is_on_off:
                def on_power_rule(m, t):
                    return flex_var[t] == u_flex[t] * self.p_on_kw
                def on_energy_req_rule(m):
                    return sum(u_flex[t] * self.p_on_kw * dt for t in m.T) >= self.energy_required_kwh
                def single_activation_rule(m):
                    return sum(v_start[t] for t in m.T) <= 1

                setattr(m, f'flex_on_power_{self.asset_id}', Constraint(m.T, rule=on_power_rule))
                setattr(m, f'flex_on_energy_{self.asset_id}', Constraint(rule=on_energy_req_rule))
                setattr(m, f'flex_single_act_{self.asset_id}', Constraint(rule=single_activation_rule))

        # Specifics for Shiftable Profile
        elif self.is_shiftable:
            def single_start_rule(m):
                return sum(v_start[t] for t in m.T) == 1

            def start_window_rule(m, t):
                latest_possible_start = self.t_end - self.profile_length + 1
                if t < self.t_start or t > latest_possible_start:
                    return v_start[t] == 0
                return Constraint.Skip

            def power_profile_rule(m, t):
                power_at_t = 0.0
                for k, p_val in enumerate(self.load_profile):
                    start_t = t - k
                    if start_t in m.T:
                        power_at_t += v_start[start_t] * p_val
                return flex_var[t] == power_at_t

            setattr(m, f'shift_single_start_{self.asset_id}', Constraint(rule=single_start_rule))
            setattr(m, f'shift_window_{self.asset_id}', Constraint(m.T, rule=start_window_rule))
            setattr(m, f'shift_power_{self.asset_id}', Constraint(m.T, rule=power_profile_rule))

    def register_objectives(self, m):
        """Calculate discomfort penalty for delaying the flexible load."""
        if self.discomfort_cost <= 0:
            return 0.0
            
        if self.is_shiftable:
            v_start = getattr(m, f'v_start_{self.asset_id}')
            return self.discomfort_cost * sum(
                (t - self.t_start) * v_start[t]
                for t in m.T if t >= self.t_start
            )
        else:
            flex_var = getattr(m, f'flex_{self.asset_id}')
            return self.discomfort_cost * sum(
                (t - self.t_start) * flex_var[t] * m.delta_t 
                for t in m.T if t >= self.t_start
            )

    def get_results(self, m) -> Dict[str, Any]:
        """Extract flexible load results."""
        results = {}
        flex_var = getattr(m, f'flex_{self.asset_id}', None)
        v_start = getattr(m, f'v_start_{self.asset_id}', None)
        
        if flex_var is not None:
            results['flex_power_kw'] = [value(flex_var[t]) for t in m.T]
        if v_start is not None:
            results['start_signal'] = [value(v_start[t]) for t in m.T]

        if self.is_continuous or self.is_on_off:
            u_flex = getattr(m, f'u_flex_{self.asset_id}', None)
            if u_flex is not None:
                results['is_on'] = [value(u_flex[t]) for t in m.T]
            
        return results

    def to_dict(self) -> Dict[str, Any]:
        """Serialize unified Flex Load asset to dictionary."""
        d = super().to_dict()
        d.update({
            "is_continuous": self.is_continuous,
            "is_shiftable": self.is_shiftable,
            "is_on_off": self.is_on_off,
            "time_window": (self.t_start, self.t_end),
            "discomfort_cost": self.discomfort_cost
        })
        if self.is_continuous:
            d.update({"p_min_kw": self.p_min_kw, "p_max_kw": self.p_max_kw, "energy_required_kwh": self.energy_required_kwh})
        elif self.is_on_off:
            d.update({"p_on_kw": self.p_on_kw, "energy_required_kwh": self.energy_required_kwh})[cite: 2]
        elif self.is_shiftable:
            d.update({"load_profile": self.load_profile})
            
        return d