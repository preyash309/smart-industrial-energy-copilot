# Smart Industrial Energy Copilot — Phase I

Phase II-A monitoring and energy analytics is available as a separate public-data layer. The simulator and `sim_v1.1` remain immutable. Build it with:

```powershell
.venv\Scripts\python.exe -m scripts.phase2_analytics
.venv\Scripts\python.exe -m scripts.phase2_analytics --check
```

Outputs live in `data/processed/analytics_v1/`; reports are `reports/phase2_energy_analytics.md` and `reports/phase2_feature_audit.md`. This layer adds no ML training or optimiser. Completed-heat/interval analytics contain outcomes, so use the explicit task loader instead of selecting numeric columns:

```python
from energy_copilot.analytics import load_predictors
features = load_predictors("data/processed/analytics_v1", "heat_features", "heat_energy")
```

Every predictor carries a legal publication time. Heat outcomes post at heat end, meters at interval end and production/yard registers at shift close, with configurable ingestion delay. Slot inventory is the latest published shift value with age; exact 15-minute yard/rolling state is not present in public inputs. Labels and hidden physical checks stay under `evaluation/`.

This repository prepares the two supplied public datasets and builds a validated, reduced-order reference steel-plant simulator. It contains no predictive models, MILP, generative models, dashboard or savings claims.

Use **Python 3.12**. From the repository root:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.venv\Scripts\python.exe -m scripts.release_v11
```

The V1.1 release runner checks the existing immutable V1.0 evidence, runs every Phase-I test and the B01 RHF boundary regression tests, verifies exact physical agreement with V1.0, then performs independent accounting and boundary checks for 30 additional seeds before freezing the successor. It never overwrites a differing freeze. The historical `scripts.phase1` pipeline prepared public data and produced V1.0; rebuilding that observation protocol requires its original hash-pinned source. Public-data preparation and calibration are unchanged by V1.1.

| Path | Purpose |
|---|---|
| `Readme/` | Four supplied design PDFs, read before implementation |
| `Datasets/` | Supplied originals, unchanged |
| `data/raw/` | Byte-identical read-only CSV copies, SHA256 provenance manifest |
| `data/interim/` | Clean Parquet tables and frozen source-row split manifests |
| `configs/plant_v1.yaml` | Numeric values, units, status, source and notes |
| `configs/calibration_v1.yaml` | Training-only normalized public-data behaviour |
| `configs/schema.yaml` | Complete output contract and feature allowlist |
| `src/energy_copilot/` | Preparation, shared seed factory, simulation, validation and loaders |
| `tests/` | Data, 48-hour V0/V1 and 30-day acceptance gates |
| `reports/` | Audits, plots, assumptions, temporal comparison and simulator report card |
| `data/processed/sim_v1.0/` | Immutable audited predecessor and historical evidence |
| `data/processed/sim_v1.1/` | B01-corrected successor, snapshots, hashes and validation |
| `reports/rhf_boundary_v1.1/` | Independent boundary, accounting, seed and replay evidence |

The UCI source prints each day's last midnight row with the same date after 23:45. Preparation verifies this convention, retains the original timestamp, shifts that midnight to next-day interval end, and uses interval starts for coverage and time splits. Jan–Aug is train, Sep–Oct validation, Nov–Dec test. Calibration never fits the held-out months. AI4I uses seed-42 stratified 70/15/15 partitions; its main target is preserved and identifiers/failure-type columns cannot become inputs.

The furnace uses 6500 kWh / 5000 kW = **78 powered minutes**, plus **27 non-powered minutes** for a baseline 105-minute cycle. Exact subslot integration retains these times on the common 15-minute clock. All material losses, billet inventory and coal/electricity accounting are explicit. Normal melting uses rated power; a labelled partial half-power fault is an abnormal practice mechanism.

The frozen baseline uses thirteen 10 t liquid heats, giving 123.5 t billets and 118.56 t bars per working day. It uses a disclosed 16-hour rolling window and 50 t opening billet stock to meet those targets. These reconcile approximate source figures rather than silently invent capacity. Read `reports/assumption_register.md` and `reports/sim_report_card.md` before interpreting outputs.

For an installed package (optional `pip install -e . --no-build-isolation` with the pinned build dependency installed):

```python
from energy_copilot.sim import simulate

result = simulate("configs/plant_v1.yaml", schedule=None, practice=None, seed=42, days=30)
result.write("data/runs/example")
```

`schedule` maps stable heat IDs to local start timestamps or minutes since simulation start; invalid overlaps, off-day IDs or unmet targets raise `InvariantError`. `practice` may set `practice_loss` in kWh/t liquid or suppress superheat/lid/half-power practice mechanisms. Both interfaces are replay hooks, not an optimiser or an improvement claim. External weather, heat identities/charge marks, calendar degradation and observation tapes are generated first using stable named `numpy.random.Generator` streams. Changing schedule/practice does not change the exogenous tape.

Use only `schema.load_reading_features()` for downstream readings. `latent_truth.parquet` and `latent_heats.parquet` are internal diagnostics; fault labels/events are supervision targets, not input features. Measurement noise never modifies physical state. The schema permits observation gaps/glitches while physical validation enforces true state constraints.

V1.1 resolves the original audit's B01: RHF zone and flue temperatures use separate stable named RNG streams at the existing sensor-noise scale. The old ratio attack no longer recovers latent fouling to numerical precision, while flue temperature retains physical fouling information. See `reports/rhf_boundary_v1.1/boundary_audit.md`. The historical independent audit and its warnings remain unchanged.

The plant's repeated furnace cycles cause lower lag-4 autocorrelation than UCI. This predeclared diagnostic mismatch is documented without fitting the plant to reproduce a different process. Phase-I test success establishes simulation feasibility and reproducibility, not measured plant reliability, forecasting accuracy or savings. Phase II remains outside this implementation.
