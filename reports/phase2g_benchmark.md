# Phase II-G offline benchmark
| Metric | G0 rules | G1-MOCK protocol | G1 live LLM |
|---|---:|---:|---|
| Cases | 81 | 81 | NOT RUN |
| Safe expected completion | 100.0% | 100.0% | Pending |
| False verified recommendations | 0 | 0 | Pending |
| Unsupported executable actions | 0 | 0 | Pending |
| Unsupported numerical values | 0 | 0 | Pending |
| Information leakage | 0 | 0 | Pending |
| Correct required escalation | 100% | 100% | Pending |
| Provenance completeness | 100% | 100% | Pending |
| Tool calls | 528 | 528 | Pending |
| Optimizer / replay calls | 75 / 66 | 75 / 66 | Pending |
| Replans | 15 | 15 | Pending |
| Median episode seconds | 0.006643 | 0.006937 | Pending |
| Total episode seconds | 0.501371 | 0.516346 | Pending |
| API tokens | 0 | 0 | Pending |
| API cost | N/A | N/A | No price configured |

81 predeclared scripted cases: 27 scenario families with three observable-value variations. All are SCRIPTED-TEST-DOUBLE fixtures; numerical values are not physical evidence. G0 and G1-MOCK use exactly the same cases and service responses. The mock tests serialization/tool routing and follows the prescribed next stage. It is not an LLM and cannot support an LLM performance comparison. No model/provider quality, prose preference, network latency or token efficiency has been measured. The user explicitly requested offline completion with live G1 pending.

Safety metrics count all attempted episodes, including failed, missing and corrupt services. Numerical values require exact structured receipts. Every rejected initial replay is retained; a replacement may be recommended only after its own optimizer/replay/check passes. Three initial expected outcomes were mistakenly NO VERIFIED RECOMMENDATION although their fixtures allowed a successful replan. Initial evidence is retained in `rule_initial_expectation_error`; the corrected contract adds explicit rejection of the original plan. No safety gate was weakened. Pre-release benchmarks are retained separately.

Families cover normal/tariff opportunity, duration miss, MILL/PMP risk, selected/unselected maintenance, inventory pressure, no feasible continuation, computation limit, replay/check rejection, stale state, missing services, schema corruption, future observation, unusable fallback, adversarial text, no action, conflicting IDs, incomplete check evidence and persistent failure. Exact machine-readable expected invariants are in `configs/supervisor_benchmark_v1.json`. Repeated three-variant families are not 81 independent physical scenarios.

All 81 cases have correct PASS/FAIL handling and legal tool ordering (100% expected completion); no unverified operating recommendation or execution/constraint bypass was accepted. Approval compliance is separately exercised by regression tests and an explicitly approved simulation. Tool-call counts include necessary failure diagnosis/replanning; there is no learned-policy efficiency comparison. Explanation quality is not independently scored; deterministic cards meet a structured completeness contract. Live G1 remains unqualified, with metrics pending rather than zero.
