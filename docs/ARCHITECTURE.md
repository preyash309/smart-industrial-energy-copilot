# Architecture and responsibilities

The production prototype is deterministic. The simulator owns physical state; analytics own accounting and posting-time features; PredictionService predicts; MILP chooses candidates; independent replay/checking judges physical feasibility; G0 orchestrates and explains; DashboardService presents structured evidence and records operator feedback.

`energy_copilot.sim.simulate` uses the frozen 15-minute reference plant. RHF true zone/flue temperatures respond physically to fouling; independent seed-derived sensor streams prevent exact shared-noise cancellation. Noise never modifies material/energy state. `latent_truth.parquet` remains evaluation-only.

Analytics contracts use interval_start, interval_end and available_at. Completed heat outcomes become history only after posting. Forecast preprocessing is fitted on training data; whole-seed splits prevent within-run target mixing. `energy_copilot.forecast.interfaces.PredictionService` supplies independent heat energy/duration, AUX-only load and MILL/PMP risk predictions. Marginal p90 values are empirical upper forecast quantiles, not joint guarantees.

`energy_copilot.optimization` uses Pyomo/HiGHS. Candidate heat coefficients come from the typed prediction interface. Controllable asset loads are constructed separately from AUX to avoid MAIN double counting. Furnace occupancy, production, yard, rolling, demand and pump/process constraints are hard. Independent checker mathematics do not reuse MILP expressions.

`energy_copilot.replay` runs matched exogenous conditions. `energy_copilot.robust` reserves slack, builds frozen uncertainty scenarios and replans remaining decisions after observed completion. Executed decisions stay immutable. `energy_copilot.maintenance` uses the frozen health/sensor gate and synthetic service semantics; no hidden wear enters planning.

`energy_copilot.supervisor` is one deterministic G0 state machine with bounded typed tools. Optimization feasibility, accepted replay and checker PASS are all required for VERIFIED. A computational limit is not proof of infeasibility. VERIFIED differs from APPROVED. Explicit human approval is required before any permitted simulated execution; dashboard execution is disabled. LLM provider adapters exist but live G1 remains unqualified/pending.

`energy_copilot.dashboard.service.DashboardService` loads one coherent evidence bundle per scenario. It keeps OPTIMIZER-PREDICTED and DIGITAL-TWIN-REALIZED separate and preserves source IDs, config hashes and chained approval records. Demo never invokes heavy services; live simulation is explicitly requested and requires the full archive. UI pages do not implement plant mathematics.

Energy, tariff exposure, reliability, schedule robustness and production are separate outputs. UCI Steel and AI4I benchmark experiments are separate from integrated simulated plant operation.
