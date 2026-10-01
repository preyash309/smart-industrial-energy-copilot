# Phase II-G retained failures
| Final integration attempt | Seed/day | Outcome | Tool calls | Replans | Seconds |
|---|---|---|---:|---:|---:|
| normal_release_checks | 3001/7 | VERIFIED_RECOMMENDATION | 11 | 1 | 81.442 |
| maintenance_release_checks | 3002/14 | NO_VERIFIED_RECOMMENDATION | 11 | 2 | 73.545 |
| late_day_release_approval | 3003/28 | VERIFIED_RECOMMENDATION | 8 | 0 | 7.618 |

Real integration uses fresh seeds 3001/3002/3003, days 7/14/28; no Phase II-D or F final seeds were used for development or policy tuning. These are integration examples, not a new reliability population. The normal static robust plan is rejected and the frozen adaptive continuation passes. The late-day plan passes. The maintenance scenario selects a preventive pump window in its initial plan, but its replay/continuation is rejected; no verified maintenance recommendation is fabricated. Remaining furnace timing/continuation failures are distinct from maintenance eligibility. Public rejection reasons and retained logs support classification; private physical outputs remain EVALUATION-ONLY.

An early G maintenance attempt repeated the same rejected adaptive plan and collided with an existing replay evidence directory. This is a supervisory infrastructure defect, not a physical failure. The original attempt/logs are retained; the fixed wrapper escalates unchanged rejected candidates without rewriting evidence. Replay itself is idempotent for frozen controls. Earlier three scripted benchmark mismatches were expected-contract errors for recoverable rejection; their evidence is retained and the original-rejection invariant strengthened. A regression exposed timing-dependent packet hashes; semantic provenance now excludes latency while the audit still records it.

All scripted missing/stale/corrupt/unsafe services, checker/replay rejection and persistent failure cases fail closed or take a bounded verified replan. Computation limits explicitly say no accepted continuation was obtained within the solve limit; they never claim proven infeasibility. Correct no-action cases issue no operating change. Remaining live G1 model/tool selection failures are unknown because live evaluation was deferred.
