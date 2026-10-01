# Remaining failures

All outcomes are reduced-order digital-twin simulations. Electricity and synthetic 4/8/12 Rs/kWh cost are separate. No field savings, actual tariff bill, emissions or maintenance benefit is claimed. All strategies use the existing synthetic practice_loss_40 intervention; it is not a qualified shop-floor recommendation.

E0: frozen central scheduler; E1: frozen static conservative scheduler; E2: static scenario-robust scheduler; E3: receding-horizon central scheduler; E4: receding-horizon scenario-robust scheduler.

Every failed final attempt remains in failure_analysis.parquet. No infeasible schedule is represented as feasible; failed complete-day cost/energy is unavailable.

| seed | strategy | status | cause | reason |
| --- | --- | --- | --- | --- |
| 201 | E0 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 201 | E1 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 202 | E0 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 202 | E3 | no_feasible_continuation | solver_infeasibility | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| 203 | E0 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 204 | E0 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 204 | E2 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 204 | E3 | no_feasible_continuation | solver_infeasibility | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| 205 | E0 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 205 | E3 | no_feasible_continuation | end_of_day_overrun | D007_H12 cannot complete daily target within working day: end 1441.70 min |
| 206 | E0 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 206 | E1 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 206 | E2 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 207 | E0 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 207 | E3 | no_feasible_continuation | solver_infeasibility | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| 208 | E0 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 208 | E1 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 208 | E2 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 209 | E0 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 209 | E2 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 209 | E3 | no_feasible_continuation | solver_infeasibility | No eligible candidates under required scenario reserve/buffer occupancy bounds |
| 210 | E0 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 210 | E1 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |
| 210 | E2 | replay_infeasible | duration_miss_overlap | Schedule has overlapping heat or wrong working day |

failure_mechanisms_evaluation_only.parquet lists matched exogenous physical marks, including half-power, charge/lid/superheat extensions, and outages where present. static_heat_execution_evaluation_only.parquet reproduces exact unchanged controls, including partial failed traces. failure_causal_context_evaluation_only.parquet identifies the preceding heat, its actual end, blocked next start, exact overlap duration and physical contributing marks for every static overlap. These are post-experiment evaluation labels. A mark present somewhere in a day is not itself proof that it caused the failure. Overlap/end-of-day failures are traced to duration misses; no-feasible continuations retain their actual past state and forecast histories. All successful traces independently pass mass/electricity/fuel, demand, cooling, production, inventory, windows/capacity and exact-command checks. Calendar day 7 has no maintenance-outage robustness evidence; later failure-day scheduling is outside this release.

Final failure counts: 19 exact static overlaps, four central adaptive solver-infeasible continuations after 12 completed heats, and one central adaptive end-of-day overrun. Reproduced static overlaps range from 0.159 to 11.716 minutes. No E4 final attempt failed. These counts are descriptive evaluation results, not policy selection criteria.
