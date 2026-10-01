"""Explicit feature roles and per-column legal availability; deny by default."""
from pathlib import Path
import numpy as np
import pandas as pd
import yaml

FORBIDDEN = ("latent_", "fault_label", "severity", "future_failure", "future_event", "health", "random_")


def kind(series):
    if pd.api.types.is_datetime64_any_dtype(series): return "datetime"
    if pd.api.types.is_bool_dtype(series): return "boolean"
    if pd.api.types.is_numeric_dtype(series): return "number"
    return "string"


def field(unit, at, role="observed", tasks=(), source="public observed/register data", notes=""):
    return dict(unit=unit, available_at=at, role=role, predictor_tasks=list(tasks), source=source, notes=notes)


class Contracts:
    def __init__(self, timezone):
        self.schema = dict(version="analytics_v1", timezone=timezone, tables={})

    def add(self, name, frame, keys, fields, access="public_analytics"):
        assert set(frame) == set(fields), (name, set(frame)^set(fields))
        columns = {}
        for col in frame:
            spec = dict(fields[col], type=kind(frame[col]), nullable=bool(frame[col].isna().any()), min=None, max=None)
            if col.endswith("_pf"):
                spec.update(min=0, max=1)
            columns[col] = spec
        self.schema["tables"][name] = dict(keys=keys, access=access, columns=columns)
        validate_feature_table(frame, name, self.schema)

    def availability(self):
        return dict(version="analytics_v1", timezone=self.schema["timezone"],
            timestamp_convention="Local naive timestamps in declared timezone; all windows are half-open [start,end).",
            posting="Completed meters/states/sensors at interval end; heat outcomes at heat end; production registers at shift end, plus configured posting delay.",
            forecasting="Select only task allowlisted columns with column availability <= forecast_origin. Same-slot energy/PF cannot predict same-slot energy.",
            missingness="Unknown values stay null. No backward fill, centered windows or future interpolation.",
            inventory="Latest published shift-end inventory joined backward at interval START; opening stock is a static known balance. No inferred 15-minute physical stock/output.",
            labels="Events and fault labels are evaluation-only and never enter predictor loaders.",
            tables={table: {col: {k: spec[k] for k in ("available_at", "role", "predictor_tasks", "source", "notes")}
                             for col, spec in rule["columns"].items()} for table, rule in self.schema["tables"].items()})


def validate_feature_table(frame, table, schema):
    rule = schema["tables"][table]
    if set(frame) != set(rule["columns"]): raise ValueError(f"{table}: schema columns differ")
    if frame.duplicated(rule["keys"]).any(): raise ValueError(f"{table}: duplicate key")
    for col, spec in rule["columns"].items():
        if any(token in col.lower() for token in FORBIDDEN): raise ValueError(f"Hidden/label column: {col}")
        if kind(frame[col]) != spec["type"]: raise ValueError(f"{table}.{col}: type mismatch")
        if not spec["nullable"] and frame[col].isna().any(): raise ValueError(f"{table}.{col}: unexpected null")
        if spec["available_at"] not in frame: raise ValueError(f"{col}: missing availability source")
        if kind(frame[spec["available_at"]]) != "datetime": raise ValueError(f"{col}: availability must be datetime")
        if spec["type"] == "number":
            x = frame[col].dropna()
            if not np.isfinite(x).all(): raise ValueError(f"{col}: nonfinite")
            if spec["min"] is not None and (x < spec["min"]).any(): raise ValueError(f"{col}: below range")
            if spec["max"] is not None and (x > spec["max"]).any(): raise ValueError(f"{col}: above range")
    return True


def select_predictors(frame, table, schema, task, forecast_origins=None, columns=None):
    """Strict task allowlist plus availability masking; never returns outcomes/labels."""
    validate_feature_table(frame, table, schema)
    rule = schema["tables"][table]
    if rule["access"] != "public_analytics": raise ValueError("Not a predictor table")
    allowed = [col for col, spec in rule["columns"].items() if task in spec["predictor_tasks"]]
    if not allowed: raise ValueError(f"Task not supported: {task}")
    selected = list(columns) if columns is not None else allowed
    if not set(selected) <= set(allowed): raise ValueError("Column outside predictor allowlist")
    origin_column = {"heat_energy": "start_time", "slot_load_at_start": "interval_start",
                     "slot_next_load": "interval_end", "asset_next_day_risk": "interval_end"}[task]
    origin = frame[origin_column].copy() if forecast_origins is None else pd.Series(pd.to_datetime(forecast_origins), index=frame.index)
    if isinstance(origin.dtype, pd.DatetimeTZDtype):
        origin = origin.dt.tz_convert(schema["timezone"]).dt.tz_localize(None)
    if origin.isna().any(): raise ValueError("Forecast origin cannot be missing")
    data = {col: frame[col] for col in rule["keys"]}; data["forecast_origin"] = origin
    used = []
    for col in selected:
        at = frame[rule["columns"][col]["available_at"]]
        legal = at.notna() & at.le(origin)
        data[col] = frame[col].where(legal)
        used.append(at.where(legal & frame[col].notna()))
    data["inputs_available_at"] = pd.concat(used, axis=1).max(axis=1)
    result = pd.DataFrame(data, index=frame.index)
    assert (result.inputs_available_at.isna() | result.inputs_available_at.le(origin)).all()
    return result


def load_predictors(directory, table, task, forecast_origins=None, columns=None):
    directory = Path(directory)
    schema = yaml.safe_load((directory / "feature_schema.yaml").read_text(encoding="utf-8"))
    if table not in schema["tables"]: raise ValueError("Unknown or evaluation-only table")
    return select_predictors(pd.read_parquet(directory / f"{table}.parquet"), table, schema, task, forecast_origins, columns)
