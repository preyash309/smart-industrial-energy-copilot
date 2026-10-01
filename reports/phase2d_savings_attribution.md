# Phase II-D simulated savings attribution

All quantities are simulated reference-plant outcomes. DIGITAL-TWIN-REALIZED uses physical truth only in segregated evaluation. OPTIMIZER-PREDICTED remains separate. SYNTHETIC-TARIFF is 4/8/12 Rs/kWh, not a Punjab/PSPCL bill. SYNTHETIC-PRACTICE is the existing loss-40 intervention, not a validated shop-floor recommendation. No EXTERNAL-BENCHMARK is used in replay or as a plant outcome. No field savings, emissions, fuel prices or maintenance benefits are claimed.

S0: conventional back-to-back normal practice/default rolling. S1: original tariff-normal MILP heat AND rolling decisions. S2: origin-day practice loss40 only with unchanged reference policies (shorter heats naturally start subsequent heats earlier). S3: original central practice+tariff MILP; conservative normal/synthetic separately evaluated. Global practice40 is never applied to shared earlier history.

| case vs S0 | kWh reduction | energy reduction % | physical synthetic Rs reduction | physical cost reduction % | QC-known meter Rs difference |
| --- | --- | --- | --- | --- | --- |
| S1 | -0.146775 | -0.000138 | 14858.142702 | 1.878675 | 15131.715789 |
| S2 | 2600.000000 | 2.435841 | 10400.000000 | 1.314984 | 220.736477 |
| S3 | unavailable | unavailable | unavailable | unavailable | unavailable |
| conservative_normal | -0.146775 | -0.000138 | 14858.142702 | 1.878675 | 15131.715789 |
| conservative_synthetic | 2599.766400 | 2.435622 | 33257.448103 | 4.205098 | 33531.981066 |

The primary full S0/S1/S2/S3 bridge is incomplete because original central S3 fails. No combined central saving is invented. Conservative synthetic vs S0 is a valid paired total but not a replacement S3 ablation. Per-seed complete bridges are saved only when all four cases pass. Energy changes and cost changes have independent arithmetic: shifting a normal heat cannot remove its kWh. Small site-energy differences can arise from rolling timing versus calendar wear; these are not furnace efficiency claims. Production/closing stock are checked equal, maintenance decisions are absent, and no avoided downtime is credited.

Realized public MAIN meter kWh × same-slot synthetic price is stored row by row. QC cost invalidates row-level glitch flags and missing energy; no hidden truth or power fallback silently fills a gap. Raw-known, QC-known and coverage are reported. Complete physical evaluation cost is separately labeled evaluation-only. Missing-meter subtotals cannot be called a complete bill. Paired complete physical-cost deltas support controlled simulated attribution; paired known-meter differences support only observed-coverage comparison, not field savings.

| case | valid/attempted | feasible | kWh reduction % valid pairs | physical cost reduction % valid pairs | lower cost % all seeds |
| --- | --- | --- | --- | --- | --- |
| S1 | 5/10 | 50.0% | mean -0.0001; median -0.0001; range [-0.0002, -0.0001] (n=5) | mean 1.3394; median 1.6687; range [0.0822, 2.2032] (n=5) | 50.0% |
| S3 | 0/10 | 0.0% | no valid pairs | no valid pairs | 0.0% |
| conservative_normal | 5/10 | 50.0% | mean -0.0001; median -0.0001; range [-0.0002, -0.0001] (n=5) | mean 1.3394; median 1.6687; range [0.0822, 2.2032] (n=5) | 50.0% |
| conservative_synthetic | 6/10 | 60.0% | mean 2.4354; median 2.4340; range [2.4160, 2.4582] (n=6) | mean 3.6792; median 3.6938; range [2.7426, 4.5412] (n=6) | 60.0% |
