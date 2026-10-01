"""Transparent prequential means/ranges; no ML training and no fault labels."""
import numpy as np
import pandas as pd


def heat_history(heats, parameters):
    rows = []
    for row in heats.itertuples():
        past = heats.loc[heats.available_at.le(row.start_time) & heats.heat_id.ne(row.heat_id)]
        past = past.sort_values(["available_at", "heat_id"])
        valid = past.dropna(subset=["SEC_kWh_per_t", "duration_min", "liquid_t"])
        rolling = valid.tail(parameters["history_window"])
        same_shift = valid.loc[valid["shift"].eq(row.shift)]
        grouped = same_shift.loc[same_shift.working_day.eq(row.working_day)]
        n = len(valid)
        if len(grouped) >= parameters["group_min_history"]:
            selected = grouped; method = "prior_shift_working_group_mean"
        elif len(rolling) >= parameters["min_history"]:
            selected = rolling; method = "prior_rolling_mean"
        elif n >= parameters["min_history"]:
            selected = valid; method = "prior_global_mean"
        else:
            selected = valid.iloc[:0]; method = "insufficient_history"
        lo, hi = parameters["range_quantiles"]
        energy = selected.SEC_kWh_per_t
        expectation = energy.mean()
        liquid = selected.liquid_t.mean()
        rows.append(dict(previous_heat_SEC=valid.SEC_kWh_per_t.iloc[-1] if n else np.nan,
            previous_heat_duration=valid.duration_min.iloc[-1] if n else np.nan,
            previous_heat_available_at=valid.available_at.iloc[-1] if n else pd.NaT,
            history_count=n, global_mean_SEC=valid.SEC_kWh_per_t.mean(),
            shift_mean_SEC=same_shift.SEC_kWh_per_t.mean(), rolling_mean_SEC=rolling.SEC_kWh_per_t.mean(),
            historical_duration_mean=selected.duration_min.mean(), historical_duration_sd=selected.duration_min.std(),
            expected_SEC=expectation, expected_SEC_sd=energy.std(),
            expected_SEC_low=energy.quantile(lo), expected_SEC_high=energy.quantile(hi),
            expected_n=len(selected), expected_method=method, expected_liquid_t=liquid,
            expected_kWh=expectation*liquid, baseline_available_at=row.start_time))
    return pd.DataFrame(rows, index=heats.index)
