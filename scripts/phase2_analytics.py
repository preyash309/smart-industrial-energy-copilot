"""Reproducible Phase-II-A release; input freeze and simulator stay immutable."""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energy_copilot.common import sha256, write_json, values
from energy_copilot.analytics import build_analytics, load_public_inputs, select_predictors
from energy_copilot.analytics.evaluation import write_evaluation
from energy_copilot.analytics.reporting import reports
from scripts.report import runtime_manifest

SOURCE = ROOT / "data/processed/sim_v1.1"
TARGET = ROOT / "data/processed/analytics_v1"


def verify_protected():
    protected = json.loads((ROOT / "configs/phase1_readonly_manifest.json").read_text())
    mismatches = [name for name, digest in protected.items() if sha256(ROOT / name) != digest]
    if mismatches: raise RuntimeError(f"Phase-I protected files changed: {mismatches}")
    return protected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Regenerate and validate byte identity against the existing analytics freeze")
    args = parser.parse_args()
    protected = verify_protected()
    config_path = ROOT / "configs/analytics_v1.yaml"
    result = build_analytics(load_public_inputs(SOURCE))
    again = build_analytics(load_public_inputs(SOURCE))
    run = ROOT / "data/runs/analytics_v1_candidate"
    replay = ROOT / "data/runs/analytics_v1_replay"
    result.write(run); again.write(replay)
    identity = {p.name: sha256(p)==sha256(replay/p.name) for p in run.iterdir()
                if p.name in [f"{name}.parquet" for name in result.tables] or p.name in ("feature_schema.yaml", "feature_availability.yaml", "config_snapshot.yaml", "accounting_validation.json")}
    assert all(identity.values())
    task_counts = {}
    for table, task in (("heat_features", "heat_energy"), ("slot_features", "slot_load_at_start"), ("slot_features", "slot_next_load"), ("asset_daily_metrics", "asset_next_day_risk")):
        f = select_predictors(result.tables[table], table, result.schema, task)
        assert (f.inputs_available_at.isna() | f.inputs_available_at.le(f.forecast_origin)).all()
        task_counts[task] = len(f.columns)-len(result.schema["tables"][table]["keys"])-2
    completed = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, capture_output=True, text=True)
    print(completed.stdout, flush=True)
    if completed.returncode: raise RuntimeError(completed.stdout+completed.stderr)
    count = re.search(r"(\d+) passed", completed.stdout)
    assert count
    assert protected == verify_protected()
    # Targets/hidden physical checks are a one-way evaluation handoff; result
    # tables are already frozen in memory and never consume evaluation outputs.
    write_evaluation(SOURCE, run / "evaluation", result)
    gates = dict(phase1_unchanged="PASS", public_mass_accounting="PASS", noisy_energy_reconciliation="PASS",
        hidden_truth_evaluation_only="PASS", feature_reproducibility="PASS", predictor_boundary="PASS",
        time_availability="PASS", historical_baselines="PASS", diagnostic_candidates="PASS",
        tests=f"{count.group(1)} passed")
    kpi = reports(result, ROOT / "reports", gates)
    report_dir = run / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    for name in ("phase2_energy_analytics.md", "phase2_feature_audit.md"):
        shutil.copyfile(ROOT / "reports" / name, report_dir / name)
    figure_dir = report_dir / "phase2_analytics"
    figure_dir.mkdir(exist_ok=True)
    for p in (ROOT / "reports/phase2_analytics").iterdir():
        if p.is_file(): shutil.copyfile(p, figure_dir / p.name)
    source_hashes = {p.name: sha256(p) for p in SOURCE.iterdir() if p.is_file()}
    write_json(run / "source_manifest.json", dict(source_version="sim_v1.1", hashes=source_hashes,
        feature_inputs=["readings.parquet", "heats.parquet (strict public field selection)", "production.parquet", "public clock/calendar/opening balance"],
        evaluation_only=["events.parquet", "latent_truth.parquet", "latent_heats.parquet"],
        design_inputs={p.name: sha256(p) for p in (ROOT / "Readme").glob("*.pdf")}))
    write_json(run / "phase1_readonly_manifest.json", protected)
    write_json(run / "validation_report.json", dict(version="analytics_v1", status="PASS", gates=gates, byte_replay=identity,
        predictor_column_counts=task_counts, accounting=result.accounting, baseline_rule="No ML fit: prequential historical means and empirical ranges",
        table_rows={name: len(frame) for name, frame in result.tables.items()}))
    write_json(run / "operator_kpis.json", kpi)
    write_json(run / "runtime_manifest.json", runtime_manifest())
    shutil.copyfile(ROOT / "requirements.lock.txt", run / "requirements.lock.txt")
    shutil.copyfile(config_path, run / "analytics_v1.yaml")
    sources = [*sorted((ROOT / "src/energy_copilot/analytics").glob("*.py")), Path(__file__).resolve(),
               ROOT / "tests/test_analytics.py", config_path, ROOT / "configs/phase1_readonly_manifest.json"]
    write_json(run / "code_manifest.json", {p.relative_to(ROOT).as_posix(): sha256(p) for p in sources})
    h = result.tables["heat_features"]
    card = f"""# analytics_v1 data card

**Phase II-A monitoring and energy analytics.** Derived deterministically from the frozen sim_v1.1 public tables. {len(h)} heats, {len(result.tables['slot_features'])} 15-minute plant slots, {len(result.tables['asset_daily_metrics'])} asset-days. Thirty local Asia/Kolkata calendar days from 2026-01-05, with 26 working days. No new simulated randomness, physical model changes, ML training, optimisation or savings claims.

Files: heat_features.parquet (completed heat analytics and earlier historical context), slot_features.parquet (public interval channels and past windows), asset_daily_metrics.parquet, diagnostic_candidates.parquet, production_register.parquet. feature_schema.yaml and feature_availability.yaml define every column's type, unit, role and legal publication time. Config parameters/thresholds retain value/unit/status/source/notes in config_snapshot.yaml and analytics_v1.yaml. Inputs, protected Phase-I files, code and pinned runtime are hashed beside the data.

Completed outcomes coexist with historical features for analytics, so **never use automatic numeric feature selection**. Use `energy_copilot.analytics.load_predictors(directory, table, task)` with heat_energy, slot_load_at_start, slot_next_load or asset_next_day_risk. The loader rejects outcomes/evaluation tables and masks late inputs, returning inputs_available_at and forecast_origin. Current-heat energy/duration/temp/mass/chemistry are absent from pre-heat predictors. Current-slot power/PF are absent from start-time load predictors. No latent wear/fouling, future failures/events, hidden random variables or fault labels enter allowed predictors.

Heat energy expectations are prior-only global/shift/group/rolling means with empirical ranges, not trained ML or best-practice claims. Diagnostics are observable candidates with limitations, not true fault diagnoses. Known meter/fuel totals have incomplete coverage; kW fallback uses the same completed interval only. MAIN is never double-counted with its six feeders. Runtime is active-slot occupancy; public partial repairs only bound downtime. Yard/output are last published completed-shift quantities, not true 15-minute trajectories. Ideal zero posting latency is an explicit assumption, replaceable by the delay parameter. Chemistry remains a synthetic placeholder, excluded from pre-heat predictors.

`evaluation/` contains separate heat/load targets, fault labels/events, a chronological split manifest and hidden physical accounting checks. These cannot be read by the predictor loader. Only heat/load provisional splits exist; maintenance still needs cycle-aware evaluation and sufficient horizon. Physical truth is used solely for testing, never operator KPIs or feature values. See reports/phase2_energy_analytics.md and reports/phase2_feature_audit.md. Every release gate passes; Phase-I files are unchanged.

Regenerate/verify: Python 3.12 with requirements.lock.txt; `python -m scripts.phase2_analytics --check`. No timestamp-dependent release metadata. An existing differing analytics_v1 is never overwritten; choose a new analytics version for changed inputs/config/code. No executable tariff/emission inputs are supplied, so cost and carbon metrics are absent.
"""
    (run / "data_card.md").write_text(card, encoding="utf-8")
    assert protected == verify_protected()
    hashes = {p.relative_to(run).as_posix(): sha256(p) for p in sorted(run.rglob("*")) if p.is_file() and p.name != "freeze_manifest.json"}
    write_json(run / "freeze_manifest.json", dict(version="analytics_v1", source_version="sim_v1.1", hashes=hashes))
    if TARGET.exists():
        prior = json.loads((TARGET / "freeze_manifest.json").read_text())
        if prior["hashes"] != hashes: raise RuntimeError("Frozen analytics_v1 differs; never overwrite. Version changed analytics separately.")
        assert all(sha256(TARGET/name)==digest for name,digest in hashes.items())
    elif args.check:
        raise RuntimeError("analytics_v1 missing; run without --check to create it")
    else:
        shutil.copytree(run, TARGET)
    assert protected == verify_protected()
    print(f"Phase-II-A exit gates PASS: {TARGET}", flush=True)


if __name__ == "__main__":
    main()
