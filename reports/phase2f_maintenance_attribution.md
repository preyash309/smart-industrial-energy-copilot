# Phase II-F strict maintenance attribution

Final: 16 acknowledged executed services; 14 independently full-day verified. 14 strict matched avoided failures; 0 unnecessary within 24 hours; 2 undetermined.

Avoided requires the same asset to fail in the completed matched F0 replay, preventive service to finish before its represented failure threshold, and no corresponding failure within the configured horizon in completed F2. The postprocessor checks these conditions without changing the frozen raw labels. If either matched day fails, attribution remains undetermined. Unnecessary requires a completed no-action counterfactual with no same-asset failure in the service-relative 24-hour window; no longer-term value claim follows.

Unnecessary rate: 0/16 executed services = 0.00%. MILL/PMP breakdown: {'MILL_01': {'executed': 6, 'classifications': {'averted_within_24h': 5, 'undetermined_counterfactual': 1}}, 'PMP_01': {'executed': 10, 'classifications': {'averted_within_24h': 9, 'undetermined_counterfactual': 1}}}.

Recommendation dispositions: {'executed': 16, 'replaced_by_replan': 7}. Each selected recommendation appearance ends in an explicit terminal disposition; candidate windows not selected by the solver have a separate ledger. Repeated or replaced proposals do not add executed service counts.

See `executed_service_ledger.parquet`, `recommendation_disposition_ledger.parquet`, `unselected_candidate_dispositions.parquet` and the untouched per-case raw attribution. These are EVALUATION-ONLY, not runtime predictors. No maintenance ROI, labor cost, spare-part cost or rupee benefit from avoided failures is inferred.
