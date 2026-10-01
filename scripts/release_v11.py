"""Gate and freeze the B01-only successor; never write to sim_v1.0."""
from __future__ import annotations
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from energy_copilot.common import load_config, sha256, write_json, canonical_hash
from energy_copilot.schema import load_reading_features, validate_table
from energy_copilot.sim import simulate
from scripts.independent_accounting import independent
from scripts.rhf_boundary import temperature_boundary, assert_b01_resolved
from scripts.report import runtime_manifest

VERSION = "sim_v1.1"
PRIOR = ROOT / "data/processed/sim_v1.0"
EVIDENCE = ROOT / "reports/rhf_boundary_v1.1"
TABLES = ("readings", "heats", "production", "events", "latent_truth", "latent_heats")


def prior_hashes():
    manifest = json.loads((PRIOR / "freeze_manifest.json").read_text())
    assert all(sha256(PRIOR / name) == digest for name, digest in manifest["hashes"].items())
    files = [*PRIOR.rglob("*"), ROOT / "reports/phase1_independent_audit.md",
             *(ROOT / "reports/phase1_audit").rglob("*")]
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in files if p.is_file()}


def boundary_loader_checks(readings, directory):
    with patch("energy_copilot.schema.pd.read_parquet", return_value=readings):
        features = load_reading_features(directory)
    schema = yaml.safe_load((ROOT / "configs/schema.yaml").read_text())
    assert not set(schema["forbidden_features"]) & set(features)
    assert not any(col.startswith("latent_") for col in features)
    rejected = []
    for field in ("latent_fouling", "latent_wear", "true_fault_severity", "health",
                  "future_failure_time", "future_exogenous_event", "fault_label"):
        injected = readings.assign(**{field: 0})
        with patch("energy_copilot.schema.pd.read_parquet", return_value=injected):
            try:
                load_reading_features(directory)
            except ValueError:
                rejected.append(field)
            else:
                raise AssertionError(f"Hidden column accepted: {field}")
    return dict(feature_columns=list(features), hidden_column_injections_rejected=rejected,
                scope="Observed allowlist only; events/heats labels are targets; latent files internal. W01 as-of warning remains.")


def main():
    before = prior_hashes()
    config = load_config(); old_config = load_config(PRIOR / "config_snapshot.yaml")
    adjusted = dict(old_config, version=config["version"])
    assert adjusted == config, "B01 release must not change parameters or assumptions"
    assert config["version"] == "plant_v1.1"
    runtime = runtime_manifest()
    pinned = json.loads((PRIOR / "runtime_manifest.json").read_text())["dependencies"]
    assert runtime["dependencies"] == pinned
    completed = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT,
                               text=True, capture_output=True)
    print(completed.stdout, flush=True)
    if completed.returncode:
        raise RuntimeError(completed.stdout + completed.stderr)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    write_json(EVIDENCE / "tests.json", dict(command="python -m pytest -q", status="PASS",
                                            output=completed.stdout.strip()))
    result = simulate(config, seed=42, days=30)
    replay = simulate(config, seed=42, days=30)
    tables = {name: getattr(result, name) for name in TABLES}
    old = {name: pd.read_parquet(PRIOR / f"{name}.parquet") for name in TABLES}
    identical = {}
    for name in TABLES:
        first = getattr(result, name); again = getattr(replay, name)
        pd.testing.assert_frame_equal(first, again, check_exact=True)
        identical[name] = hashlib.sha256(first.to_parquet(index=False)).hexdigest() == hashlib.sha256(again.to_parquet(index=False)).hexdigest()
        assert identical[name]
        validate_table(first, name)
        if name != "readings":
            pd.testing.assert_frame_equal(first, old[name], check_exact=True)
    rhf = old["readings"].asset_id.eq("RHF_01")
    pd.testing.assert_frame_equal(result.readings.loc[~rhf], old["readings"].loc[~rhf], check_exact=True)
    pd.testing.assert_frame_equal(result.readings.drop(columns=["temp_C", "flue_temp_C"]),
                                  old["readings"].drop(columns=["temp_C", "flue_temp_C"]), check_exact=True)
    assert result.summary == json.loads((PRIOR / "simulation_summary.json").read_text())
    assert result.scenario_manifest == replay.scenario_manifest
    assert result.scenario_manifest["config_sha256"] == canonical_hash(config)
    previous = temperature_boundary(old["readings"], old["latent_truth"], old_config)
    current = temperature_boundary(result.readings, result.latent_truth, config)
    assert previous["max_error"] < 1e-12
    assert_b01_resolved(current, config["observations"]["sensor_noise"]["value"])
    boundary = boundary_loader_checks(result.readings, EVIDENCE)
    write_json(EVIDENCE / "boundary_checks.json", dict(status="PASS", B01="RESOLVED",
        old=previous, new=current, loader=boundary, noise_scale=config["observations"]["sensor_noise"]["value"],
        streams=["rhf_zone_temperature", "rhf_flue_temperature"]))
    metrics, checks, residuals = independent(tables, config)
    assert metrics["violations"] == 0
    write_json(EVIDENCE / "independent_checks.json", dict(metrics=metrics, checks=checks, residuals=residuals))
    historical = pd.read_csv(ROOT / "reports/phase1_audit/seed_results.csv").set_index("seed")
    rows = []; seed_checks = []
    for seed in range(1, 31):
        seeded = simulate(config, seed=seed, days=30)
        m, check, residual = independent({n: getattr(seeded, n) for n in TABLES}, config)
        assert m["violations"] == 0, (seed, check)
        deltas = {k: abs(float(v)-float(historical.loc[seed, k])) for k, v in m.items()
                  if isinstance(v, (int, float, np.number)) and k in historical}
        assert all(delta <= 1e-8 for delta in deltas.values()), (seed, deltas)
        b = temperature_boundary(seeded.readings, seeded.latent_truth, config)
        assert_b01_resolved(b, config["observations"]["sensor_noise"]["value"])
        rows.append(dict(seed=seed, **m, recovery_median_error=b["median_error"],
                         recovery_max_error=b["max_error"], flue_fouling_correlation=b["observed_flue_fouling_correlation"],
                         maximum_historical_physical_KPI_delta=max(deltas.values())))
        seed_checks.append(dict(seed=seed, checks=check, residuals=residual, boundary=b, historical_deltas=deltas))
        print(f"seed {seed}: independent constraints PASS, B01 PASS, physical KPIs unchanged", flush=True)
    seeds = pd.DataFrame(rows)
    assert seeds.if_sec.nunique() > 1 and seeds.plant_MWh.nunique() > 1
    seeds.to_csv(EVIDENCE / "seed_results.csv", index=False)
    write_json(EVIDENCE / "seed_checks.json", seed_checks)
    replay_evidence = dict(parquet_byte_identical=identical, scenario_manifest_identical=True,
        physical_summary_identical_to_v10=True, physical_and_label_tables_identical_to_v10=list(TABLES[1:]),
        different_seeds_vary=True, additional_seeds=30, prior_evidence_unchanged=before == prior_hashes())
    assert replay_evidence["prior_evidence_unchanged"]
    write_json(EVIDENCE / "replay.json", replay_evidence)
    write_json(EVIDENCE / "prior_evidence_hashes.json", before)
    distributions = {col: dict(min=float(seeds[col].min()), mean=float(seeds[col].mean()), max=float(seeds[col].max()))
                     for col in ("if_sec", "plant_MWh", "reported_peak_kVA", "coal_tpd", "bar_tpd", "inventory_min", "inventory_max",
                                 "recovery_median_error", "recovery_max_error", "flue_fouling_correlation")}
    write_json(EVIDENCE / "seed_distributions.json", distributions)
    write_json(EVIDENCE / "validation_report.json", dict(version=VERSION, status="PASS", resolved_blocker="B01",
        baseline_summary=result.summary, independent_violations=metrics["violations"],
        independent_checks=checks, boundary_old=previous, boundary_new=current,
        replay=replay_evidence, additional_seed_distributions=distributions,
        inherited_warnings="W01-W09 unchanged; see the immutable V1.0 independent audit"))
    write_reports(result, previous, current, metrics, checks, distributions)
    candidate = ROOT / "data/runs/sim_v1.1_candidate"
    candidate.mkdir(parents=True, exist_ok=True)
    result.write(candidate)
    assert load_config(candidate / "config_snapshot.yaml") == config
    copies = [(ROOT / "configs/schema.yaml", "schema.yaml"),
              (ROOT / "configs/calibration_v1.yaml", "calibration_v1.yaml"),
              (ROOT / "requirements.lock.txt", "requirements.lock.txt"),
              (ROOT / "data/raw/source_hashes.json", "source_hashes.json"),
              (PRIOR / "assumption_register.md", "assumption_register.md"),
              (PRIOR / "temporal_validation.json", "temporal_validation.json"),
              (EVIDENCE / "validation_report.md", "validation_report.md"),
              (EVIDENCE / "data_card.md", "data_card.md"),
              (EVIDENCE / "boundary_audit.md", "boundary_audit.md"),
              (ROOT / "CHANGELOG.md", "CHANGELOG.md")]
    copies += [(p, p.name) for p in EVIDENCE.glob("*.json")]
    copies += [(EVIDENCE / "seed_results.csv", "seed_results.csv")]
    for path, name in copies:
        shutil.copyfile(path, candidate / name)
    write_json(candidate / "seed.json", dict(seed=42))
    write_json(candidate / "runtime_manifest.json", runtime)
    sources = [*sorted((ROOT / "src").rglob("*.py")), *sorted((ROOT / "scripts").rglob("*.py")),
               *sorted((ROOT / "tests").rglob("*.py")), ROOT / "pyproject.toml", ROOT / "requirements.txt"]
    write_json(candidate / "code_manifest.json", {p.relative_to(ROOT).as_posix(): sha256(p) for p in sources})
    hashes = {p.name: sha256(p) for p in sorted(candidate.iterdir()) if p.is_file() and p.name != "freeze_manifest.json"}
    write_json(candidate / "freeze_manifest.json", dict(version=VERSION, predecessor="sim_v1.0", resolved_blocker="B01", hashes=hashes))
    target = ROOT / "data/processed" / VERSION
    assert before == prior_hashes(), "Historical V1.0 evidence changed"
    if target.exists():
        if hashes != json.loads((target / "freeze_manifest.json").read_text())["hashes"]:
            raise RuntimeError("Frozen sim_v1.1 differs; never overwrite it")
        assert all(sha256(target / name) == digest for name, digest in hashes.items())
    else:
        shutil.copytree(candidate, target)
    assert before == prior_hashes()
    print(f"Reviewed successor frozen: {target}", flush=True)


def write_reports(result, old, new, metrics, checks, distributions):
    table = "\n".join(f"| {key} | {value['min']:.6g} | {value['mean']:.6g} | {value['max']:.6g} |"
                      for key, value in distributions.items())
    boundary = f"""# RHF observation boundary audit — sim_v1.1

**PASS — B01 resolved.** This is a narrowly scoped successor to the historical `reports/phase1_independent_audit.md`, whose V1.0 verdict remains unchanged.

Root cause: zone and flue measurements multiplied their true values by the identical `(1 + sensor_noise * z)` sample. The ratio cancelled that factor. Hiding `latent_fouling` by column name did not prevent exact severity recovery.

V1.1 derives two stable named `numpy.random.Generator` streams from the simulation seed through the existing SHA256-name/SeedSequence factory: `rhf_zone_temperature` and `rhf_flue_temperature`. Both tapes are generated before decisions. True zone/flue values are computed first and only observed RHF temperatures use those tapes. Existing configured relative sensor SD remains 0.005 (0.5%); no added noise, physical model change, new faults or calibration change. Existing missing/glitch processes are preserved. Independent noise prevents sample-wise cancellation while retaining statistical information about fouling.

Attack: `{new['formula']}`. Select active RHF rows with finite flue and zone within nominal +/-100 C, reproducing the audit filter without selecting on reconstruction error.

| Metric | V1.0 | V1.1 |
|---|---:|---:|
| Rows | {old['rows']} | {new['rows']} |
| Median absolute severity error | {old['median_error']:.12g} | {new['median_error']:.12g} |
| Maximum absolute severity error | {old['max_error']:.12g} | {new['max_error']:.12g} |
| Rows with error <1e-10 | {old['exact_rows']} | {new['exact_rows']} |
| Zone/flue residual correlation | {old['residual_correlation']:.6f} | {new['residual_correlation']:.6f} |
| Observed flue/fouling correlation | {old['observed_flue_fouling_correlation']:.6f} | {new['observed_flue_fouling_correlation']:.6f} |

Measured relative zone/flue residual SD: {new['zone_relative_noise_sd']:.6f} / {new['flue_relative_noise_sd']:.6f}, consistent with the existing 0.005 scale. No new sensor-specific scale is introduced. Tests explicitly reject median error <=1e-6 or maximum error <=1e-5, require zero exact rows, independent residuals and flue/fouling correlation >0.3. The legacy artifact fails these gates, demonstrating that the regression detects the original blocker.

**PASS — public/hidden boundary.** The strict feature loader retains permitted observed columns and rejects injected latent fouling/wear, health, severity, future failure/event and fault-label columns. No future exogenous noise tape is included in public tables. Hidden tables remain internal diagnostics; labels/events are targets, not features. This tests the named algebraic attack, not a claim that noisy physical observations have no predictive information. As required, fouling still raises true flue temperature and fuel use.

**WARNING — inherited limitations unchanged.** W01-W09 from the independent V1.0 audit remain applicable, including interval-end availability, reduced RHF thermal/chemistry physics, accelerated wear, baseline output and UCI ACF discrepancies. Files are semantically separated by the loader, not protected by filesystem ACLs. No Phase-II work is included.

Evidence: `boundary_checks.json`, `seed_checks.json`, `replay.json`, `tests.json`; reproducible command: `python -m scripts.release_v11`. Configuration/hash version and scenario identity change to record the new observation model; physical exogenous sequences and accounting do not.
"""
    validation = f"""# sim_v1.1 validation report

**PASS.** All 33 tests pass (28 existing Phase-I tests plus 5 B01 regression tests). See `tests.json` for the actual command/output. Validation completes before the successor freeze. No physical/configuration numeric parameter changed; only plant/package version metadata and RHF observation processes changed.

**PASS — exact baseline preservation.** Seed 42, 30 days, 26 working days, 338 heats. V1.0 and V1.1 latent truth, latent heat registers, production, events and public heats are exactly equal. All unrelated observed columns and all non-RHF readings are exactly equal. Every physical summary field is exactly equal. IF SEC {metrics['if_sec']:.9f} kWh/t; electricity {metrics['plant_MWh']:.9f} MWh/working day; coal {metrics['coal_tpd']:.9f} t/working day; bars {metrics['bar_tpd']:.6f} t/working day. Peak conservative demand {metrics['reported_peak_kVA']:.6f} kVA; independent actual peak {metrics['exact_piecewise_peak_kVA']:.6f} kVA. Yard {metrics['inventory_min']:.6f}–{metrics['inventory_max']:.6f} t. Delta for each physical KPI: zero.

**PASS — independent accounting.** Standalone ledger arithmetic adapted from the original adversarial audit imports no simulator calculation/validation functions. All {len(checks)} independent checks pass, including mass/energy/fuel, 15-minute demand, yard bounds, cooling interlock, yields/throughput and independent subslot demand/cooling reconstruction. Residuals and violation counts are in `independent_checks.json`.

**PASS — replay and fault causality.** All six Parquets are byte-identical across two contemporary seed-42 runs and scenario manifests are equal. Changed flue-stream naming cannot shift zone noise, physical state, fault labels or unrelated observations (dedicated regression). Zero observation noise leaves physics unchanged (existing regression). Physical fault effects are covered by the existing mechanism tests and identical physical/fault tables. Seeds 1–30 additionally pass independent constraints and B01 gates. Their physical metrics match the pre-patch adversarial seed results within CSV round-trip precision, with no recalibration and no rejected/censored seeds; IF SEC and plant electricity still vary between seeds.

| Additional-seed metric | Minimum | Mean | Maximum |
|---|---:|---:|---:|
{table}

**PASS — immutable predecessor.** Every file in `sim_v1.0`, the original audit and its evidence folder is verified unchanged before and after release. Their hashes are in `prior_evidence_hashes.json`. The exact successor config, schema, calibration, seed, runtime, source hashes, dependency lock and current source/test code hashes are snapshotted in V1.1.

**WARNING — previous warnings remain.** Baseline energy acceptance is a run mean, not an every-day envelope. Existing UCI temporal diagnostics are carried over because power is exactly unchanged; no fitting or recomputation can be attributed to this observation-only patch. Refer to the immutable original independent audit for W01-W09. The previously frozen data card's blanket independent-noise statement was not true for RHF; use the V1.1 boundary audit for corrected evidence. No optimisation, models, savings claims or unrelated warning changes.
"""
    card = f"""# sim_v1.1 data card

Phase-I simulated reference plant; successor to immutable `sim_v1.0`, fixing only B01 RHF shared-noise cancellation. Seed 42; 30 days from 2026-01-05 local Asia/Kolkata; 26 working days, 338 heats, 15-minute clock. {len(result.readings):,} observed rows. Exact config and seed are stored in `config_snapshot.yaml`, `seed.json` and `scenario_manifest.json`. All physical parameters/calibration/production/faults/energy/fuel are unchanged from V1.0.

Public tables: `readings.parquet` contains observed channels; `heats.parquet` heat registers and target-only curated labels; `production.parquet` synthetic mass registers; `events.parquet` supervision/evaluation targets. Use only `schema.load_reading_features()` for readings inputs. `latent_truth.parquet` and `latent_heats.parquet` are internal only. Never join latent health/severity, future failures/events or fault labels into predictors. Treat complete-interval channels as available at interval end (inherited W01).

RHF zone/flue temperatures now use independent seed-derived named streams with the unchanged configured 0.5% relative sensor SD. True state precedes measurement and noise never modifies physics. Their old algebraic severity oracle is resolved; useful noisy fouling information remains. Existing gaps/glitches and every unrelated observed channel are preserved. No standalone claim that public measurements cannot statistically indicate faults is made.

IF SEC {metrics['if_sec']:.6f} kWh/t; plant {metrics['plant_MWh']:.6f} MWh/working day (run mean); bars {metrics['bar_tpd']:.2f} t/working day. Physical KPIs differ from V1.0 by zero. Tests, independent accounting, 30 additional seeds and same-seed byte replay pass. Read `validation_report.md` and `boundary_audit.md` for evidence. Reduced RHF/chemistry physics, accelerated calendar wear and UCI temporal discrepancies remain; no field validation, forecasting accuracy, optimisation or savings claim. Warnings alone do not unfreeze V1.0.

Version immutable. Reproduce/check with Python 3.12, `requirements.lock.txt`, `python -m scripts.release_v11`. Repeated simulation reproduces all Parquets exactly. Release evidence contains measured test-run durations, so regenerating a release package may differ in report bytes; the script refuses to overwrite an existing differing freeze. Replaying the older observation protocol requires its separately hash-pinned V1.0 source, not the patched source.
"""
    for name, body in (("boundary_audit.md", boundary), ("validation_report.md", validation), ("data_card.md", card)):
        (EVIDENCE / name).write_text(body, encoding="utf-8")


if __name__ == "__main__":
    main()
