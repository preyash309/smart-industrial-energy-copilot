"""Strict, origin-aware predictor schemas. Targets and provenance stay separate."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

FORBIDDEN = ("latent", "fouling", "severity", "future", "failure", "fault", "noise", "oracle", "random", "source_row", "UDI", "Product ID", "TWF", "HDF", "PWF", "OSF", "RNF")
OUTCOMES = {"target", "actual", "actual_sec", "sec_kwh_per_t", "kwh", "kwh_per_t", "duration_min",
            "heat_duration_minutes", "tap_temp_c", "chem_ok", "charge_t", "liquid_t", "billet_t", "end_time"}


def check_names(names):
    for name in names:
        if name.lower() in OUTCOMES or any(token.lower() in name.lower() for token in FORBIDDEN):
            raise ValueError(f"Forbidden predictor: {name}")


def validate_inputs(frame, features, types=None):
    check_names(features)
    if list(frame.columns) != list(features):
        raise ValueError("Feature schema mismatch (order, missing or extra columns)")
    if frame.select_dtypes("number").replace([np.inf, -np.inf], np.nan).isna().sum().sum() != frame.select_dtypes("number").isna().sum().sum():
        raise ValueError("Infinite predictor")
    if types:
        for col in features:
            nonmissing=frame[col].dropna()
            if types[col]=="number" and not all(isinstance(v,(int,float,np.number)) and not isinstance(v,(bool,np.bool_)) for v in nonmissing):
                raise ValueError(f"Feature type mismatch: {col}")
            if types[col]=="string" and not all(isinstance(v,str) for v in nonmissing):
                raise ValueError(f"Feature type mismatch: {col}")


def assert_available(meta):
    if meta.forecast_origin.isna().any() or meta.inputs_available_at.isna().any():
        raise ValueError("Missing forecast origin/publication bound")
    if (meta.inputs_available_at > meta.forecast_origin).any():
        raise ValueError("Information published after forecast origin")
    if "target_start" in meta and (meta.target_start < meta.forecast_origin).any():
        raise ValueError("Target precedes forecast origin")


@dataclass
class Dataset:
    X: pd.DataFrame
    meta: pd.DataFrame
    y: pd.Series

    def audit(self):
        validate_inputs(self.X, list(self.X))
        if "snapshot_available" in self.meta:
            if not self.meta.snapshot_available.all():raise ValueError("AI4I snapshot availability violation")
        else:
            assert_available(self.meta)
        if len(self.X) != len(self.meta) or len(self.X) != len(self.y):
            raise ValueError("Feature/target join mismatch")
        if not np.isfinite(self.y).all():
            raise ValueError("Invalid target")
        if not self.meta.row_id.is_unique:
            raise ValueError("Duplicate target join key")
        if set(self.meta.split) != {"train", "validation", "calibration", "test"}:
            raise ValueError("Four independent fitting/selection/calibration/test partitions required")
        # All variants of a simulated seed, including its failure episodes, stay together.
        if "seed" in self.meta and self.meta.groupby("seed").split.nunique().max() != 1:
            raise ValueError("Seed crosses partitions")
        return {"status": "PASS", "features": list(self.X), "rows": len(self.y),
                "rows_by_split": self.meta.groupby("split").size().to_dict(),
                "null_predictors": self.X.isna().sum().to_dict()}

    def write(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        self.X.to_parquet(directory / "features.parquet", index=False)
        self.meta.to_parquet(directory / "index.parquet", index=False)
        pd.DataFrame({"row_id": self.meta.row_id, "target": self.y}).to_parquet(directory / "targets.parquet", index=False)

    @classmethod
    def read(cls, directory):
        X = pd.read_parquet(directory / "features.parquet")
        meta = pd.read_parquet(directory / "index.parquet")
        targets = pd.read_parquet(directory / "targets.parquet")
        if not meta.row_id.equals(targets.row_id):
            raise ValueError("Target join/order changed")
        return cls(X, meta, targets.target)
