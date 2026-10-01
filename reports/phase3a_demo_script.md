# Three-minute operator demonstration

| Time | Screen / scenario | What to say / show |
|---|---|---|
| 0:00–0:25 | Overview / Normal optimization | “This is our simulated SME steel plant. The snapshot is known at the decision time; these separate completed-day KPIs show the verified replay outcome.” Point to production, electricity, SEC and demand. |
| 0:25–0:45 | Energy / Normal optimization | “This is where electricity is going. Historical expected heat energy and actual completed heat energy make discrepancies explainable without asserting a hidden fault.” |
| 0:45–1:10 | Optimise / Normal optimization | “The deterministic robust optimizer chooses a schedule under production, demand, inventory and cooling constraints.” Show tariff shading, predicted metrics and rolling/inventory. Identify the prior observed reference timeline honestly. |
| 1:10–1:30 | Decision Center / Replay rejection | “We do not trust solver feasibility alone. This initial candidate failed physical replay and is withheld.” Show that Approve is disabled. |
| 1:30–1:50 | Decision Center / Adaptive recovery | “Bounded deterministic replanning produced a replacement that passed replay and the independent checker. VERIFIED is still not APPROVED.” Explicitly confirm simulated review and Approve if demonstrating audit workflow. |
| 1:50–2:15 | Maintenance / Maintenance warning | “Predictive risk creates policy-eligible service candidates, not an exact failure time. This initial pump-service candidate was rejected; selection is not execution.” |
| 2:15–2:45 | Impact | “Here are separately attributed historical results: 2.44% simulated electricity and 4.21% synthetic tariff reductions in the matched Phase-D example; final E0 0/10 versus E4 10/10 robustness. Phase F prevented represented equipment failures but did not improve final scheduling feasibility.” |
| 2:45–3:00 | Evidence / Audit | “Each number and decision points to a model, plan, replay, checker and configuration. Approval is audited; this prototype controls no machinery.” |

Use Demo Mode throughout this path; precomputed evidence is visibly labelled and no fake solver animation runs. Optional live appendix: select Normal optimization and click Run full simulation; show actual backend stage events and wait for its independently checked result. Live computation is outside the three-minute presentation path.
