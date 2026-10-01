# Receding-horizon execution

All outcomes are reduced-order digital-twin simulations. Electricity and synthetic 4/8/12 Rs/kWh cost are separate. No field savings, actual tariff bill, emissions or maintenance benefit is claimed. All strategies use the existing synthetic practice_loss_40 intervention; it is not a qualified shop-floor recommendation.

E0: frozen central scheduler; E1: frozen static conservative scheduler; E2: static scenario-robust scheduler; E3: receding-horizon central scheduler; E4: receding-horizon scenario-robust scheduler.

Trigger: immediately after each completed heat. Commitment: current heat cannot move; rolling feed is immutable once its quarter-hour slot begins. State uses completed heat billet weights and accepted feed acknowledgements, not latent yard truth. Completed outcomes update legitimate prior-heat history; frozen heat/health models are called again. The frozen AUX API supports midnight origins only, so its published day-ahead forecast is retained without pretending it was refreshed.

For a completion inside a quarter hour, decision_time is the actual posted completion; accounting_geometry_start is the beginning of the current quarter hour. Current-slot feed is fixed; the just-completed billet arrival is a known constant at that slot's close. The opening inventory is reconstructed from that acknowledgement ledger. All new heat starts must be at/after decision_time; one-minute rounding adds at most one minute. Heat log outcomes are immediately available; meter observations are usable only after interval_end. No open interval is posted early.

The remaining-work objective excludes completed IF electricity. Already committed current-slot service energy is a constant and cannot affect decisions. Full-day energy, production, cost, peak demand and stock come only from independent complete replay. Every step records timestamps, public feature values/posting times, prediction version, uncertainty set, remaining heats, chosen plan, constraints and trigger. Replanning does not retrain weights or tune a policy online. No online residual correction was necessary.

Early development quarter-boundary waiting controllers failed after 12 heats; those smoke attempts are retained. Waiting created avoidable cumulative latency. The successor immediate-posting contract removes that wait while preserving the sensor availability boundary.
| strategy | development valid/attempted | validation valid/attempted | final valid/attempted | final conditional kWh | final conditional synthetic Rs | replans |
| --- | --- | --- | --- | --- | --- | --- |
| E0 | 1/6 | 0/4 | 0/10 | unavailable | unavailable | 0 |
| E1 | 5/6 | 3/4 | 6/10 | 104154.500 | 759204.913 | 0 |
| E2 | 6/6 | 2/4 | 5/10 | 104055.697 | 751305.127 | 0 |
| E3 | 1/6 | 2/4 | 5/10 | 103705.911 | 732978.283 | 120 |
| E4 | 6/6 | 4/4 | 10/10 | 104029.870 | 744789.175 | 120 |
