"""Model-independent, deterministic optimizer-facing contracts; no decisions here."""
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import joblib
import numpy as np
import pandas as pd
from .contracts import validate_inputs
from .uncertainty import prediction_quantiles


@dataclass(frozen=True)
class HeatPrediction:
    heat_id: str
    practice_mode: str
    energy_p10_kWh: float
    energy_p50_kWh: float
    energy_p90_kWh: float
    SEC_p50: float
    duration_p10_min: float
    duration_p50_min: float
    duration_p90_min: float
    available_at: str
    model_version: str
    status: str
    usable_for_constraints: bool


@dataclass(frozen=True)
class LoadPrediction:
    interval_start: str
    interval_end: str
    available_at: str
    horizon_slot: int
    load_p10_kW: float
    load_p50_kW: float
    load_p90_kW: float
    components: tuple
    model_version: str
    status: str
    usable_for_constraints: bool


@dataclass(frozen=True)
class HealthPrediction:
    asset_id: str
    horizon_hours: float
    failure_probability: float
    calibrated_probability: float | None
    available_at: str
    model_version: str
    status: str
    usable_for_constraints: bool


class PredictionService:
    """Caller supplies values AND per-field publication times; deny by default.

    Heat calendar may represent a proposed start; all observed history must be
    frozen at decision origin, including when that candidate starts tomorrow.
    Forecast context is an explicit origin snapshot, never a realized future row.
    Missing artifacts use documented training-only fallbacks and disable use in
    constraints. Missing metadata fails closed, since there is no defensible bound.
    """
    def __init__(self,directory):
        self.directory=Path(directory)
        self.contract=json.loads((self.directory/"prediction_contract.json").read_text())

    def _load(self,task):
        d=self.directory/task
        metadata=json.loads((d/"metadata.json").read_text())
        path=d/"production.joblib"
        return (joblib.load(path) if path.exists() else None),metadata

    @staticmethod
    def _inputs(context,metadata,origin):
        values=context["features"];ats=context["available_at"]
        features=metadata["features"]
        if set(values)!=set(features) or set(ats)!=set(features):
            raise ValueError("Feature schema mismatch")
        origin=pd.Timestamp(origin)
        if pd.isna(origin) or origin.tz is not None:raise ValueError("Use nonmissing declared local naive forecast origin")
        for name in features:
            at=pd.Timestamp(ats[name])
            if pd.isna(at) or at.tz is not None or at>origin:raise ValueError(f"Late/unavailable input {name}")
        X=pd.DataFrame([{k:values[k] for k in features}])
        validate_inputs(X,features,metadata["feature_types"])
        return X

    def _regress(self,task,context,origin,horizon=None):
        bundle,metadata=self._load(task);X=self._inputs(context,metadata,origin)
        if bundle is None:
            base=np.array([metadata["fallback"]["central"]]);cal=metadata["fallback"]["calibration"]
        else:
            base=np.maximum(0,bundle["model"].predict(X));cal=bundle["by_horizon"].get(str(horizon),bundle["calibration"])
        q=prediction_quantiles(base,cal)
        return {k:float(v[0]) for k,v in q.items()},bundle is not None

    def predict_heat(self,heat_context,practice_mode=None):
        mode=practice_mode or "normal"
        if mode not in self.contract["practice_modes"]:raise ValueError("Unsupported/unvalidated practice mode")
        origin=heat_context["forecast_origin"]
        if pd.Timestamp(heat_context["candidate_start"])<pd.Timestamp(origin):raise ValueError("Candidate in past")
        features=heat_context["features"]
        if features["candidate_liquid_t"]!=self.contract["candidate_liquid_t"]:
            raise ValueError("No batch-size extrapolation: only configured 10-t crucible qualified")
        if features["practice_loss_kWh_t"]!=self.contract["practice_modes"][mode]["practice_loss_kWh_t"]:
            raise ValueError("Practice feature/decision mismatch")
        candidate=pd.Timestamp(heat_context["candidate_start"])
        if (features["hour"],features["weekday"],features["shift"])!=(candidate.hour,candidate.dayofweek,candidate.hour//8):
            raise ValueError("Candidate calendar/context mismatch")
        e,ok_e=self._regress("heat_energy",heat_context,origin)
        d,ok_d=self._regress("heat_duration",heat_context,origin)
        ok=ok_e and ok_d
        return HeatPrediction(str(heat_context["heat_id"]),mode,e["p10"],e["p50"],e["p90"],e["p50"]/features["candidate_liquid_t"],
                              d["p10"],d["p50"],d["p90"],pd.Timestamp(origin).isoformat(),self.contract["version"],"model" if ok else "fallback",ok)

    def predict_background_load(self,forecast_origin,horizon,context):
        if not isinstance(horizon,int) or not 1<=horizon<=self.contract["load_max_horizon_slots"]:raise ValueError("Unsupported load horizon")
        origin=pd.Timestamp(forecast_origin)
        if origin!=origin.normalize():raise ValueError("Only daily midnight origins validated")
        result=[]
        for h in range(1,horizon+1):
            target=origin+pd.Timedelta(minutes=15*(h-1));minute=target.hour*60+target.minute
            c=dict(features=dict(context["features"]),available_at=dict(context["available_at"]))
            known=dict(horizon_slot=h,target_hour=target.hour,target_weekday=target.dayofweek,target_shift=target.hour//8,
                       target_sin=float(np.sin(2*np.pi*minute/1440)),target_cos=float(np.cos(2*np.pi*minute/1440)))
            # The seasonal observation differs by horizon; caller supplies the known prior-day profile.
            profile=context["seasonal_profile"]
            if len(profile)!=self.contract["load_max_horizon_slots"]:raise ValueError("Incomplete prior-day profile")
            c["features"].update(known,seasonal_naive=profile[h-1]["value"])
            c["available_at"].update({k:origin for k in known});c["available_at"]["seasonal_naive"]=profile[h-1]["available_at"]
            q,ok=self._regress("load",c,origin,h)
            result.append(LoadPrediction(target.isoformat(),(target+pd.Timedelta(minutes=15)).isoformat(),origin.isoformat(),h,
                         q["p10"],q["p50"],q["p90"],("AUX",),self.contract["version"],"model" if ok else "fallback",ok))
        return result

    def predict_health(self,asset_state,horizon):
        asset=asset_state["asset_id"]
        if asset not in self.contract["health_assets"] or horizon!=self.contract["health_horizon_hours"]:raise ValueError("Unsupported asset/horizon")
        bundle,metadata=self._load(f"health/{asset}");origin=asset_state["forecast_origin"]
        X=self._inputs(asset_state,metadata,origin)
        if bundle is None:p=metadata["fallback"]["prevalence"];calibrated=None
        else:
            from .models import logit
            p=float(bundle["model"].predict_proba(X)[0,1]);calibrated=float(bundle["calibrator"].predict_proba(logit(np.array([p])))[0,1])
        return HealthPrediction(asset,horizon,p,calibrated,pd.Timestamp(origin).isoformat(),self.contract["version"],
                                "model" if bundle else "fallback_uncalibrated",bundle is not None)
