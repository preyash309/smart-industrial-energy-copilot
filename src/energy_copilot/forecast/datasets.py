"""Public feature construction only. No events, latent state or simulator imports."""
import numpy as np
import pandas as pd
from .contracts import Dataset, assert_available
from energy_copilot.analytics.contracts import select_predictors

HEAT_FEATURES = ["hour", "weekday", "shift", "previous_heat_SEC", "previous_heat_duration",
                 "rolling_mean_SEC", "global_mean_SEC", "historical_duration_mean",
                 "context_PMP_01_flow_m3_h", "context_MILL_01_vibration_mm_s"]
HEALTH_CHANNELS = ["vibration_mm_s", "temp_C", "kW", "rpm", "flow_m3_h"]


def heat_dataset(heats, schema, run_id, seed, split, practice_loss, liquid_t):
    selected = select_predictors(heats, "heat_features", schema, "heat_energy", columns=HEAT_FEATURES)
    X = selected[HEAT_FEATURES].copy()
    # Candidate decision/static crucible capacity, never the completed charge register.
    X["practice_loss_kWh_t"] = practice_loss
    X["candidate_liquid_t"] = liquid_t
    meta = pd.DataFrame(dict(row_id=run_id+":"+heats.heat_id, run_id=run_id, seed=seed, split=split,
                             heat_id=heats.heat_id, forecast_origin=heats.start_time,
                             inputs_available_at=heats.start_time, target_start=heats.start_time,
                             target_end=heats.end_time, practice_loss_kWh_t=practice_loss))
    # Verify every used observation's source posting, not just row timestamps.
    for col in HEAT_FEATURES:
        at = heats[schema["tables"]["heat_features"]["columns"][col]["available_at"]]
        if (heats[col].notna() & (at.isna() | at.gt(heats.start_time))).any():
            raise ValueError(f"Late heat predictor {col}")
    assert_available(meta)
    return Dataset(X, meta, heats.kWh), Dataset(X.copy(), meta.copy(), heats.duration_min)


def direct_load_dataset(times, available, load, run_id, split_for_time, steps=96, lags=(1,2,4,96), windows=(4,96)):
    """96 direct targets per daily origin; ALL lag/window inputs end at origin.

    Seasonal naive reads target-minus-one-day, whose interval ends by the origin.
    No recursive forecasts and no target-indexed realized lag predictors.
    """
    times = pd.DatetimeIndex(times).as_unit("ns"); available = pd.DatetimeIndex(available).as_unit("ns")
    load = np.asarray(load, dtype=float)
    if not times.is_monotonic_increasing or not times.is_unique:
        raise ValueError("Nonchronological load series")
    step = pd.Timedelta(minutes=15)
    if not np.all(np.diff(times.asi8) == step.value):
        raise ValueError("Broken 15-minute coverage")
    X, meta, y = [], [], []
    for j in range(max(lags), len(times)-steps+1):
        origin = times[j]
        if origin != origin.normalize():
            continue
        if (available[j-max(lags):j] > origin).any():
            raise ValueError("Late published source in direct forecasting window")
        history = {}
        for lag in lags:
            history[f"load_lag_{lag}"] = load[j-lag]
        for w in windows:
            past = load[max(0,j-w):j]; finite = past[np.isfinite(past)]
            history[f"load_past_{w}_mean"] = float(finite.mean()) if len(finite) else np.nan
            history[f"load_past_{w}_std"] = float(finite.std()) if len(finite) else np.nan
        for h in range(1,steps+1):
            k=j+h-1; target=times[k]; part=split_for_time(target)
            if not np.isfinite(load[k]):
                continue  # Never recover a missing target from latent truth/future fill.
            seasonal_at=available[k-steps]
            if seasonal_at>origin:
                raise ValueError("Seasonal naive used future meter")
            minute=target.hour*60+target.minute
            features=dict(history, seasonal_naive=load[k-steps], horizon_slot=h,
                          target_hour=target.hour, target_weekday=target.dayofweek,
                          target_shift=target.hour//8, target_sin=np.sin(2*np.pi*minute/1440),
                          target_cos=np.cos(2*np.pi*minute/1440))
            X.append(features); y.append(load[k])
            meta.append(dict(row_id=f"{run_id}:{origin.isoformat()}:{h}", run_id=run_id, split=part,
                             forecast_origin=origin, inputs_available_at=origin,
                             target_start=target, target_end=target+step, horizon_slot=h,
                             source_max_available_at=max(available[j-1],seasonal_at)))
    return Dataset(pd.DataFrame(X), pd.DataFrame(meta), pd.Series(y, name="target"))


def health_features(slots, asset, run_id, seed, split, horizon_hours=24, stride=4):
    """Current completed sensor sample + strictly backward condition summaries.

    Runtime is past public running-slot occupancy, not latent degradation age.
    Rows during observed repair are excluded; right-edge outcomes are censored
    later by the target builder. No future episode identifiers live in X.
    """
    X = pd.DataFrame(index=slots.index)
    for channel in HEALTH_CHANNELS:
        x=slots[f"{asset}_{channel}"]
        X[channel]=x
        for w in (4,96):
            previous=x.shift(1).rolling(w,min_periods=1)
            X[f"{channel}_past_{w}_mean"]=previous.mean()
            X[f"{channel}_past_{w}_std"]=previous.std(ddof=0)
        X[f"{channel}_change_24h"]=x-x.shift(96)
    running=slots[f"{asset}_state"].eq("running").astype(float)
    X["runtime_past_24h"]=running.shift(1).rolling(96,min_periods=1).sum()*.25
    take=(np.arange(len(slots))%stride==stride-1) & ~slots[f"{asset}_state"].isin(["repair","repair_partial"])
    end=slots.interval_end.max()
    take &= slots.available_at + pd.Timedelta(hours=horizon_hours) <= end
    s=slots.loc[take]; X=X.loc[take].reset_index(drop=True)
    meta=pd.DataFrame(dict(row_id=run_id+":"+asset+":"+s.interval_end.astype(str),run_id=run_id,
                           seed=seed,split=split,asset_id=asset,forecast_origin=s.interval_end,
                           inputs_available_at=s.available_at,target_start=s.interval_end,
                           target_end=s.interval_end+pd.Timedelta(hours=horizon_hours))).reset_index(drop=True)
    assert_available(meta)
    return X, meta


def concatenate(datasets):
    return Dataset(pd.concat([d.X for d in datasets],ignore_index=True),
                   pd.concat([d.meta for d in datasets],ignore_index=True),
                   pd.concat([d.y for d in datasets],ignore_index=True))
