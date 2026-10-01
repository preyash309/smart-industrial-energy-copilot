"""Public, versioned service eligibility; classifier operating thresholds are ignored."""
from dataclasses import dataclass,asdict
import math
import pandas as pd
from .contracts import settings


@dataclass(frozen=True)
class MaintenancePolicy:
    mill_probability: float
    pump_probability: float
    persistence_observations: int
    warning_probability: float = 0.3
    minimum_valid_recent_fraction: float = 0.75

    def validate(self):
        if any(not math.isfinite(x) or not 0<=x<=1 for x in (self.mill_probability,self.pump_probability,self.warning_probability,self.minimum_valid_recent_fraction)):
            raise ValueError('Invalid maintenance policy probabilities')
        if self.persistence_observations not in (1,2):raise ValueError('Unsupported persistence policy')
        return self

    def threshold(self,asset):
        if asset=='MILL_01':return self.mill_probability
        if asset=='PMP_01':return self.pump_probability
        raise ValueError('Unsupported maintenance asset')


def eligible_assets(predictions,public_readings,now,policy,previous=(),already_serviced=()):
    policy.validate();at=pd.Timestamp(now);done=set(already_serviced);out={};audit=[]
    for asset in ('MILL_01','PMP_01'):
        prediction=next((p for p in predictions if p.asset_id==asset),None)
        if prediction is None:raise ValueError('Missing typed health prediction')
        if prediction.status!='model' or not prediction.usable_for_constraints or prediction.horizon_hours!=24:raise ValueError('Unusable health prediction')
        if pd.Timestamp(prediction.available_at)>at:raise ValueError('Future health prediction')
        recent=public_readings.loc[public_readings.asset_id.eq(asset)&(public_readings.timestamp+pd.Timedelta(minutes=15)<=at)].sort_values('timestamp').tail(4)
        measure='vibration_mm_s';valid=recent[measure].map(lambda x:math.isfinite(float(x)) if pd.notna(x) else False)&~recent.sensor_glitch.astype(bool)
        quality=float(valid.sum()/4)
        state=recent.state.iloc[-1] if len(recent) else None
        earlier=[r for r in previous if r['asset_id']==asset and pd.Timestamp(r['available_at'])<at]
        trailing=(earlier[-(policy.persistence_observations-1):] if policy.persistence_observations>1 else [])
        persistent=len(trailing)==policy.persistence_observations-1 and all(r['eligible_probability']>=policy.threshold(asset) and r['recent_valid_fraction']>=policy.minimum_valid_recent_fraction and r['recent_state'] not in ('repair','repair_partial','preventive_service','preventive_service_partial') for r in trailing)
        p=float(prediction.calibrated_probability)
        ready=(quality>=policy.minimum_valid_recent_fraction and state not in ('repair','repair_partial','preventive_service','preventive_service_partial') and asset not in done)
        eligible=bool(ready and p>=policy.threshold(asset) and persistent)
        out[asset]=eligible
        audit.append(dict(asset_id=asset,available_at=prediction.available_at,decision_time=at.isoformat(),model_version=prediction.model_version,
                          failure_probability=prediction.failure_probability,calibrated_probability=p,eligible_probability=p,
                          threshold=policy.threshold(asset),warning=bool(p>=policy.warning_probability),recent_valid_fraction=quality,
                          recent_state=state,persistent=persistent,already_serviced=asset in done,eligible=eligible,
                          visible_evidence=dict(vibration_mm_s=None if not len(recent) or pd.isna(recent[measure].iloc[-1]) else float(recent[measure].iloc[-1]),
                                                temperature_C=None if not len(recent) or pd.isna(recent.temp_C.iloc[-1]) else float(recent.temp_C.iloc[-1])),
                          limitation='24-hour simulated risk; conditional timing assumed uniform in the planning heuristic; no future event input'))
    return out,tuple(audit)
