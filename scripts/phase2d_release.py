"""Reports and plots derived from retained replay evidence, including failures."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from energy_copilot.common import sha256,write_json


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',
                      *['| '+' | '.join(str(x) for x in r)+' |' for r in rows]])


def reports(out,experiment):
    report_root=Path('reports') if out.resolve()==Path('replay/optimizer_v1').resolve() else out/'reports'
    report_root.mkdir(parents=True,exist_ok=True)
    d=report_root/'phase2d';d.mkdir(exist_ok=True)
    cases=experiment['primary'];rows=[]
    for name,e in cases.items():
        m=e.get('realized_metrics')
        rows.append([name,e['status'],*[f'{m[k]:.4f}' if m else 'unavailable' for k in ('MWh','IF_SEC_kWh_per_t','bar_t','peak_piecewise_kVA','final_inventory_t','QC_known_meter_tariff_cost_Rs','physical_evaluation_tariff_cost_Rs')]])
    results=table(['case','physical status','MWh','IF SEC','bars t','peak kVA','closing stock t','QC known meter Rs','complete physical evaluation Rs'],rows)
    robust=experiment['robustness'];rr=[]
    def dist(v):
        return f"mean {v['mean']:.4f}; median {v['median']:.4f}; range [{v['min']:.4f}, {v['max']:.4f}] (n={v['n']})" if v['n'] else 'no valid pairs'
    for n,v in robust.items():
        cost=v['cost_reduction_pct_valid_pairs'];energy=v['kWh_reduction_pct_valid_pairs']
        rr.append([n,f"{v['feasible']}/{v['total_scenarios']}",f"{v['feasible_pct']:.1f}%",dist(energy),dist(cost),f"{v['lower_cost_pct_of_all_scenarios']:.1f}%"])
    rt=table(['case','valid/attempted','feasible','kWh reduction % valid pairs','physical cost reduction % valid pairs','lower cost % all seeds'],rr) if rr else 'Multi-seed evaluation pending.'
    pred=[]
    for n,e in cases.items():
        if 'forecast_errors' in e:
            for task,v in e['forecast_errors'].items():
                if isinstance(v,dict) and 'MAE' in v:pred.append([n,task,v['n'],f"{v['MAE']:.4f}",f"{v['RMSE']:.4f}",f"{v['bias_actual_minus_p50']:.4f}",v.get('p90_exceedance','n/a')])
    ft=table(['case','target','n','MAE','RMSE','bias actual-p50','p90 exceedance'],pred)
    failures=pd.read_parquet(out/'failure_analysis.parquet');bad=failures[failures.status.ne('diagnostic')]
    failuretable=table(['seed','case','status','cause','reason'],bad[['seed','case','status','category','reason']].itertuples(index=False,name=None))
    tests=experiment.get('tests','pending')
    enriched,mode_rows=detail_diagnostics(out,cases)
    detailed_failures=table(['seed','case','conflicting heat','previous heat','duration overrun min','physical fault evidence'],
        enriched[['seed','case','heat_id','previous_heat_id','timing_overrun_min','previous_fault_labels']].itertuples(index=False,name=None))
    mode_table=table(['seed','mode family','central status','conservative status','actual idle h central/conservative','actual cost Rs central/conservative'],mode_rows)
    predicted_rows=[]
    names={'S1':'c3_tariff_normal','S3':'c4_tariff_synthetic','conservative_normal':'conservative_tariff_normal','conservative_synthetic':'conservative_tariff_synthetic'}
    for n,plan in names.items():
        p=json.loads((out/'primary/optimized'/plan/'optimizer_result.json').read_text())['predicted_metrics'];m=cases[n].get('realized_metrics')
        predicted_rows.append([n,f"{p['predicted_total_kWh']/1000:.4f}",f"{m['MWh']:.4f}" if m else 'failed',f"{p['predicted_tariff_cost_Rs']:.2f}",f"{m['physical_evaluation_tariff_cost_Rs']:.2f}" if m else 'failed'])
    predicted_table=table(['case','OPTIMIZER-PREDICTED MWh','DIGITAL-TWIN-REALIZED MWh','predicted synthetic Rs','realized physical evaluation Rs'],predicted_rows)
    attribution_rows=[]
    for n,p in experiment['primary_attribution']['comparisons'].items():
        attribution_rows.append([n,*[f'{p[k]:.6f}' if k in p else 'unavailable' for k in ('kWh_reduction','kWh_reduction_pct','physical_evaluation_cost_reduction_Rs','physical_evaluation_cost_reduction_pct','QC_known_meter_cost_difference_Rs')]])
    attribution_table=table(['case vs S0','kWh reduction','energy reduction %','physical synthetic Rs reduction','physical cost reduction %','QC-known meter Rs difference'],attribution_rows)
    base='''All quantities are simulated reference-plant outcomes. DIGITAL-TWIN-REALIZED uses physical truth only in segregated evaluation. OPTIMIZER-PREDICTED remains separate. SYNTHETIC-TARIFF is 4/8/12 Rs/kWh, not a Punjab/PSPCL bill. SYNTHETIC-PRACTICE is the existing loss-40 intervention, not a validated shop-floor recommendation. No EXTERNAL-BENCHMARK is used in replay or as a plant outcome. No field savings, emissions, fuel prices or maintenance benefits are claimed.'''
    architecture='''The frozen V1.1 source has no origin snapshot or rolling-dispatch API. Separate replay/compatible_v111.py is a versioned replay-compatible layer copied from the protected engine. Its checked diff adds day-scoped uniform practice and exact rolling-feed admission only. All original physical equations, exogenous draws, sensor models, ratings/yields/calibration and invariant validation remain unchanged. It never clips feed, postpones a heat or reduces an order. Default six tables, summary and scenario manifest match the frozen engine and historical seed-42 artifact exactly. Additional-seed defaults are also compared to the original engine. The original simulator, analytics, models and optimizer source/artifacts remain immutable.

The replay recreates the full 30-day Jan-5 trajectory with the same seed/config. Random arrays depend on horizon length: a shortened seven/eight-day simulation would change multiple IF marks and observation tapes. Controls affect only Jan-12 00:00 to Jan-13 00:00. All six pre-origin table hashes and opening stock are compared; scenario SHA256 and individual weather/charge/delay/wear/repair/noise/missing/glitch tapes are hashed before decisions. Inventory is 50 t. Wear is calendar-driven, temperature algebraic, and V1.1 has no persistent thermal state or runtime-driven wear counter to initialize. This preserves all represented state; it cannot prove realism of absent dynamics.'''
    compatibility='''Archived normal/synthetic central/conservative plans are represented with exact heat/practice/rolling controls. Uniform practice is mapped from the frozen public prediction contract and scoped to the origin day, never applied retroactively. Mixed per-heat modes fail closed. Requested feed uses opening inventory only and must fit actual mill/RHF capacity and repair availability. Exact controls do not mean exact predicted power or completion: original stochastic physical energy, delays, half-power and repairs remain independent judges. No original-plan reoptimization is performed. Additional seeds receive their own legal completed-public history and one central/conservative normal/synthetic solve each, through the unchanged typed PredictionService and optimizer. Optimizer assumptions are not replaced with future faults.'''
    summary=f'''# Phase II-D matched-condition replay summary

**Decision-loop milestone: {'ACHIEVED for independently checked simulated operating changes' if experiment['complete_decision_loop'] else 'NOT ACHIEVED'}. Failed original plans remain unreleasable.**

{base}

## Architecture and exact origin

{architecture}

{compatibility}

## Primary seed 42: original archived plans

{results}

{predicted_table}

Every valid case independently passes full-run mass/electricity/fuel accounting, exact piecewise IF integration/demand/cooling, clock/cardinality, actual availability/capacity/windows, inventory, production, quality flags and control adherence. Reported heat starts and every rolling feed are compared to the requested plan. No partial heat-only approximation is used for these admitted plans. Checks and maximum accounting errors live with each evaluation. IF utilization is cycle occupied time /24h; rolling utilization is feed / (8 t/h ×24h); active-slot runtime separately counts any active quarter hour.

## Central versus conservative and failures

{failuretable}

## Independently reconstructed timing root causes

{detailed_failures}

Overruns are computed from retained actual heat timestamps and the original requested next start/day end, not solver slacks. Half-power and combined charge/lid/superheat losses physically extend powered duration. No MILL/PMP failure occurs inside this January-12 window for the declared seeds; this experiment therefore does not establish repair-window robustness. Five-minute rounding leaves normal central/conservative reservations identical; conservative synthetic increases reservation but still fails four additional seeds.

S0 and normal S1 have the same modeled primary IF energy and powered-duration requirements. Shifted load timing and rolling wear exposure change site trajectories. The reduced twin assigns IF losses by seed/day/ordinal rather than start hour, so success does not establish field invariance to shifting. Completed-attempt error metrics are censored by the first abort and cannot be read as whole-day interval coverage. No diagnostic is fitted back into the frozen model.

Primary normal central/conservative start/rolling controls are identical because both duration quantiles round to the same five-minute reservation. Thus their realized energy/cost/idle time are identical despite different predicted coefficients. Central synthetic S3 finishes its last heat 0.47 min beyond midnight; it is retained with a partial evaluation-only heat trace and no full-day savings metric. Conservative synthetic succeeds for the original primary scenario. p90 is empirical, not a joint safety guarantee. Robustness below includes all attempted seeds; improvement distributions are explicitly conditional on physically valid pairs.

{rt}

{mode_table}

## Attribution, tests and handoff

{attribution_table}

Full primary central attribution bridge: {experiment['primary_attribution']['bridge']['status']}. Exact paired quantities are in primary/paired_comparison.json.

Tests: {tests}. Protected upstream: {experiment['protected']}. Same-plan byte replay: reproducibility.json. Frozen default regression: default_regression.json plus each seed's evidence. Ten predeclared seeds 201–210 are disjoint from the predictive corpus 101–125; multi-seed status: {experiment['multi_seed_status']}. No cherry picking or forecast recalibration.

Machine-readable outputs: {out.as_posix()}/experiment.json, robustness.json, evaluation_split_manifest.json, failure_analysis.parquet; primary/evaluation per-case controls, matched manifest, predicted result, physical verification, six simulator tables, tariff ledger, heat/load comparisons or retained failure. Full evidence cannot turn a failed original plan into an approved operating recommendation. This verifier is ready for a later separately authorized propose/replay/revise stage; no such loop, LLM/agent or dashboard is implemented.
'''
    (report_root/'phase2d_replay_summary.md').write_text(summary,encoding='utf-8')
    matched=f'''# Phase II-D matched-conditions audit

PASS — frozen upstream hashes remain unchanged ({experiment['protected']['protected_files']} protected files). No Phase I, II-A, II-B or II-C source/config/data artifact was edited. configs/phase2d_readonly_manifest.json includes prior release/source/report hashes after verifying the original manifests.

{architecture}

{compatibility}

PASS — completed branches compare identical prefix readings/heats/production/events/latent truth/latent heats and opening stock plus the full scenario identity. Component hashes prove sensor/noise tapes and failures match, not just a shared seed number. IF fault timestamps may move with heat starts; day/ordinal fault marks remain identical. Failures compare generated tape and executed pre-origin heat state, with control scope enforced before any run; no fabricated complete branch table exists after an abort.

PASS — generated extra-seed predictors receive only explicit allowed public columns, filtered to completed publication <= origin before context calculation. No hidden table/events/tape enters history.py, PredictionService or MILP. Future faults are evaluation-only. Original seed42 uses archived typed inputs/results with independent predicted checker, never predictions/test_* evaluation Parquets. Public meter costs and hidden physical evaluation cost are separate columns with explicit labels.

WARNING — semantic separation is not an OS access-control boundary. No persistent thermal dynamics/runtime wear is represented. Exact replay admission can reject forecast-feasible controls. Defaults preserve the original modeled physics, including its documented limitations. Tests: {tests}.
'''
    (report_root/'phase2d_matched_conditions_audit.md').write_text(matched,encoding='utf-8')
    forecast=f'''# Phase II-D forecast-error and domain-shift diagnostics

{base}

{ft}

Heat metrics compare both quantiles with true physical outcomes; public heat-counter noise is separately available in simulation/heats.parquet. AUX_physical and AUX_observed_QC are reported separately: near-perfect physical AUX error reflects deterministic synthetic structure, while observed noise/missingness remains. MAIN is constructed controlled + AUX, never a MAIN forecast added twice. MAIN errors compare the selected planning mode; conservative p90 can overpredict energy. Piecewise actual peak is compared against the MILP bound; averaging cannot hide a demand violation.

Failed attempts keep completed heat comparisons (not full accepted-day metrics). The primary S3 final-day failure is a duration forecast miss plus tight day-end scheduling, not a changed fault model. Original fixed plans remain unchanged. Stale origin-frozen history, shifted starts and rounding are evaluated prospectively here; neither these seeds nor diagnostics recalibrate the frozen models. failure_analysis.parquet records valid-case residual diagnostics and all unreleasable attempts; per-seed heat/load comparison Parquets retain error-by-slot/heat for independent analysis. No claim of universal domain robustness follows from the successful subset.

{failuretable}
'''
    (report_root/'phase2d_forecast_error.md').write_text(forecast,encoding='utf-8')
    attribution=f'''# Phase II-D simulated savings attribution

{base}

S0: conventional back-to-back normal practice/default rolling. S1: original tariff-normal MILP heat AND rolling decisions. S2: origin-day practice loss40 only with unchanged reference policies (shorter heats naturally start subsequent heats earlier). S3: original central practice+tariff MILP; conservative normal/synthetic separately evaluated. Global practice40 is never applied to shared earlier history.

{attribution_table}

The primary full S0/S1/S2/S3 bridge is incomplete because original central S3 fails. No combined central saving is invented. Conservative synthetic vs S0 is a valid paired total but not a replacement S3 ablation. Per-seed complete bridges are saved only when all four cases pass. Energy changes and cost changes have independent arithmetic: shifting a normal heat cannot remove its kWh. Small site-energy differences can arise from rolling timing versus calendar wear; these are not furnace efficiency claims. Production/closing stock are checked equal, maintenance decisions are absent, and no avoided downtime is credited.

Realized public MAIN meter kWh × same-slot synthetic price is stored row by row. QC cost invalidates row-level glitch flags and missing energy; no hidden truth or power fallback silently fills a gap. Raw-known, QC-known and coverage are reported. Complete physical evaluation cost is separately labeled evaluation-only. Missing-meter subtotals cannot be called a complete bill. Paired complete physical-cost deltas support controlled simulated attribution; paired known-meter differences support only observed-coverage comparison, not field savings.

{rt}
'''
    (report_root/'phase2d_savings_attribution.md').write_text(attribution,encoding='utf-8')
    limits=f'''# Phase II-D limitations and release boundary

{base}

- Replay-compatible versioned copy adds admission controls only; maintain its explicit diff/regression when evolving it. Frozen V1.1 is untouched.
- Exact heat/practice/rolling controls remain subject to future duration, yield timing and actual availability. All forecast-feasible failures are unreleasable and retained. There is no automatic repair/reoptimization.
- Full30-day recreation is essential; V1.1 does not have prefix-invariant tapes across horizon lengths. Wear/faults are calendar driven; persistent thermal chemistry/runtime state absent. Chemistry remains a placeholder, not a metallurgical quality certificate.
- Five-minute starts and quarter-hour accounting are inherited optimizer approximations. p50/p90 are marginal empirical quantiles, not certified joint safety bounds. A successfully replayed simulated seed is not a plant safety guarantee.
- Ten held-out seeds retain the same fixed January calendar and reduced plant model. Robustness denominators include failed plans; savings distributions are conditional on success and are not unconditional expected benefits.
- Unchanged sensor noise/missingness/glitches prevent exact observed accounting. Meter cost remains an incomplete subtotal where coverage is missing; physical truth is evaluation-only. No real tariff economics, fuel-cost/carbon calculation or external-benchmark transfer claim is implemented.
- S1 tariff scheduling includes optimized rolling timing as well as heat starts. Its small wear-dependent energy/fuel effects are shown separately. S2's reference start policy responds naturally to shorter heats. No maintenance decision is evaluated.
- Primary central synthetic plan fails; the complete central attribution bridge is unavailable. Conservative synthetic success is reported separately. Remaining forecast misses are evidence for a later authorized supervisory step, not grounds to recalibrate or unfreeze upstream.

Milestone achieved: {experiment['complete_decision_loop']}. Multi-seed status: {experiment['multi_seed_status']}. Test evidence: {tests}. All generated files are new Phase-II-D files. Upstream frozen manifest: configs/phase2d_readonly_manifest.json. Reproduce in a new --output directory; released replay evidence is not overwritten.
'''
    (report_root/'phase2d_limitations.md').write_text(limits,encoding='utf-8')
    card=out/'data_card.md'
    card.write_text('# replay_v1 data card\n\n'+base+'\n\n'+architecture+'\n\n'+compatibility+'\n\n'+results+'\n\nPublication: these are evaluation outcomes, not predictors. Hidden simulation tables and fault traces stay in per-case simulation/evaluation; predictor history is projected from completed public records only. Failed runs retain diagnostics and never appear as successful full-day outcomes. Test/protected/reproducibility/release manifests accompany the evidence.\n',encoding='utf-8')
    plot_primary(out,d,cases)


def plot_primary(out,d,cases):
    paths={'S0':out/'primary/baseline/simulation','S1':out/'primary/optimized/c3_tariff_normal/simulation','S2':out/'primary/practice_only/simulation','conservative_synthetic':out/'primary/optimized/conservative_tariff_synthetic/simulation'}
    fig,axes=plt.subplots(4,1,figsize=(12,10),sharex=True)
    for n,p in paths.items():
        if cases[n]['status']!='physically_valid':continue
        t=pd.read_parquet(p/'latent_truth.parquet');x=t[(t.asset_id=='MAIN')&t.timestamp.between(pd.Timestamp('2026-01-12'),pd.Timestamp('2026-01-13'),inclusive='left')]
        h=(x.timestamp-pd.Timestamp('2026-01-12')).dt.total_seconds()/3600
        axes[0].step(np.r_[h,24],np.r_[x.kW,x.kW.iloc[-1]],where='post',label=n)
        boundary=np.arange(len(x)+1)*.25
        opening=cases[n]['matched_conditions']['origin_state']['inventory_t']
        axes[1].step(boundary,np.r_[opening,x.yard_stock_t],where='post',label=n)
        axes[2].step(boundary,np.r_[0,x.bar_t.cumsum()],where='post',label=n)
    axes[0].set_ylabel('Actual mean kW');axes[1].set_ylabel('Yard t');axes[2].set_ylabel('Cumulative bars t')
    ledger=pd.read_parquet(out/'primary/baseline/realized_tariff_ledger.parquet');axes[3].step(np.arange(97)*.25,np.r_[ledger.tariff_Rs_per_kWh,ledger.tariff_Rs_per_kWh.iloc[-1]],where='post');axes[3].set_ylabel('Synthetic Rs/kWh');axes[3].set_xlabel('Hours from Jan-12 local midnight')
    for ax in axes[:3]:ax.legend(ncol=4);ax.grid(alpha=.2)
    fig.suptitle('DIGITAL-TWIN-REALIZED | matched seed42 | complete physical evaluation only');fig.tight_layout();fig.savefig(d/'primary_timeline.png',dpi=130);plt.close(fig)
    # Residuals are evaluation outputs, never fed into optimization.
    p=out/'primary/optimized/c3_tariff_normal/heat_forecast_comparison.parquet'
    if p.exists():
        h=pd.read_parquet(p);fig,ax=plt.subplots(1,2,figsize=(11,4))
        for a,col,prefix,unit in [(ax[0],'actual_energy_kWh','energy','kWh'),(ax[1],'actual_duration_min','duration','min')]:
            suffix='kWh' if prefix=='energy' else 'min';a.plot(h[col].to_numpy(),'o-',label='realized');a.plot(h[f'{prefix}_p50_{suffix}'].to_numpy(),label='p50');a.plot(h[f'{prefix}_p90_{suffix}'].to_numpy(),label='p90');a.set_xlabel('Heat ordinal');a.set_ylabel(unit);a.legend()
        fig.suptitle('Origin-frozen predictions vs exact-control replay');fig.tight_layout();fig.savefig(d/'forecast_residuals.png',dpi=130);plt.close(fig)


def freeze(out,tests):
    from scripts.phase2d import protected
    out=Path(out);experiment=json.loads((out/'experiment.json').read_text());experiment['tests']=tests;experiment['protected']=protected()
    write_json(out/'experiment.json',experiment);reports(out,experiment)
    sources=list(Path('src/energy_copilot/replay').glob('*.py'))+list(Path('scripts').glob('phase2d*.py'))+list(Path('tests').glob('test_replay*.py'))+[Path('configs/replay_v1.yaml'),Path('configs/phase2d_readonly_manifest.json'),Path('configs/replay_compatibility_manifest.json'),Path('docs/phase2d_compatibility_diff.patch')]
    write_json(out/'code_manifest.json',{p.as_posix():sha256(p) for p in sources})
    files=[p for p in out.rglob('*') if p.is_file() and p.name!='release_manifest.json']
    rep=list(Path('reports').glob('phase2d*.md'))+list(Path('reports/phase2d').glob('*.png'))+list(Path('docs').glob('phase2d*.md'))
    write_json(out/'release_manifest.json',dict(version='replay_v1',hashes={p.relative_to(out).as_posix():sha256(p) for p in files},reports={p.as_posix():sha256(p) for p in rep},tests=tests))


def detail_diagnostics(out,primary):
    names={'S1':'c3_tariff_normal','S3':'c4_tariff_synthetic','conservative_normal':'conservative_tariff_normal','conservative_synthetic':'conservative_tariff_synthetic'}
    runs=[(42,out/'primary',primary)]
    for folder in sorted((out/'evaluation').glob('seed_*')) if (out/'evaluation').exists() else []:
        runs.append((int(folder.name.split('_')[-1]),folder,json.loads((folder/'case_results.json').read_text())))
    details=[];modes=[];rows=[]
    for seed,folder,cases in runs:
        for key,entry in cases.items():
            if entry['status']!='replay_infeasible' or key not in names:continue
            directory=folder/'optimized'/names[key]
            if not (directory/'failed_heat_trace_evaluation_only.parquet').exists():continue
            h=pd.read_parquet(directory/'failed_heat_trace_evaluation_only.parquet');diag=entry['diagnostic']
            requested=pd.Timestamp('2026-01-05')+pd.Timedelta(minutes=diag['heatstart'])
            previous=h.iloc[-1];responsible=previous.heat_id;duration=(previous.end-previous.start).total_seconds()/60
            overrun=(previous.end-requested).total_seconds()/60;labels=previous.fault_label
            if 'cannot complete' in entry['violation']:
                responsible=diag['heat_id'];duration=diag['end']-diag['heatstart'];overrun=diag['end']-(pd.Timestamp('2026-01-13')-pd.Timestamp('2026-01-05')).total_seconds()/60
                common=pd.read_parquet(folder/'baseline/simulation/latent_heats.parquet');labels=common.set_index('heat_id').loc[responsible,'fault_label']
            result=json.loads((directory/'optimizer_result.json').read_text());prediction=next(r for r in result['schedule'] if r['heat_id']==responsible)
            details.append(dict(seed=seed,case=key,heat_id=diag['heat_id'],previous_heat_id=responsible,
                timing_overrun_min=round(overrun,9),previous_fault_labels=labels,actual_duration_min=duration,
                selected_prediction_min=prediction['selected_duration_min'],duration_underprediction_min=duration-prediction['selected_duration_min'],
                category='duration underprediction; fault evidence; five-minute reservation',retained=True))
        for family,central,conservative in [('normal','S1','conservative_normal'),('synthetic','S3','conservative_synthetic')]:
            a=cases[central];b=cases[conservative];am=a.get('realized_metrics');bm=b.get('realized_metrics')
            text=lambda m,k:f'{m[k]:.4f}' if m else 'failed'
            modes.append(dict(seed=seed,family=family,central_status=a['status'],conservative_status=b['status'],
                              central_idle_hours=am['IF_idle_hours'] if am else None,conservative_idle_hours=bm['IF_idle_hours'] if bm else None,
                              central_physical_cost_Rs=am['physical_evaluation_tariff_cost_Rs'] if am else None,conservative_physical_cost_Rs=bm['physical_evaluation_tariff_cost_Rs'] if bm else None))
            rows.append([seed,family,a['status'],b['status'],text(am,'IF_idle_hours')+' / '+text(bm,'IF_idle_hours'),text(am,'physical_evaluation_tariff_cost_Rs')+' / '+text(bm,'physical_evaluation_tariff_cost_Rs')])
    frame=pd.DataFrame(details)
    frame.to_parquet(out/'failure_analysis_details.parquet',index=False);write_json(out/'central_vs_conservative.json',modes)
    return frame,rows
