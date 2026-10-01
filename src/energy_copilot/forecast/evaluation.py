"""Future events used ONLY for targets/evaluation, never for feature building."""
import numpy as np
import pandas as pd


def failure_targets(meta, events, asset):
    starts = events.loc[events.asset_id.eq(asset) & events.type.eq("failure"), "start"].sort_values()
    times=pd.DatetimeIndex(starts).as_unit("ns").asi8
    origins=pd.DatetimeIndex(meta.forecast_origin).as_unit("ns").asi8
    ends=pd.DatetimeIndex(meta.target_end).as_unit("ns").asi8
    following=np.searchsorted(times,origins,side="right")
    sentinel=np.iinfo(np.int64).max
    next_event=np.r_[times,sentinel][following]
    return pd.Series((next_event<=ends).astype(int)), pd.Series(np.where(next_event==sentinel,"censored_after_horizon",following.astype(str)))
