class HeuristicFallback:
    def __init__(self, charge_quantile=0.3, discharge_quantile=0.7):
        self.charge_q = charge_quantile
        self.discharge_q = discharge_quantile

    def run(self, ts, battery_conf, flex_conf=None):
        T = ts.T
        prices = ts.price_buy

        low_thr = sorted(prices)[int(self.charge_q * T)]
        high_thr = sorted(prices)[int(self.discharge_q * T)]

        p_ch = [0.0] * T
        p_dis = [0.0] * T
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

        flex = [0.0] * T
        if flex_conf:
            window = range(flex_conf.t_start, flex_conf.t_end + 1)
            sorted_window = sorted(window, key=lambda t: prices[t])
            energy = flex_conf.energy_required_kwh
            dt = 1.0
            for t in sorted_window:
                if energy <= 0:
                    break
                flex[t] = min(flex_conf.p_max_kw, energy / dt)
                energy -= flex[t] * dt

        return {
            "p_ch": p_ch,
            "p_dis": p_dis,
            "soc": soc,
            "flex": flex,
        }
