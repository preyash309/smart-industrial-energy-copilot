# Information and immutability audit

All outcomes are reduced-order digital-twin simulations. Electricity and synthetic 4/8/12 Rs/kWh cost are separate. No field savings, actual tariff bill, emissions or maintenance benefit is claimed. All strategies use the existing synthetic practice_loss_40 intervention; it is not a qualified shop-floor recommendation.

E0: frozen central scheduler; E1: frozen static conservative scheduler; E2: static scenario-robust scheduler; E3: receding-horizon central scheduler; E4: receding-horizon scenario-robust scheduler.

PASS: immutable upstream hash manifest; disjoint development/validation/final split; calibration function refuses non-development seeds; frozen policy/config/core source hashes before final evaluation. Source training/calibration code never reads 201–210 outcomes. Frozen Phase II-B artifacts are unchanged.

PASS: public_snapshot projects an explicit sensor/heat allowlist before state/prediction creation; drops fault_label, events, latent truth, health/severity/future failures. Slots require interval_start+15min <= current_time. Completed heat logs require end <= current_time. Past-only heat summaries and condition features retain per-feature posting timestamps. PredictionService independently rejects schema/time violations and unsafe fallbacks. Current-slot material arrival is a completed public billet register, not an unknown future cast.

PASS: typed remaining input validates model/schema, quantile order, calendar/tariff identity, physical parameters, actual inventory and unchanged full production order. Completed records are deeply immutable dataclasses; already executed feed cannot change. Independent checker includes current-slot known arrivals and fixed feed. Tests poison hidden columns and reject future arrivals/predictions and lowered orders.

Evaluation-only: physical twin truth/fault marks are accessible only to replay/checking/report modules, never to feature/context construction. The execution gateway generates the full random tape before decisions but hands the controller filtered public snapshots. Same-seed prefix/default output equivalence is tested. Node-limited optimality and fixed calendar/accelerated degradation are limitations; empirical scenarios are not certified joint safety bounds.
