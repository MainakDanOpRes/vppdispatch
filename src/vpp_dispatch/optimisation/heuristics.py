class HeuristicFallback:
    def __init__(self, charge_quantile=0.3, discharge_quantile=0.7):
        self.charge_q = charge_quantile
        self.discharge_q = discharge_quantile

    def run(self, ts, assets):
        """
        Simple price-threshold heuristic used when the LP/MIP solver fails.

        Args:
            ts: CustomerTimeSeries with price_buy etc.
            assets: list of asset objects for this customer (the first
                BatteryAsset and first FlexLoadAsset found are used, matching
                how the legacy single-battery/single-flex-load dispatch works)
        """
        # Local import avoids a circular import at module load time.
        from ..models.assets import BatteryAsset, FlexLoadAsset

        battery_conf = next((a for a in assets if isinstance(a, BatteryAsset)), None)
        flex_conf = next((a for a in assets if isinstance(a, FlexLoadAsset)), None)

        T = ts.T
        prices = ts.price_buy

        p_ch = [0.0] * T
        p_dis = [0.0] * T
        soc = []

        if battery_conf is not None:
            low_thr = sorted(prices)[int(self.charge_q * T)]
            high_thr = sorted(prices)[int(self.discharge_q * T)]
            soc = [battery_conf.soc_initial]

            for t in range(T):
                if prices[t] <= low_thr:
                    p_ch[t] = battery_conf.p_charge_max_kw
                elif prices[t] >= high_thr:
                    p_dis[t] = battery_conf.p_discharge_max_kw

                new_soc = soc[-1] + (
                    battery_conf.eff_charge * p_ch[t]
                    - (1 / battery_conf.eff_discharge) * p_dis[t]
                )
                new_soc = max(battery_conf.soc_min, min(battery_conf.soc_max, new_soc))
                soc.append(new_soc)

            soc = soc[1:]
        else:
            soc = [0.0] * T

        flex = [0.0] * T
        if flex_conf is not None:
            t_start = getattr(flex_conf, 't_start', 0)
            t_end = getattr(flex_conf, 't_end', T - 1)
            window = [t for t in range(t_start, t_end + 1) if t < T]
            sorted_window = sorted(window, key=lambda t: prices[t])
            energy = flex_conf.energy_required_kwh
            p_max = getattr(flex_conf, 'p_max_kw', None) or getattr(flex_conf, 'p_on_kw', 0.0)
            dt = 1.0
            for t in sorted_window:
                if energy <= 0:
                    break
                flex[t] = min(p_max, energy / dt)
                energy -= flex[t] * dt

        # Net grid draw implied by this heuristic schedule: fixed load + charge
        # - solar - discharge - flex-load-shed. This is intentionally a rough
        # estimate (fallback path only), not a fully balanced power flow.
        pv_kw = getattr(ts, 'pv_kw', [0.0] * T)
        fixed_load_kw = getattr(ts, 'fixed_load_kw', [0.0] * T)
        p_grid = [
            fixed_load_kw[t] + p_ch[t] + flex[t] - pv_kw[t] - p_dis[t]
            for t in range(T)
        ]

        objective = sum(prices[t] * max(p_grid[t], 0.0) for t in range(T))

        return {
            "p_ch": p_ch,
            "p_dis": p_dis,
            "soc": soc,
            "flex": flex,
            "p_grid": p_grid,
            "objective": objective,
        }
