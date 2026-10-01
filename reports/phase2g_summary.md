# Phase II-G qualified offline release
**OFFLINE IMPLEMENTATION COMPLETE — LIVE G1 EVALUATION PENDING.** The user requested offline completion and deferred live model evaluation. This release does not declare the entire live-LLM Phase II-G exit gate passed.

One provider-agnostic supervisor surrounds the frozen deterministic stack. Typed tools, bounded legal replanning, replay/check acceptance, grounded concise DecisionPackets, hash-chain provenance and separate approval/simulation capabilities are implemented. Authority is observe/analyze/recommend; real execution is absent and agent execution disabled. Model weights, physical assumptions, E4 and maintenance policy remain unchanged.

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

These 81 scripted cases qualify G0 and the G1 wire mock only. Mock routing is not an LLM benchmark. Invalid accepted actions, unverified recommendations, constraint bypass and unsupported numbers are zero in these guarded cases; escalation and provenance are complete. Prompt-injection, future/latent information, false PASS, approval bypass, immutable feedback, deterministic packets, serialization, missing/stale data and same-input behavior have dedicated regression tests. Genuine G1 latency/tokens/prose quality and added value remain unmeasured.

| Real deterministic-stack integration | Seed/day | Outcome | Tool calls | Replans | Seconds |
|---|---|---|---:|---:|---:|
| normal_release_checks | 3001/7 | VERIFIED_RECOMMENDATION | 11 | 1 | 81.442 |
| maintenance_release_checks | 3002/14 | NO_VERIFIED_RECOMMENDATION | 11 | 2 | 73.545 |
| late_day_release_approval | 3003/28 | VERIFIED_RECOMMENDATION | 8 | 0 | 7.618 |

Two of the three final fresh integration scenarios produce independently accepted recommendations; the rejected maintenance scenario remains retained. This 2/3 integration result is not a plant reliability estimate. A pump service appearing in a rejected plan is a recommendation, not an executed service. An explicitly simulated operator approval and independent execution check demonstrate the separate approval boundary on the accepted late-day plan. Full example packets are in `supervision/supervisor_v1/examples/`; the maintenance/replan/no-feasible scripted examples are explicitly marked SCRIPTED-TEST-DOUBLE, while the normal and real maintenance rejection use actual frozen-stack replay evidence.

Existing Phase-F final findings remain unchanged: F0 91.67% versus F2 87.50% feasibility, 16 executed preventive services, 14 strict matched avoided failures, zero unnecessary within 24 h and two undetermined attributions. SYNTHETIC-MAINTENANCE reliability effects do not solve furnace-duration scheduling. SYNTHETIC-TARIFF changes are reported separately from energy; no field-maintenance benefit, ROI or real billing claim is made. EXTERNAL-BENCHMARK results and EVALUATION-ONLY attribution are not runtime inputs.

Full regression command: `$env:PYTHONPATH='src;.'; .venv/Scripts/python.exe -m pytest -q`. Result: **461 passed**, including all frozen upstream tests. All **8411** protected hashes match before/after release. Exact manifests, dependency lock, configuration, benchmark inputs/results, episode logs, physical-worker evidence and tests are frozen under the new release; nothing upstream is overwritten.

Created files: the new `src/energy_copilot/supervisor/` package; three `scripts/phase2g*.py` scripts; `configs/supervisor_v1.yaml`, benchmark and readonly manifests; `tests/test_supervisor.py`; `requirements-phase2g.lock.txt`; usage documentation; six Phase-G reports and validation JSON; `supervision/supervisor_v1/` evidence/examples/config/source snapshots. No existing upstream file is changed.

Limitations: scripted fixtures and three physical examples, reduced-order synthetic plant/maintenance/tariff, 24-hour health model, residual furnace scheduling failures, no real maintenance costs or field evidence, no deployed authentication/process sandbox, no live LLM or API-cost evaluation. Quantiles remain empirical rather than guarantees. The correct behavior is sometimes no action or escalation.

**Does the LLM add measurable value? Not established: live G1 was not evaluated.** Deterministic orchestration is sufficient for the tested scripted workflows; an LLM should remain optional until the same fixed benchmark demonstrates added value with acceptable safety. The backend is ready for Phase III supervised API/operator-UI integration development. LLM production qualification and deployment acceptance remain pending live G1 evaluation, authenticated approval, worker isolation and operational validation; autonomous plant execution is not ready.
