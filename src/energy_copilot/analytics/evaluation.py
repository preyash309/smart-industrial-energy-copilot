"""Evaluation-only labels/truth. This module must never feed feature construction."""
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
from energy_copilot.common import values, write_json


def write_evaluation(source, destination, analytics):
    source = Path(source); destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    # Deliberately separate entry point, called AFTER features have been built.
    public_heats = pd.read_parquet(source / "heats.parquet")
    labels = public_heats[["heat_id", "fault_label"]].copy()
    labels.to_parquet(destination / "heat_labels.parquet", index=False)
    pd.read_parquet(source / "events.parquet").to_parquet(destination / "events.parquet", index=False)
    h = analytics.tables["heat_features"]
    h[["heat_id", "start_time", "end_time", "available_at", "kWh", "SEC_kWh_per_t"]].to_parquet(destination / "heat_targets.parquet", index=False)
    s = analytics.tables["slot_features"]
    targets = pd.DataFrame(dict(interval_start=s.interval_start, forecast_origin=s.interval_end,
        target_interval_start=s.interval_start.shift(-1), target_interval_end=s.interval_end.shift(-1),
        target_available_at=s.available_at.shift(-1), next_MAIN_kWh=s.MAIN_energy_best_kWh.shift(-1)))
    targets.to_parquet(destination / "slot_targets.parquet", index=False)
    days = sorted(s.interval_start.dt.normalize().unique())
    fractions = values(analytics.config)["parameters"]["time_split_fractions"]
    first = int(len(days)*fractions[0]); second = int(len(days)*(fractions[0]+fractions[1]))
    validation_start = pd.Timestamp(days[first]); test_start = pd.Timestamp(days[second])
    rows = []
    for table, frame, key, origin in (("heat_energy", h, "heat_id", "start_time"), ("slot_next_load", targets, "interval_start", "forecast_origin")):
        split = np.select([frame[origin].lt(validation_start), frame[origin].lt(test_start)], ["train", "validation"], default="test")
        for i, row in frame.iterrows():
            end = row.end_time if table == "heat_energy" else row.target_interval_end
            # Purge outcomes crossing partition boundaries and the missing last target.
            boundary = validation_start if split[i] == "train" else test_start if split[i] == "validation" else s.interval_end.iloc[-1]
            purged = pd.isna(end) or end > boundary
            rows.append(dict(task=table, row_id=str(row[key]), forecast_origin=row[origin], split=split[i], purged=purged))
    pd.DataFrame(rows).to_parquet(destination / "time_split_manifest.parquet", index=False)
    write_json(destination / "access_policy.json", dict(access="evaluation_only", predictor_access=False,
        label_policy="Injected annotations are evaluation targets, not observable diagnoses; never merge into predictor columns.",
        splits=dict(validation_start=str(validation_start), test_start=str(test_start), basis="Chronological calendar-day cutoffs; purge crossing outcome windows.",
                    maintenance="No maintenance labels/training here. Cycle-aware grouping and adequate horizon remain required in the next stage.")))
    # Independent frozen truth accounting is ONLY evaluation; no values are passed
    # back to features, baselines, diagnostics or operator KPI reports.
    from scripts.independent_accounting import independent
    cfg = yaml.safe_load((source / "config_snapshot.yaml").read_text())
    tables = {name: pd.read_parquet(source / f"{name}.parquet") for name in ("latent_truth", "latent_heats", "production", "events")}
    metrics, checks, residuals = independent(tables, cfg)
    assert metrics["violations"] == 0
    write_json(destination / "physical_validation.json", dict(access="evaluation_only", status="PASS", metrics=metrics, checks=checks, residuals=residuals))
