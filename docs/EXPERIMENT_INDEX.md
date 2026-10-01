# Experiment index

| Phase | Responsibility / major result | Final evidence |
|---|---|---|
| I | physical plant, data audit, 30-day simulation; RHF observation fix | [Simulation card](../reports/sim_report_card.md), [independent audit](../reports/phase1_independent_audit.md), [sim_v1.1 data card](../data/processed/sim_v1.1/data_card.md) |
| II-A | posting-safe accounting/features | [Energy analytics](../reports/phase2_energy_analytics.md), [feature audit](../reports/phase2_feature_audit.md) |
| II-B | independent prediction + uncertainty, separate UCI/AI4I | [Models](../reports/phase2b_model_summary.md), [uncertainty](../reports/phase2b_uncertainty_report.md), [leakage](../reports/phase2b_leakage_audit.md) |
| II-C | deterministic constrained MILP | [Optimizer](../reports/phase2c_optimizer_summary.md), [constraints](../reports/phase2c_constraint_audit.md) |
| II-D | matched replay; forecast-feasible plans can fail | [Replay](../reports/phase2d_replay_summary.md), [limitations](../reports/phase2d_limitations.md) |
| II-E | robust/adaptive final 0/10→10/10 comparison | [Summary](../reports/phase2e_summary.md), [failure analysis](../reports/phase2e_failure_analysis.md) |
| II-F | maintenance final 91.67%→87.50%, 14 strict avoided | [Summary](../reports/phase2f_summary.md), [attribution](../reports/phase2f_maintenance_attribution.md) |
| II-G | 81 deterministic safety cases; live G1 pending | [Supervisor](../reports/phase2g_summary.md), [information boundary](../reports/phase2g_information_boundary.md) |
| III-A | seven pages, four coherent cases, explicit approval | [Dashboard](../reports/phase3a_summary.md), [UI audit](../reports/phase3a_ui_audit.md), [demo script](../reports/phase3a_demo_script.md) |
| IV | public packaging without scientific retuning | [Release audit](../reports/phase4_release_audit.md), [clean checkout](../reports/phase4_clean_checkout_validation.md) |

Detailed reports retain their original archive-relative provenance paths. Some point to bulk evidence intentionally retained in the full archive rather than Git; `REPRODUCIBILITY.md` and the public-profile manifest declare this boundary. Historic absolute paths in retained reports are historical receipts, not portable runtime commands.
