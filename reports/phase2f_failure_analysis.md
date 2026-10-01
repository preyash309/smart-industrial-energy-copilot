# Phase II-F retained failure analysis

28 of 192 strategy attempts failed their continuation or independent replay checks. Every failure remains in the partition tables and feasibility denominators.

| Split | Strategy | Seed | Day | Cause | Completed heats | Completed duration bias min | Reason |
|---|---|---:|---:|---|---:|---:|---|
| development | F0 | 2001 | 28 | inventory_or_rolling_availability | 0 | unavailable | Requested rolling exceeds opening stock/capacity/remaining target at 2026-02-02 00:45:00: requested 2.0, feasible 1.4332113544330545 |
| development | F0 | 2003 | 12 | solver_infeasibility | 12 | 1.05 | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| development | F0 | 2003 | 14 | solver_infeasibility | 12 | 2.23 | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| development | F0 | 2004 | 14 | solver_infeasibility | 12 | 0.69 | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| development | F0 | 2004 | 26 | end_of_day_overrun | 12 | 0.69 | D026_H12 cannot complete daily target within working day: end 1442.56 min |
| development | F0 | 2005 | 14 | solver_infeasibility | 12 | 1.35 | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| development | F1 | 2001 | 28 | inventory_or_rolling_availability | 0 | unavailable | Requested rolling exceeds opening stock/capacity/remaining target at 2026-02-02 00:45:00: requested 2.0, feasible 1.4332113544330545 |
| development | F1 | 2003 | 12 | solver_infeasibility | 12 | 1.05 | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| development | F1 | 2003 | 14 | solver_infeasibility | 12 | 2.23 | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| development | F1 | 2004 | 14 | solver_infeasibility | 12 | 0.69 | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| development | F1 | 2004 | 26 | end_of_day_overrun | 12 | 0.69 | D026_H12 cannot complete daily target within working day: end 1442.56 min |
| development | F1 | 2005 | 14 | solver_infeasibility | 12 | 1.35 | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| development | F2 | 2003 | 12 | solver_infeasibility | 12 | 1.05 | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| development | F2 | 2004 | 14 | end_of_day_overrun | 12 | -0.78 | D014_H12 cannot complete daily target within working day: end 1440.57 min |
| development | F2 | 2004 | 26 | end_of_day_overrun | 12 | 0.69 | D026_H12 cannot complete daily target within working day: end 1442.56 min |
| validation | F0 | 2101 | 14 | inventory_or_rolling_availability | 4 | 2.05 | Requested rolling exceeds opening stock/capacity/remaining target at 2026-01-19 07:30:00: requested 2.0, feasible 1.0021378019058222 |
| validation | F0 | 2103 | 28 | end_of_day_overrun | 12 | 0.30 | D028_H12 cannot complete daily target within working day: end 1447.02 min |
| validation | F0 | 2104 | 28 | inventory_or_rolling_availability | 6 | -0.52 | Requested rolling exceeds opening stock/capacity/remaining target at 2026-02-02 11:45:00: requested 2.0, feasible 0.9878359923954122 |
| validation | F1 | 2101 | 14 | inventory_or_rolling_availability | 4 | 2.05 | Requested rolling exceeds opening stock/capacity/remaining target at 2026-01-19 07:30:00: requested 2.0, feasible 1.0021378019058222 |
| validation | F1 | 2103 | 28 | end_of_day_overrun | 12 | 0.30 | D028_H12 cannot complete daily target within working day: end 1447.02 min |
| validation | F1 | 2104 | 28 | inventory_or_rolling_availability | 6 | -0.52 | Requested rolling exceeds opening stock/capacity/remaining target at 2026-02-02 11:45:00: requested 2.0, feasible 0.9878359923954122 |
| final | F0 | 2204 | 28 | solver_infeasibility | 12 | 2.52 | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| final | F0 | 2205 | 26 | end_of_day_overrun | 12 | 0.68 | D026_H12 cannot complete daily target within working day: end 1442.77 min |
| final | F1 | 2204 | 28 | solver_infeasibility | 12 | 2.52 | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| final | F1 | 2205 | 26 | end_of_day_overrun | 12 | 0.68 | D026_H12 cannot complete daily target within working day: end 1442.77 min |
| final | F2 | 2202 | 14 | solver_infeasibility | 5 | 0.47 | No feasible maintenance continuation at feasibility |
| final | F2 | 2204 | 28 | solver_infeasibility | 12 | 0.64 | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| final | F2 | 2205 | 26 | end_of_day_overrun | 12 | 0.68 | D026_H12 cannot complete daily target within working day: end 1442.77 min |

Continuation failures retain completed-heat and public-state ledgers, but lack a completed independently accepted day. Their energy, tariff and full-day production are not imputed from successful runs. Service decisions in failed cases remain committed-attempt records, with undetermined failure attribution where the complete counterfactual is unavailable. A final heat deadline miss remains a scheduling/forecast failure even if preventive service removed a wear failure.

Duration bias uses only acknowledged completed heats and their predictions. Positive-error sums and the last public state time are retained in `*_failure_diagnostics.parquet`. They diagnose consumed schedule slack; they do not assign an unobserved future fault as the cause of an aborted day.

Final reporting refinement: seed 2202/day 14 F2 ended at a solver limit after five heats. The generic frozen classification is retained; no proof of physical/mathematical infeasibility is claimed. It remains a failed attempted case. The other final failures are remaining-window/duration failures, not automatically attributed to maintenance. See `final_failure_diagnostics.parquet`.
