"""Checked predicted plans, plots, provenance and deterministic handoff reports."""
from dataclasses import asdict,replace
from pathlib import Path
import json
import platform
import importlib.metadata
import pandas as pd
import numpy as np
import yaml
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from energy_copilot.common import write_json,sha256
from energy_copilot.optimization import optimize,check_schedule
from energy_copilot.optimization.contracts import timestamp
from energy_copilot.optimization.baseline import baseline_schedule
from energy_copilot.optimization.explain import explanation_data

OUT=Path('plans/optimizer_v1')


def store(name,inp,result,baseline=None):
    if not result.releasable or not check_schedule(inp,result)['feasible']:raise RuntimeError(f'Cannot release {name}: {result.reason}')
    result=replace(result,explanation_data=explanation_data(inp,result,baseline))
    directory=OUT/name;directory.mkdir(parents=True,exist_ok=True)
    write_json(directory/'result.json',result.to_dict())
    pd.DataFrame(result.schedule).to_parquet(directory/'schedule.parquet',index=False)
    pd.DataFrame(result.inventory_trajectory).to_parquet(directory/'inventory.parquet',index=False)
    rows=[]
    for r in result.load_trajectory:
        row={k:v for k,v in r.items() if k not in ('asset_run','asset_kWh')}
        row.update({a+'_kWh':v for a,v in r['asset_kWh'].items()});row.update({a+'_run':v for a,v in r['asset_run'].items()});rows.append(row)
    pd.DataFrame(rows).to_parquet(directory/'load.parquet',index=False)
    write_json(directory/'checker.json',result.checker)
    return result


def release(inp,provenance,protected,c1):
    from scripts.phase2c import verify_frozen
    results={};stage_inputs={};gates={}
    results['c1_feasibility']=store('c1_feasibility',inp,c1);stage_inputs['c1_feasibility']=inp;gates['C1']='PASS'
    for name,objective in [('c2_energy_normal','energy'),('c3_tariff_normal','cost'),('c4_tariff_synthetic','cost')]:
        current=replace(inp,objective_mode=objective)
        baseline=baseline_schedule(current)
        if not baseline.releasable:raise RuntimeError('Reference predicted schedule failed independent gate')
        practices=None if name.startswith('c4') else ('normal',)
        result=optimize(current,practices=practices)
        key='predicted_total_kWh' if objective=='energy' else 'predicted_tariff_cost_Rs'
        if not result.releasable or result.predicted_metrics[key]>baseline.predicted_metrics[key]+inp.constraints.tolerance:raise RuntimeError('Stage objective/reference gate failed '+name)
        results[name]=store(name,current,result,baseline);stage_inputs[name]=current;gates[name[:2].upper()]='PASS'
        if name=='c3_tariff_normal':results['central_baseline']=store('central_baseline',current,baseline);stage_inputs['central_baseline']=current
    conservative=replace(inp,optimization_mode='conservative',objective_mode='cost')
    b=baseline_schedule(conservative)
    results['conservative_baseline']=store('conservative_baseline',conservative,b);stage_inputs['conservative_baseline']=conservative
    normal=optimize(conservative,practices=('normal',));r=optimize(conservative)
    for name,result in [('conservative_tariff_normal',normal),('conservative_tariff_synthetic',r)]:
        if not result.releasable or result.predicted_metrics['predicted_tariff_cost_Rs']>b.predicted_metrics['predicted_tariff_cost_Rs']+inp.constraints.tolerance:raise RuntimeError('C5 failed')
        results[name]=store(name,conservative,result,b);stage_inputs[name]=conservative
    gates['C5']='PASS'
    # Exact frozen service coefficients and API inputs. Contains predictions, not targets.
    write_json(OUT/'optimizer_input.json',asdict(inp));write_json(OUT/'conservative_input.json',asdict(conservative))
    write_json(OUT/'origin_provenance.json',provenance)
    for fname in ('configs/optimizer_v1.yaml','requirements-phase2c.lock.txt'):
        (OUT/Path(fname).name).write_bytes(Path(fname).read_bytes())
    write_json(OUT/'runtime_manifest.json',dict(python=platform.python_version(),packages={n:importlib.metadata.version(n) for n in ('pyomo','highspy','ply','numpy','pandas','lightgbm','scikit-learn')}))
    schema=dict(version='optimizer_v1',prediction_version=inp.prediction_version,timezone='Asia/Kolkata',accounting='96 x 15 min',
        candidate_start_grid_minutes=inp.constraints.candidate_step_minutes,
        input_contract='energy_copilot.optimization.OptimizerInput',output_contract='energy_copilot.optimization.OptimizerResult',
        inputs_available='All observations/predictions published <= forecast_origin; future calendar/tariff and candidate decisions are known inputs.',
        public_predictions=['HeatPrediction','LoadPrediction(AUX only)','HealthPrediction(informational 24h)'],
        schedule_fields={k:type(v).__name__ for k,v in results['c3_tariff_normal'].schedule[0].items()},
        schedule_units=dict(energy_p50_kWh='kWh',energy_p90_kWh='kWh',duration_p50_min='min',duration_p90_min='min',selected_energy_kWh='kWh',selected_duration_min='min'),
        metrics_units=dict(predicted_total_kWh='kWh/day',predicted_IF_SEC_kWh_per_t='kWh/t liquid',predicted_peak_kVA_bound='kVA conservative additive/nameplate bound',
            predicted_peak_average_kVA='kVA interval-average combined P/Q',predicted_peak_kW_reserve='kW nameplate reserve',predicted_tariff_cost_Rs='Rs electricity energy cost under supplied synthetic tariff'),
        release_rule='feasible MILP incumbent AND independent arithmetic checker pass',
        forecast_modes=dict(central='energy/duration/AUX p50',conservative='energy/duration/AUX p90; not a safety guarantee'),
        forbidden_inputs=['evaluation Parquets','actual future targets','latent truth','future events','fault severity'],sec_target=inp.constraints.sec_target_kWh_per_t)
    (OUT/'optimizer_schema.yaml').write_text(yaml.safe_dump(schema,sort_keys=False),encoding='utf-8')
    # Necessarily infeasible policies are exposed, never patched/recalibrated.
    strict=replace(inp,constraints=replace(inp.constraints,candidate_step_minutes=15),heat_candidates=tuple(k for k in inp.heat_candidates if timestamp(k.start).minute%15==0))
    examples={'strict_15_minute_reference':optimize(strict,practices=('normal',))}
    excessive=replace(inp,production_order=replace(inp.production_order,bars_t=200))
    examples['excess_production']=optimize(excessive)
    examples['low_demand_cap']=optimize(replace(inp,constraints=replace(inp.constraints,demand_limit_kVA=500)))
    examples['impossible_SEC_cap']=optimize(replace(inp,constraints=replace(inp.constraints,sec_target_kWh_per_t=500)))
    for name,result in examples.items():
        if result.status!='infeasible' or result.releasable:raise RuntimeError('Infeasibility gate failed')
    write_json(OUT/'infeasible_examples.json',{name:r.to_dict() for name,r in examples.items()})
    comparisons={}
    for name,base in [('c3_tariff_normal','central_baseline'),('c4_tariff_synthetic','central_baseline'),('conservative_tariff_normal','conservative_baseline'),('conservative_tariff_synthetic','conservative_baseline')]:
        comparisons[name]={k:results[name].predicted_metrics[k]-results[base].predicted_metrics[k] for k in results[name].predicted_metrics if isinstance(results[name].predicted_metrics[k],(int,float))}
    write_json(OUT/'predicted_comparison.json',dict(label='OPTIMIZER-PREDICTED; not verified savings',deltas=comparisons))
    validation=dict(stage_gates=gates,independent_checkers={name:r.checker['feasible'] for name,r in results.items()},
                    frozen_inputs=verify_frozen(),evaluation_or_hidden_solver_inputs=False,simulator_replay_completed=False,
                    tests='See reports/phase2c_tests.json',input_sha256=sha256(OUT/'optimizer_input.json'))
    write_json(OUT/'validation_report.json',validation)
    plots(results,inp)
    reports(inp,results,examples,provenance,validation)
    (OUT/'data_card.md').write_text('''# optimizer_v1 predicted plan data card

Checked deterministic Phase II-C plans for 2026-01-12, using only frozen forecast_v1 public typed predictions and completed analytics_v1 history. Same 13 ordered heats, 130 t liquid, 123.5 t billets and 118.56 t bars; opening/required closing yard stock 50 t. No realized future outcomes, hidden truth/events, retraining, recalibration or simulator replay. Source/protection hashes, input snapshots, config, runtime, schema and independent checkers accompany the plans.

Every accounting/rolling/availability horizon has 96 quarter-hour slots. Starts may occur every five minutes, explicitly documented to avoid false 120-min occupancy rounding. A strict 15-min-start reference is infeasible and separately recorded. Energy/duration/AUX quantiles use p50 centrally or p90 conservatively. p90 is empirical uncertainty, not a physical guarantee. Full-power heat-tail energy approximation and additive/nameplate apparent-power bound are documented in the reports. Pump/RHF/compressor retain reference duties; bar yield/SEC/capacity and PF originate from frozen plant parameters. No SEC cap was supplied in release examples; explicit caps are supported and tested.

Tariff inputs are synthetic Rs/kWh values, separate from mathematics and not a Punjab bill. practice_loss_40 plans are synthetic interventions, not real shop-floor recommendations. Health risk is informational, not an automatic shutdown/maintenance policy. Independent checker passes all released schedules, but detailed metallurgy/thermal physics and actual future faults require Phase II-D evaluation. The frozen twin accepts heat starts and a global practice setting; it does not accept this optimizer's rolling dispatch table or per-heat mixed practices. This compatibility gap must be handled explicitly during Phase II-D; no exact replay is claimed here.

Regenerate: PYTHONPATH=src; python -m scripts.phase2c --stage all. Solve archived inputs with input_from_dict and optimize; check independently with check_schedule. Plans contain predicted coefficients and decision outputs, not ML feature tables. Do not treat them as measured outcomes or verified savings.
''',encoding='utf-8')
    sources=list(Path('src/energy_copilot/optimization').glob('*.py'))+list(Path('scripts').glob('phase2c*.py'))+list(Path('tests').glob('test_optimizer*.py'))+[Path('configs/optimizer_v1.yaml'),Path('requirements-phase2c.lock.txt')]
    write_json(OUT/'code_manifest.json',{p.as_posix():sha256(p) for p in sources})
    files=[p for p in OUT.rglob('*') if p.is_file() and p.name!='release_manifest.json']
    write_json(OUT/'release_manifest.json',dict(version='optimizer_v1',hashes={p.relative_to(OUT).as_posix():sha256(p) for p in files}))
    print('C1-C5 PASS; released',len(results),'independently checked predicted plans; frozen files',protected['protected_files'])


def plots(results,inp):
    d=Path('reports/phase2c');d.mkdir(exist_ok=True)
    for name in ('central_baseline','c3_tariff_normal','c4_tariff_synthetic','conservative_tariff_synthetic'):
        r=results[name];slots=pd.DataFrame(r.load_trajectory);hours=np.arange(inp.constraints.horizon_slots)*inp.constraints.slot_minutes/60
        fig,axes=plt.subplots(5,1,figsize=(12,11),sharex=True)
        for a in ('IF_01','MILL_01','PMP_01'):axes[0].step(hours,[int(v[a]) for v in slots.asset_run],where='post',label=a)
        axes[0].set_ylabel('On');axes[0].legend(ncol=3)
        axes[1].step(hours,slots.total_kW,where='post',label='Mean kW');axes[1].step(hours,slots.kVA_bound,where='post',label='kVA bound');axes[1].axhline(inp.constraints.demand_limit_kVA,color='r',linestyle='--',label='Contract');axes[1].set_ylabel('Load');axes[1].legend(ncol=3)
        axes[2].step(np.arange(inp.constraints.horizon_slots+1)*inp.constraints.slot_minutes/60,[v['inventory_t'] for v in r.inventory_trajectory],where='post');axes[2].set_ylabel('Yard (t)')
        axes[3].step(hours,np.cumsum(slots.bar_t),where='post');axes[3].set_ylabel('Cumulative bars (t)')
        axes[4].step(hours,slots.tariff_Rs_per_kWh,where='post');axes[4].set_ylabel('Synthetic Rs/kWh');axes[4].set_xlabel('Hours from local midnight')
        fig.suptitle(name+' — OPTIMIZER-PREDICTED, no replay');fig.tight_layout();fig.savefig(d/(name+'.png'),dpi=140);plt.close(fig)


def reports(inp,results,examples,provenance,validation):
    lines=['# Phase II-C optimizer summary','',
        '**PASS — C1–C5 and independent schedule release gates. OPTIMIZER-PREDICTED; no twin replay or verified savings.**','',
        'Pyomo 6.9.5 + highspy/HiGHS 1.12.0, serial deterministic seed 42, zero requested relative MIP gap. Pinned additive lock: requirements-phase2c.lock.txt (includes ply 3.11); earlier dependencies unchanged. [APPSI interface](https://pyomo.readthedocs.io/en/6.9.5/api/pyomo.contrib.appsi.solvers.highs.Highs.html), [HiGHS release](https://pypi.org/project/highspy/1.12.0/).','',
        'Horizon 2026-01-12 local midnight to midnight, 96 × 15-minute material/meter/availability slots. All candidates and forecasts generated before building a solver. Known completed history from Jan 5–11 is predicate-filtered at posting time before loading; last published shift-close inventory is 50 t. Orders remain 13 heats, 130 t liquid, 123.5 t billets, 118.56 t bars, closing stock at least 50 t. No stock drawdown funds the comparison.','',
        '## Decisions and objectives','',
        'Binary x[candidate_id] = x[heat,start,practice], furnace_on[t], pump_on[t], asset_run[asset,t]; continuous inventory[0..96] and rolling_t[0..95] (billet feed tonnes). Heat sequence preserves supplied identity order. Candidate starts use a five-minute subslot grid while all accounting and rolling remain at 15 minutes. Occupancy reserves ceil(predicted duration / start grid). With normal p50 ≈105.2 min and p90 ≈108.4 min, the strict 15-min-start policy reserves 120 min/heat and cannot fit 13 heats into 24h. That infeasibility is recorded rather than shortening a forecast or lowering output. Five-minute resolution is an explicit optimizer assumption, not a physical/configuration recalibration.','',
        'C1: feasibility objective 0, normal practice. C2: sum predicted slot kWh. C3: sum slot kWh × supplied Rs/kWh, normal practice. C4: same cost objective with explicitly supported synthetic practice_loss_40. C5: central vs conservative marginal quantiles. No weighted multiobjective, carbon/fuel objective, or maintenance scheduling. No SEC target was supplied: cap is explicitly disabled in release examples. Optional input cap is enforced; tests demonstrate a 635 cap and infeasible 500 cap without changing forecasts.','',
        '## Predicted comparison','',
        'All rows produce 118.56 t bars / 123.5 t billets and end at 50 t inventory. Synthetic tariff: offpeak 4, normal 8, peak 12 Rs/kWh; these are test inputs, not a jurisdiction-specific bill.','',
        '| Plan | MWh | IF SEC kWh/t | Synthetic cost Rs | Peak kVA bound | Yard minimum t | Reserved IF utilization |','|---|---:|---:|---:|---:|---:|---:|']
    for name in ('central_baseline','c2_energy_normal','c3_tariff_normal','c4_tariff_synthetic','conservative_baseline','conservative_tariff_normal','conservative_tariff_synthetic'):
        m=results[name].predicted_metrics
        lines.append(f"| {name} | {m['predicted_total_kWh']/1000:.4f} | {m['predicted_IF_SEC_kWh_per_t']:.4f} | {m['predicted_tariff_cost_Rs']:.2f} | {m['predicted_peak_kVA_bound']:.3f} | {m['inventory_min_t']:.3f} | {m['reserved_furnace_utilization']:.4%} |")
    lines+=['','Normal-practice tariff scheduling changes synthetic cost while leaving predicted kWh/SEC unchanged in this example. The coupled intervention changes both forecast energy and cycle time through the frozen models; no independent MILP efficiency formula was added. Comparison deltas are in plans/optimizer_v1/predicted_comparison.json. These are predicted differences, not verified savings.','',
        '## Constraints and binding evidence','',
        'Each heat exactly once; ordered nonoverlapping furnace occupancy at the configured start grid; every heat finishes within horizon; IF and all service equipment respect supplied windows/availability; full-power energy tail requires at least configured 27 nonpowered minutes; cooling ON whenever IF powered; configured cast/melt/rolling yields; billet output requirement; exact bar order (no gratuitous overproduction); mill and RHF feed capacity, mill nameplate energy limit; rolling consumes only opening stock; 97 bounded yard states and conservative intra-slot arrival upper bound; explicit closing reserve; configured RHF setpoint inside 1150–1250 C; supported practice allowlist; optional SEC cap; per-slot additive apparent-power/nameplate reserve <=7000 kVA. All are hard, with no violation-slack variables.','']
    for name in ('c3_tariff_normal','c4_tariff_synthetic','conservative_tariff_synthetic'):
        a=results[name].active_constraints
        lines.append(f"- {name}: demand slack {a['min_demand_slack_kVA']:.3f} kVA; binding demand slots {a['binding_demand_slots']}; production slack {a['production_slack_t']:.6f} t; closing inventory slack {a['closing_inventory_slack_t']:.6f} t; lower/upper yard binding boundaries {a['binding_inventory_lower']} / {a['binding_inventory_upper']}; SEC cap absent; {a['binary_start_variables']} start binaries, {a['constraints']} constraints.")
    lines+=['','Full solver termination/bounds and active constraints accompany each result. Production and closing stock bind; nameplate demand has positive slack, so no claim that demand was the optimization bottleneck. Furnace reservation utilization approaches the one-day limit. No IIS/minimal infeasible subsystem is claimed.','',
        '## Approximations and handoff limitations','',
        'IF forecast energy is placed at 5-MW full power at the END of the predicted cycle; preceding time is nonpowered. This preserves forecast total energy and leaves the configured nonpowered minimum but does not reproduce every half-power/repair/delay trajectory. Heat energy remains exact under overlap integration into 15-min slots. Nameplate IF/mill/compressor reserve is used for demand, separate from average electrical energy. Additive asset apparent power upper-bounds combined P/Q apparent power by the triangle inequality; both are reported. PF is fixed to versioned configuration. AUX is the ONLY forecast component; five controlled feeders are added once. No MAIN forecast is consumed.','',
        'RHF nominal readiness and compressor loaded/idle duty retain the reference window; pump stays continuously on when available. Mill energy follows 100 kWh/t bars with configured yield/capacity. Wear/future faults, chemistry and detailed thermal dynamics are not modeled by the MILP. Equipment availability is an external planning/permissive assumption, including qualified cooling flow; a health probability cannot certify tomorrow’s availability.','',
        'Frozen V1.1 accepts arbitrary-time heat-start maps plus a GLOBAL practice setting, but not this rolling dispatch table or mixed per-heat modes. Released intervention plans use one global mode, yet an exact origin-state/rolling-policy replay adapter still needs explicit design in Phase II-D. Do not silently replay a different rolling policy or apply an intervention to earlier history and call it matched conditions. No replay has occurred here.','',
        'p90 is empirical, not a physical guarantee; individual energy/duration quantiles are not a joint calibrated safe region. Shifted/stale-history schedules remain outside Phase II-B’s separate prospective validation. Synthetic practice loss 40 is not a real shop-floor recommendation. Inherited chemistry/wear/UCI/tariff warnings remain unchanged. No demand charges/FPPAS/kVAh billing, fuel costs, emissions or verified savings.','',
        '## Health, infeasibility, tests and next phase','']
    for p in inp.health_predictions:lines.append(f"- {p.asset_id}: raw 24-h failure probability {p.failure_probability:.6g}, calibrated {p.calibrated_probability:.6g}; informational only. Tests changing risks to 0.999 leave the schedule unchanged.")
    for name,r in examples.items():lines.append(f'- {name}: **{r.status.upper()}**, unreleasable; {r.reason}.')
    lines+=['','All existing and new test results: reports/phase2c_tests.json. Deterministic C1 and cost solves, typed input serialization/reload, analytical toy optimum, independent tamper attacks, unavailable services, SEC/demand/output infeasibility, p50/p90 selection, source separation, null sensors, posting timestamps, fallback rejection and frozen hashes are tested. No model retraining or simulator/config/data modification.','',
        'New code: src/energy_copilot/optimization/{contracts,candidates,model,constraints,objective,solve,checker,baseline,explain,__init__}.py; scripts/phase2c{,_setup,_release}.py; configs/optimizer_v1.yaml and phase2c_readonly_manifest.json; requirements-phase2c.lock.txt; tests/test_optimizer_*.py; docs/phase2c_usage.md; plans/optimizer_v1; three Phase-II-C reports and aligned load/production/inventory plots. No earlier-phase source/artifact files changed.','',
        'Phase II-D receives exact orders/state/availability/tariff, origin-frozen typed predictions, model/schema hashes, solver decisions and independent-checker evidence. Next work is an explicitly compatible matched-condition replay and outcome evaluation, including handling of replay-policy gaps and forecast misses. It is not completed in Phase II-C.','',
        '![Central normal plan](phase2c/c3_tariff_normal.png)','', '![Conservative synthetic experiment](phase2c/conservative_tariff_synthetic.png)']
    Path('reports/phase2c_optimizer_summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    Path('reports/phase2c_constraint_audit.md').write_text('''# Phase II-C constraint audit

PASS — every released plan passes the MILP feasibility status AND an optimizer-independent ledger checker. check_schedule imports contracts only, never Pyomo/model/coefficients/constraint expressions. It reconstructs every selected prediction, timestamps/end/reservation, 96-slot power overlap, 97 stock boundaries, delayed billet arrivals, material consumption/yields, nameplate demand reserve, combined mean P/Q kVA, service/interlock/calendar/capacity constraints, fixed RHF setpoint, SEC cap, energy totals and tariff cost. Reported metric/trajectory/quantile/state alterations and unknown fields fail closed. Checker results are saved beside every plan; zero mass/energy residuals within 1e-6 numeric tolerance. Interlocks remain boolean, never relaxed.

PASS — incremental gates: C1 normal feasibility passed before C2 energy, C3 generic tariff, C4 supported synthetic practice and C5 conservative quantiles. All comparisons retain 13 heats, 123.5 t billets, 118.56 t bars and 50-t opening/closing inventory. No violation slacks, output reduction or stock depletion finance the objective. Both selected forecast modes meet the 7000-kVA bound.

PASS — tests include hand-computed toy optimum 65952 Rs; changed cost/power/mass/production/temperature/quantiles/states/stock/overlap rejected independently; strict 15-minute-start reference, insufficient output/services, low demand/SEC and excessive closing reserve explicitly infeasible. Repeated inputs produce identical results. Explicit externally unavailable pump blocks powered IF candidates. Health risk does not implicitly change availability.

WARNING — five-minute starts are an explicit optimization-grid assumption inside the quarter-hour accounting horizon. If an operator requires starts ONLY on quarter-hour boundaries, the 13-heat reference is infeasible with current central/conservative duration predictions; do not label that case feasible. The optimizer rounds reservations upward and never shortens a prediction.

WARNING — nameplate/additive apparent-power bounds are conservative deterministic reduced-model constraints, not future physical guarantees. AUX quantiles/PF/availability are assumptions, and p90 coverage is empirical. Fixed in-range RHF setpoint and supported practice membership replace unrepresented thermal/metallurgical relationships; no chemistry solver, fault oracle or future outage model is introduced. Physical replay remains necessary. Thermal dynamics, within-slot rolling distribution and schedule-controlled mill/fuel faults are outside this MILP. The next-boundary billet release/opening-stock-only rolling rules deliberately protect availability and intra-slot inventory.

WARNING — detailed source/replay limitations are in phase2c_optimizer_summary.md: frozen twin lacks arbitrary rolling dispatch and mixed per-heat practice interfaces. All plans are predictions, not completed simulator replay or savings. No Phase-I assumptions/warnings, Phase-II-A tables or Phase-II-B artifacts changed. Verification hashes cover 847 protected files; stage/test/release manifests contain evidence.
''',encoding='utf-8')
    Path('reports/phase2c_prediction_integration.md').write_text('''# Phase II-C prediction integration and availability audit

PASS — only the public typed forecast.PredictionService supplies production coefficients. build_optimizer_input checks the versioned prediction_contract.json and prediction_schema.yaml SHA256 before any generation. Each heat/hour/practice requests the exact 12-feature schema with origin-frozen historical values and legally known proposed calendar. Equal predictor envelopes within one hour reuse the returned typed coefficient; no energy/duration estimator, model fitting or private service method lives in optimization. Ordered identities are derived from known configured calendar, not actual future heat/event rows.

PASS — AUX forecast uses origin-frozen load lags 1/2/4/96, preceding 4/96 means/std and an already posted prior-day seasonal profile. All 96 horizons are direct service outputs. Candidate history/past heat SEC/duration is completed and published no later than origin; it never incorporates predicted or realized intervening future heat outcomes. Two health calls use current completed public sensor observations and strictly prior windows; only informational probabilities enter output. All contexts carry per-field publication bounds.

PASS — scripts.phase2c projects a strict list of public analytics_v1 columns and applies PyArrow available_at <= forecast_origin filters BEFORE converting to data frames. No events, hidden tables, evaluation Parquets, source noise tapes or predictions/test_* are read. Completed past heat outcomes are legitimate history; future/current candidate outcomes are never loaded. Reporting stores typed predictions and solver decisions only, never actual future targets. Models/forecast source remain unchanged; no simulator imports/replay or training calls in optimization.

PASS — validation rejects late publication, unknown practices, wrong candidate identity/size, unsafe fallback, wrong schema/version, missing/gapped/MAIN load forecasts, malformed timestamps, crossed/nonfinite quantiles, inconsistent SEC, tariff periods/rates, invalid stock/order/yields/temperatures and unsupported assets. Inventory is an explicitly supplied known opening state (demo uses last posted shift register), not hidden instantaneous stock. Equipment availability masks are externally supplied planning assumptions, not future realized faults or a health threshold. JSON round-trip preserves typed input/predictions; source is scanned for prohibited table/training APIs.

WARNING — publication stamps/provenance must be honest upstream; the API cannot detect deliberately fabricated timestamps or forged typed predictions. Demo zero-delay posting is inherited, not proof of actual ERP/sensor latency. Missing sensors stay null for frozen model preprocessing; no latent or future imputation. Stale day-ahead heat context, shifted scheduling, synthetic practice, fixed January/AUX calendar and empirical marginal quantile limitations remain as documented by Phase II-B. No Phase-II-B artifact, feature schema or probability calibrator was changed. This is semantic data separation, not an OS permission/security boundary.

Audit and reproduction: plans/optimizer_v1/{optimizer_input,conservative_input,origin_provenance}.json; optimizer_v1.yaml; optimizer_schema.yaml; runtime/code/release manifests; per-plan result/checker JSON. Original inputs/source protected by configs/phase2c_readonly_manifest.json. See reports/phase2c_tests.json for actual full test command and outcome.
''',encoding='utf-8')
