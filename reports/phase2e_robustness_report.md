# Robustness and cost trade-off

All outcomes are reduced-order digital-twin simulations. Electricity and synthetic 4/8/12 Rs/kWh cost are separate. No field savings, actual tariff bill, emissions or maintenance benefit is claimed. All strategies use the existing synthetic practice_loss_40 intervention; it is not a qualified shop-floor recommendation.

E0: frozen central scheduler; E1: frozen static conservative scheduler; E2: static scenario-robust scheduler; E3: receding-horizon central scheduler; E4: receding-horizon scenario-robust scheduler.

| strategy | development valid/attempted | validation valid/attempted | final valid/attempted | final conditional kWh | final conditional synthetic Rs | replans |
| --- | --- | --- | --- | --- | --- | --- |
| E0 | 1/6 | 0/4 | 0/10 | unavailable | unavailable | 0 |
| E1 | 5/6 | 3/4 | 6/10 | 104154.500 | 759204.913 | 0 |
| E2 | 6/6 | 2/4 | 5/10 | 104055.697 | 751305.127 | 0 |
| E3 | 1/6 | 2/4 | 5/10 | 103705.911 | 732978.283 | 120 |
| E4 | 6/6 | 4/4 | 10/10 | 104029.870 | 744789.175 | 120 |

Scenario set: central; frozen marginal p90 energy/duration/AUX; two complete development residual-day vectors (median/high-total); one next-heat development positive-residual-p95 stress (3.6434 min). Residuals are relative to p50; max(p90, p50+residual) avoids adding a residual twice. Negative residuals do not shorten nominal occupancy. Energy-duration consistency retains configured full-power/nonpowered lower bounds. No scenario probability or joint safety guarantee is asserted. Whole-day vectors retain dependence/order; pooled adjacent residual correlation is -0.0208, based on only six days. The largest observed residual (~14 min) is represented in a whole-day vector; the p95 next-heat stress alone does not cover every half-power event at every position.

Binary heat-start decisions and rolling feed are shared across all required scenarios. Each scenario has independent inventory state; non-overlap, buffers, end reserve, windows, cooling and additive kVA demand bounds remain hard. Scenario energy shapes reserve a rated-power tail. Inventory posts casts at quarter-hour boundaries, uses opening stock only, and bounds stock before consumption. Feasibility solve precedes electricity-cost minimization. Quantiles remain empirical, not physical guarantees. Explicit buffer support is max(minimum, fraction*(p90-p50)); selected additional fraction is zero because scenario occupancy already reserves upper durations. Candidate policy trade-offs, including failed five-minute-grid trials, are retained.

Feasibility denominators include every declared seed, including failures. Conditional cost/energy statistics describe only feasible executions. Absolute improvement is final E4 rate minus E0 rate; relative improvement is undefined when E0 rate is zero. Matched-reference attribution compares the same loss-40 intervention to back-to-back reference operation. Common practice energy reduction must not be attributed to robustness.

All-attempt machine-readable metrics are in final_regression_comparison.json. Initial host-resource aborts are separately recorded; they are not physical passes and no historical failure is erased. The canonical final experiment has one attempt per strategy/seed, plus retained development resource attempts.

Final E4: 10/10 physical passes, 120 replans, mean 104029.870 kWh/day, IF SEC 630.405 kWh/t, plant intensity 877.445 kWh/t, synthetic cost 744789.175 Rs/day. Mean observed duration MAE 2.148 min, bias 0.449 min, p90 exceedance 0.108, realized end reserve 11.215 min, realized-minus-initial finish -1.993 min. Absolute feasibility improvement over E0 is 100.0 percentage points; relative improvement is undefined with zero E0 passes. E4 versus E0: 0 paired feasible seeds, mean cost delta unavailable% and mean energy delta unavailable kWh; E4 versus E1: 6 paired feasible seeds, mean cost delta -1.992% and mean energy delta -0.103 kWh; E4 versus E2: 5 paired feasible seeds, mean cost delta -1.072% and mean energy delta 0.022 kWh; E4 versus E3: 5 paired feasible seeds, mean cost delta 1.340% and mean energy delta 0.151 kWh. These are conditional comparisons; failed cases remain in the feasibility denominator and cannot supply a complete-day cost.

