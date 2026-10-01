# Results and limitations

All integrated plant results are DIGITAL-TWIN-REALIZED reduced-order simulation evidence. External benchmark metrics do not validate reference-plant operation.

| Experiment | Result | Evidence |
|---|---|---|
| Matched energy / tariff example | 2.435622% lower electricity; 4.205098% lower synthetic tariff cost; production maintained | [Phase II-D](../reports/phase2d_replay_summary.md), SYNTHETIC-PRACTICE / SYNTHETIC-TARIFF |
| Robust adaptive scheduling | E0 0/10; E4 10/10 final scenarios feasible | [Phase II-E](../reports/phase2e_summary.md), seeds 201–210 held out |
| Maintenance development | F0 18/24; F2 21/24 | [Phase II-F](../reports/phase2f_summary.md) |
| Maintenance validation | F0 13/16; F2 16/16 | Same frozen policy |
| Maintenance final | F0 22/24 (91.67%); F2 21/24 (87.50%) | Final feasibility difference −4.17 percentage points |
| Maintenance attribution | 16 executed; 14 strict matched avoided failures; 0 unnecessary within 24 h; 2 undetermined | SYNTHETIC-MAINTENANCE; failed counterfactuals not counted as avoided |
| Supervisor | 81 deterministic scripted cases; 100% expected safe handling; 0 false verified recommendations | [Phase II-G](../reports/phase2g_summary.md); G1 mock is not a live LLM |

For 21 accepted matched maintenance pairs, electricity changed by mean −0.0331%; synthetic tariff cost by +0.0075%. IF SEC was unchanged. Corrective downtime was 2.7246 → 0 summed asset-hours; preventive downtime 0 → 3.5; total 2.7246 → 3.5. These are paired accepted-day metrics, not all-attempt imputed totals. All-attempt feasibility retains unsuccessful cases in the denominator.

Maintenance removed represented equipment failures but did not solve furnace-duration accumulation. A forecast-feasible plan can fail replay; p50/p90 do not certify safety. More robustness can reduce tariff flexibility. Repeated seed/day histories and small final populations limit inference.

The plant is reduced order, not safety-certified. Synthetic tariffs omit real billing/demand/FPPAS details. Synthetic wear/reset/service assumptions are not field maintenance evidence. No real service, labor or spare cost exists; no maintenance ROI/payback is calculated. AI4I is machine-state synthetic data, not a days-ahead degradation series. Real deployment needs field sensor validation, calibration, industrial trials and secure operations.

Packaging changes no scientific result. Complete failed runs, attribution ledgers, training corpora and latent evaluation evidence are retained in the full research archive, not erased from the experiment merely because the GitHub profile is smaller.
