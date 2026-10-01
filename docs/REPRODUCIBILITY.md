# Reproducibility profiles

## Lightweight public demo / CI

Python 3.12 is the qualified interpreter. Create a new environment and install `requirements-demo.txt`; `requirements-dev.txt` adds test tools. These preserve the working UI versions (Streamlit 1.64.0, Plotly 7.1.0, PyYAML 6.0.3). Do not merge this tier into the separately pinned scientific environment.

```sh
python -m venv .venv
# activate using your shell
python -m pip install -r requirements-dev.txt
python scripts/verify_release.py --tests
python -m streamlit run dashboard/app.py
python examples/demo_decision.py
```

The demo loads immutable evidence without internet/API/model training or heavy replay. Four scenarios use one seed/day bundle each. Human feedback writes a new session-local hash-chained audit and never changes frozen evidence. Public verification checks selected-source hashes, bundle coherence, prediction schema, deck metric values/source hashes and main-document links. Lightweight CI runs original simulator, supervisor and dashboard/UI tests plus packaging checks. It does not pretend to run historical corpus-dependent tests.

## Full scientific archive

The complete original scientific archive includes raw/interim data, frozen sim_v1.0/v1.1 and analytics parquet, training/test corpora, full replay populations, failed attempts, split manifests, hash ledgers, release receipts and model/evaluation artifacts. They remain unchanged locally; the Git profile contains selected summaries and inference artifacts rather than multi-run bulk evidence. No automatic external archive download is provided. Request the complete archive from the project owner for full historical reproduction; never silently regenerate and overwrite frozen evidence.

Install `requirements-full.txt` into a **separate** Python 3.12 environment. Its scientific versions (NumPy 2.3.5, pandas 3.0.1, PyArrow 23.0.1, scikit-learn 1.8.0, LightGBM 4.6.0, Pyomo 6.9.5, HiGHS 1.12.0) are unchanged. In the complete archive:

```powershell
$env:PYTHONPATH='src;.'
.venv\Scripts\python.exe scripts/phase3a_release.py --verify
.venv\Scripts\python.exe -m pytest -q
.venv-dashboard\Scripts\python.exe -m pytest tests/test_dashboard.py tests/test_dashboard_ui.py -q
```

Release verification is not training. Full scientific regression requires the archive; missing corpus inputs in a light checkout are not intentionally removed tests. The original tests are all retained.

## Stage commands (archive only)

The existing scripts provide `--help`; inspect exact input/output paths before invocation. Many guards reject writing into frozen releases. Use a disposable full archive copy for regeneration, never the evidence directory being cited.

| Stage | Existing entry point | Prerequisite |
|---|---|---|
| Plant/data/simulator | `python -m scripts.release_v11` | source data/spec/calibration; refuses frozen overwrite |
| Analytics | `python -m scripts.phase2_analytics --check` | frozen sim_v1.1 |
| Model leakage audit | `python -m scripts.phase2b --audit-only` | complete analytics/corpus |
| Training/evaluation | `python -m scripts.phase2b` | source datasets, pinned full environment, disposable outputs |
| MILP | `python -m scripts.phase2c --help` | PredictionService and posting-safe analytics |
| Matched replay | `python -m scripts.phase2d --help` | full exogenous scenario/replay adapter |
| Robust scheduling | `python scripts/phase2e.py --help` | frozen design/splits and replay inputs |
| Maintenance | `python scripts/phase2f.py --help` | frozen maintenance manifests and full runs |
| Supervisor | `python scripts/phase2g.py --help` | full deterministic tool stack |
| Dashboard live | `python scripts/phase3a_live.py --help` | complete archive/protected files, Windows qualified worker environment |

Reproduce the manifest seed/split protocol, never tune using final seeds 201–210 or 2201–2206. Prediction artifacts are byte-preserved and must only be loaded from trusted sources. Demo startup does not load their joblib files. Live simulation in the original qualified archive runs the real G0→prediction→MILP→replay→checker stack; the lightweight checkout fails closed if full protected inputs are absent. No fake live progress is added.

## Release verification

`python scripts/verify_release.py` is the public-profile check. `--tests` invokes the declared CI subset; `--scientific-archive PATH` additionally verifies all original upstream protected hashes against that retained archive. Scientific archive and public product metadata are separate: frozen sim package version 1.1.0 is retained under `docs/archive/frozen_root`; public product version is v1.0.0. The release manifest explicitly records that packaging migration.

Installation validation distinguishes remote wheel resolution from local offline restoration. Network restrictions in the authoring environment may prevent fresh index downloads; the clean-checkout report records the actual tested method rather than claiming unperformed internet installation. CI provides independent ordinary pip installation when GitHub Actions is available.
