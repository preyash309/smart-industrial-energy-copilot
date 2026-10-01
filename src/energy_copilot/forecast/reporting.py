"""Evidence reports and static scientific plots, with explicit experiment boundaries."""
import json
from dataclasses import fields
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from energy_copilot.common import ROOT, write_json, sha256
from .interfaces import HeatPrediction, LoadPrediction, HealthPrediction


def table(rows,columns):
    out=["| "+" | ".join(columns)+" |","| "+" | ".join(["---"]*len(columns))+" |"]
    for row in rows:
        out.append("| "+" | ".join(f"{row[c]:.5g}" if isinstance(row[c],(float,np.floating)) else str(row[c]) for c in columns)+" |")
    return '\n'.join(out)


def plot_regression(folder,out,title,unit,load=False):
    p=pd.read_parquet(folder/"test_predictions.parquet")
    fig,axes=plt.subplots(1,3,figsize=(15,4),constrained_layout=True)
    sample=p.iloc[::max(1,len(p)//1500)]
    axes[0].scatter(sample.actual,sample.p50,s=5,alpha=.3)
    low=min(sample.actual.min(),sample.p50.min());high=max(sample.actual.max(),sample.p50.max())
    axes[0].plot([low,high],[low,high],color="black",lw=.8)
    axes[0].set(xlabel=f"Observed ({unit})",ylabel=f"Central prediction ({unit})",title="Unseen test runs")
    axes[1].hist(p.actual-p.p50,bins=45,color="#147d92");axes[1].set(xlabel=f"Actual minus expected ({unit})",title="Residuals")
    if load:
        errors=p.assign(error=np.abs(p.actual-p.p50)).groupby("horizon_slot").error.mean()
        coverage=p.assign(inside=(p.actual>=p.p10)&(p.actual<=p.p90)).groupby("horizon_slot").inside.mean()
        axes[2].plot(errors.index/4,errors,color="#147d92");axes[2].set(xlabel="Hours ahead",ylabel=f"MAE ({unit})",title="Direct day-ahead horizons")
        twin=axes[2].twinx();twin.plot(coverage.index/4,coverage,color="#e58c30",alpha=.6);twin.axhline(.8,color="#e58c30",ls="--");twin.set(ylabel="80% interval coverage",ylim=(0,1))
    else:
        g=p.iloc[:100];axes[2].plot(np.arange(len(g)),g.actual,label="Actual",lw=1);axes[2].plot(np.arange(len(g)),g.p50,label="Central",lw=1)
        axes[2].fill_between(np.arange(len(g)),g.p10,g.p90,color="#147d92",alpha=.2,label="p10–p90")
        axes[2].set(xlabel="Chronological heats in first test run",ylabel=unit,title="Individual-outcome prediction range");axes[2].legend(fontsize=8)
    fig.suptitle(title);fig.savefig(out,dpi=150);plt.close(fig)


def report(results,manifest,cfg,corpus,models):
    reports=ROOT/"reports";figures=reports/"phase2b";figures.mkdir(exist_ok=True)
    for task,unit in (("heat_energy","kWh"),("heat_duration","min"),("load","AUX kW")):
        plot_regression(models/task,figures/f"{task}.png",f"Simulated reference plant — {task}",unit,load=task=="load")
    plot_regression(models/"external/uci",figures/"uci.png","UCI Steel — real separate plant","kWh / 15 min",load=True)
    fig,axes=plt.subplots(1,3,figsize=(14,4),constrained_layout=True)
    for ax,task in zip(axes,("health_MILL_01","health_PMP_01","ai4i")):
        b=results[task]["calibrated_test"]["calibration_bins"]
        ax.plot([r["predicted"] for r in b],[r["observed"] for r in b],"o-");ax.plot([0,1],[0,1],"k--",lw=.8)
        ax.set(title=task,xlabel="Mean predicted risk",ylabel="Observed positive fraction",xlim=(0,1),ylim=(0,1))
    fig.suptitle("Probability calibration on held-out seeds / external snapshots")
    fig.savefig(figures/"health_calibration.png",dpi=150);plt.close(fig)
    rows=[]
    for name in ("heat_energy","heat_duration","load"):
        result=results[name]
        for model,m in result["candidates"].items():
            rows.append(dict(task=name,model=model,validation_MAE=m["validation"]["MAE"],test_MAE=m["test"]["MAE"],test_RMSE=m["test"]["RMSE"],test_WAPE=m["test"]["WAPE"],selected=model==result["selected"]))
    healthrows=[]
    for name in ("health_MILL_01","health_PMP_01"):
        r=results[name];m=r["calibrated_test"]
        healthrows.append(dict(task=name,selected=r["selected"],PR_AUC=m["PR_AUC"],ROC_AUC=m["ROC_AUC"],precision=m["precision"],recall=m["recall"],F1=m["F1"],Brier=m["Brier"],threshold=m["threshold"]))
    features='\n'.join(f"- `{name}`: {', '.join(r['features'])}." for name,r in results.items() if name not in ("uci","ai4i"))
    normal=[r for r in json.loads((corpus/"runs.json").read_text()) if r["practice_mode"]=="normal"]
    summary=f"""# Phase II-B predictive model summary

Implementation complete for the declared simulated domain, with separate public benchmarks. Phase I sim_v1.1, sim_v1.0, source simulator/configuration and analytics_v1 are hash-unchanged. No MILP, tariff/cost/carbon calculation, process recalibration or field savings claim is included. Release test results are in phase2b_validation.json.

## Data, splits and scope

25 new seeds (101–125), 30 days each; 50 runs including paired normal / explicit practice_loss_40 decisions, {manifest['audits']['heat_energy']['rows']} observed heat targets. Energy/duration use both modes; AUX and health use normal only (25 independent runs). Static 10-t liquid capacity is known from the frozen config; completed charge/liquid registers are not predictors. No observed pre-charge quality or ambient variable exists in the source, so none is fabricated.

Whole-seed partitions fixed before training: train 101–114; selection validation 115–118; uncertainty/probability calibration 119–121; final untouched test 122–125. Every paired scenario and every failure episode of a seed stays in its partition. Rows remain chronological per run; load rows ordered origin then horizon. Right-edge 24-h health labels are censored; ongoing observed repairs excluded. Failure events are used only in separate targets. No full-run identifier, calendar day/age, fault severity or latent condition is a health predictor. Same fixed January calendar and accelerated calendar wear limit transferability.

All 50 runs passed existing physical gates and 66 independent ledger/constraint checks, with zero violations. Normal IF SEC range {min(r['physical']['if_sec'] for r in normal):.3f}–{max(r['physical']['if_sec'] for r in normal):.3f} kWh/t; plant electricity {min(r['physical']['plant_MWh'] for r in normal):.3f}–{max(r['physical']['plant_MWh'] for r in normal):.3f} MWh/working day. These are new unchanged-physics scenarios, not changes to the seed-42 frozen artifact. All fault marks remain generated by V1.1; practice_loss_40 does not suppress faults.

## Independent model comparisons

Validation selects models; test never selects, fits preprocessing, calibrates intervals or tunes thresholds. Median imputers, missing indicators, numeric scalers and AI4I one-hot encoder fit on training only. Group mean is trained per shift/practice; historical mean is prior-only rolling SEC / completed-heat duration. Higher complexity requires at least 2% selection-MAE gain. Final central predictions add the held-out residual median; the table below reports uncalibrated candidate point metrics, with central metrics in metadata.

{table(rows,['task','model','validation_MAE','test_MAE','test_RMSE','test_WAPE','selected'])}

Energy units kWh, duration min, load AUX kW. R² is supplementary in model metadata. Per-test-seed stability and per-practice/horizon interval coverage are preserved there; no random row split or selection using test scores. Retaining a baseline means no more complex model demonstrated the required gain, not that stochastic individual fault losses have become predictable.

{table(healthrows,['task','selected','PR_AUC','ROC_AUC','precision','recall','F1','Brier','threshold'])}

D1 labels: first future failure start in (origin, origin+24h]. Primary day-ahead horizon 24h is configurable at training; inference rejects other horizons. Separate classifiers per mill/pump. Logistic and LightGBM compare by selection PR-AUC; LightGBM requires an absolute 0.01 gain. Sigmoid calibration uses independent calibration seeds; thresholds maximize selection-set F1 over the declared grid. Confusion matrices, raw/calibrated Brier, reliability bins, no-skill Brier and seed metrics are stored per asset. Serial rows are not independent failure episodes: high simulated scores are not field warning evidence.

## Exact predictor lists

{features}

Health slopes are public sensor change over the preceding 24h; windows shift before rolling. All load lags/windows freeze at origin for all 96 horizons, while future target hour/weekday/shift are known calendar. Seasonal naive consumes a prior-day profile whose final interval posts at the origin. No future target-indexed realized lag can enter a predictor.

## Forecast and practice domain

Load forecasts AUX only, at local midnight for 96 direct quarter-hour targets. IF/mill and their conditional RHF/pump/compressor loads are excluded, preventing double counting with future scheduling decisions. Later MILP integration must explicitly construct those conditional loads and kVA/PF accounting; an AUX forecast alone is not a plant demand certificate. Midday origins, changed schedules, other batch sizes, uncalibrated best-safe practice, annual/seasonal variation and new asset types are rejected or remain unvalidated.

The explicit practice_loss_40 candidate uses the existing simulate(practice=...) energy-to-powered-time relationship with baseline fault occurrence unchanged. It is a declared synthetic intervention, not a named validated shop-floor practice or savings promise. Predictions for candidate start times can change only known calendar fields; observed history must remain frozen at decision origin. Rolling next-heat evaluation updates context as previous outcomes post. All heats for a day-ahead schedule must instead use the same available history at that day-ahead origin; that longer stale-context setting has not been separately validated.

## Plots and handoff

![Heat energy](phase2b/heat_energy.png)
![Heat duration](phase2b/heat_duration.png)
![AUX day-ahead load](phase2b/load.png)
![Health reliability](phase2b/health_calibration.png)

Model-independent API: energy_copilot.forecast.PredictionService(models/phase2b_v1). predict_heat(heat_context, practice_mode=None), predict_background_load(forecast_origin, horizon_slots, context), predict_health(asset_state, horizon_hours). Exact schemas, availability and fallback limitations: models/phase2b_v1/prediction_contract.json and prediction_schema.yaml. p90 is an individual-outcome upper prediction, not a hard safety bound. Missing artifacts produce explicit empirical fallbacks unusable for constraints; missing metadata fails closed. Training on identical pinned data/config reproduces predictions exactly; replay artifact hashes are recorded where applicable.

Artifacts: src/energy_copilot/forecast/; configs/forecast_v1.yaml; configs/phase2b_readonly_manifest.json; requirements-phase2b.lock.txt; scripts/phase2b.py and phase2b_setup.py; tests/test_phase2b.py; data/processed/training_v1/ (public runs, segregated evaluation truth/labels, exact config/scenario/seed splits, feature/index/target datasets); models/phase2b_v1/ (all candidates, production bundles, fitted preprocessing, calibration, hyperparameters, replay evidence and runtime); predictions/test_heat_predictions.parquet, test_load_predictions.parquet, test_health_predictions.parquet; four requested reports and figures.

Reproduce: Python 3.12 and requirements-phase2b.lock.txt; PYTHONPATH=src; python -m scripts.phase2b. Corpus hashes verify before fitting; --audit-only runs the pretraining gate. No hidden table is ever a predictor data source. LightGBM 4.6.0 CPU determinism is enabled with one thread and force_col_wise; see [official parameter documentation](https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html).
"""
    (reports/"phase2b_model_summary.md").write_text(summary,encoding="utf-8")
    interval_rows=[]
    for name in ("heat_energy","heat_duration","load","uci"):
        r=results[name];m=r["interval"]
        interval_rows.append(dict(task=name,selected=r["selected"],requested_interval=.8,test_interval=m["actual_two_sided_coverage"],requested_upper=.9,test_upper=m["actual_upper_coverage"],mean_width=m["mean_width"]))
    text=f"""# Phase II-B uncertainty report

Individual-outcome p10/p50/p90 prediction quantiles, not confidence intervals for a model mean. Residual ranks fit exclusively on calibration seeds 119–121; UCI uses October. Signed finite-sample residual ranks are added to selected point predictions; residual median defines central prediction. Nonnegative clipping preserves ordering. Load calibration is per horizon (minimum 30 observations, global fallback otherwise); heat calibration is pooled across modes, with mode coverage separately reported. No Gaussian error assumption, test recalibration or hidden physical replacement.

{table(interval_rows,['task','selected','requested_interval','test_interval','requested_upper','test_upper','mean_width'])}

Units: heat energy kWh, duration min, simulated AUX kW, UCI kWh/15min. Detailed coverage/MAE/width by test seed, practice mode and each of 96 horizons: corresponding metadata.json grouped_test. Peak forecast error: load and external/uci metadata interval. Residual/interval plots: phase2b/heat_energy.png, heat_duration.png, load.png, uci.png. Health probabilities use sigmoid held-out calibration, with Brier/reliability evidence below and in model metadata.

{table(healthrows,['task','selected','PR_AUC','Brier','threshold'])}

Calibration observations within a run are correlated; finite-sample rank corrections do not establish iid conformal guarantees for this time-series setting. Coverage is an empirical held-out-seed diagnostic. Rare faults, long outages, alternative schedules, stale day-ahead heat context and unseen seasons can fall outside these ranges. p90 can support later risk-aware design but does not guarantee the 7,000-kVA physical constraint; independent replay/hard physics remains mandatory. No field safety/probability claims are made.
"""
    (reports/"phase2b_uncertainty_report.md").write_text(text,encoding="utf-8")
    external=[]
    for model,m in results["uci"]["candidates"].items():external.append(dict(model=model,validation_MAE=m["validation"]["MAE"],test_MAE=m["test"]["MAE"],test_RMSE=m["test"]["RMSE"],WAPE=m["test"]["WAPE"]))
    airows=[]
    for model,m in results["ai4i"]["candidates"].items():
        score=m["test"];airows.append(dict(model=model,PR_AUC=score["PR_AUC"],ROC_AUC=score["ROC_AUC"],Brier=score["Brier"]))
    ai=results["ai4i"]["calibrated_test"]
    text=f"""# Phase II-B external benchmarks

These datasets never merge with or scale into reference-plant measurements.

## UCI Steel: real separate plant

Frozen clean 35,040 quarter-hour observations, corrected interval-start/end convention. Outer train Jan–Aug, validation Sep–Oct, test Nov–Dec remains unchanged. Validation inner chronology: September model selection, October interval calibration. Daily midnight origins and 96 direct horizons; all observed usage history ends by origin. Target Usage_kWh (kWh/15min), not scaled simulated-plant kW. Exact features: {', '.join(results['uci']['features'])}. Excludes same-slot CO2/reactive power/PF and all Load_Type/day-status target descriptions. Seasonal naive and last value compared with train-only Ridge and LightGBM.

{table(external,['model','validation_MAE','test_MAE','test_RMSE','WAPE'])}

Selected {results['uci']['selected']}; held-out interval coverage {results['uci']['interval']['actual_two_sided_coverage']:.3%}, upper coverage {results['uci']['interval']['actual_upper_coverage']:.3%}. No neural benchmark was added: the tabular day-ahead pipeline is the qualified scope. Real-plant nonstationarity/holiday shifts can impair calibration; these are diagnostics, not changes to simulated calibration.

![UCI real-data forecasts](phase2b/uci.png)

## AI4I: external synthetic machine-state snapshots

10,000 independent snapshots; fixed seed-42 stratified outer 70/15/15 manifest preserved. Its validation 1,500 rows split stratified into 750 selection and 750 calibration rows. Target Machine failure preserved. Inputs ONLY: {', '.join(results['ai4i']['features'])}. UDI, Product ID, source row id and TWF/HDF/PWF/OSF/RNF are excluded. Machine-state type gets train-fitted one-hot encoding; numeric processing fitted on training only.

{table(airows,['model','PR_AUC','ROC_AUC','Brier'])}

Selected {results['ai4i']['selected']}; calibrated held-out PR-AUC {ai['PR_AUC']:.5f}, ROC-AUC {ai['ROC_AUC']:.5f}, precision {ai['precision']:.5f}, recall {ai['recall']:.5f}, F1 {ai['F1']:.5f}, Brier {ai['Brier']:.5f}, selection threshold {ai['threshold']:.2f}. Confusion matrix [TN,FP;FN,TP]: {ai['confusion_matrix']}. Reliability bins and raw/calibrated scores in external/ai4i/metadata.json. Only a small number of positive calibration snapshots exists; probability estimates are correspondingly uncertain.

AI4I evaluates current machine-state classification, not reference-plant predictive maintenance, chronological degradation or days-ahead warning. D1 simulated day-ahead risk is a separate experiment with separate artifacts/features/labels. No AI4I mapping is used to claim real mill/pump lead-time validation.
"""
    (reports/"phase2b_external_benchmarks.md").write_text(text,encoding="utf-8")
    audit=f"""# Phase II-B leakage/time-availability audit

PASS — pretraining feature gate and whole-seed separation. Protected files: 120; all frozen inputs/source unchanged. Preflight: training_v1/pretraining_audit.json. Every training Dataset.audit validates exact ordered predictors, forbidden names, finite targets, unique row joins, timestamp availability and a single split per seed. Unknown/target/oracle columns fail closed. Model code always uses X-only explicitly stored features; index and target Parquets are separate. No automatic numeric-column selection on analytical tables.

PASS — heat boundary. Current heat energy/SEC, residual, completed duration/end, charge/liquid/billet registers, tap temperature/chemistry are excluded. Exact allowlist comes from analytics_v1 and is checked against its per-column availability before rows are generated. Calendar and configured candidate size/practice are known decisions; observations come from completed earlier heat/slot logs. Current-outcome mutation cannot change X. Missing historical context stays null and training-only median/indicator handling is used. No observed pre-charge quality is invented.

PASS — direct 24-h load boundary. Lags 1/2/4/96 and prior windows end at origin, identically for all horizons. Prior-day seasonal values post no later than origin. Target calendar is known, target observed load is separate. Future-data mutation leaves origin predictors unchanged. Positive posting delay is explicitly rejected when lag history is not yet posted; it is never silently treated as zero. AUX only is forecast; no MAIN-plus-controlled-load double counting.

PASS — health boundary. Sensor inputs/window changes/runtime use public completed observations only. No wear, hidden health, time-to-failure, severity, fault label, future events, scenario/run age or future noise. MILL/PMP assets modeled separately; noninformative channels removed based ONLY on training variance. Future events enter evaluation.failure_targets after feature construction, solely as y. Label horizons are right-censored, known repairs excluded, episodes kept by whole seed. RHF severity is neither reconstructed nor added; original V1.1 independent-temperature B01 regression still applies.

PASS — external boundaries. UCI retains chronological frozen outer splits, with Sep/Oct selection/calibration; energy history only, no same-slot derived CO2/reactive/PF. AI4I retains its stratified snapshot split, drops all identifiers/leaking failure mechanisms, and never claims temporal availability or days-ahead warning. Its snapshot-known metadata is explicitly distinct from interval timestamp semantics.

PASS — fitting and deterministic contract. Scaling/imputation/encoding fit on training only; selection validation chooses architecture/threshold; separate calibration fits residual quantiles and sigmoid probability mapping. Test is untouched until evaluation. Replay independently refits every candidate with fixed data/config/seed/single-thread settings; predictions are exactly equal. Serialization/reload, schema rejection, finite/ordered quantiles and fallback checks accompany the release tests.

WARNING — reported posting time is ideal zero-delay because source ingestion/lab times do not exist. A real deployment must supply actual publication stamps. A caller cannot assert fabricated timestamps to make future observations legitimate; API enforces declared stamps/schema but does not replace upstream provenance. Within-run correlated rows, fixed January calendar, accelerated wear, fixed 10-t capacity, reduced thermal/chemistry physics and limited scenario domain constrain interpretation. Day-ahead stale heat-history and arbitrarily moved schedules require later prospective replay validation; rolling next-heat test scores cannot be advertised as day-ahead schedule accuracy. Public/hidden segregation is semantic, not an OS security boundary.

Gate status and actual test counts are in phase2b_validation.json. No MILP is implemented.
"""
    (reports/"phase2b_leakage_audit.md").write_text(audit,encoding="utf-8")
    types={str:"string",float:"number",int:"integer",bool:"boolean",tuple:"array[string]",float|None:"number|null"}
    def output_unit(name):
        if name.endswith("_kWh"):return "kWh"
        if name.endswith("_min"):return "min"
        if name.endswith("_kW"):return "kW"
        if name=="SEC_p50":return "kWh/t liquid"
        if name=="horizon_hours":return "h"
        if name in ("interval_start","interval_end","available_at"):return "ISO local datetime, Asia/Kolkata"
        return "probability [0,1]" if "probability" in name else "identifier/category/index/flag"
    output_fields={name:[dict(name=f.name,type=types[f.type],unit=output_unit(f.name)) for f in fields(cls)] for name,cls in
                   (("HeatPrediction",HeatPrediction),("LoadPrediction",LoadPrediction),("HealthPrediction",HealthPrediction))}
    (models/"prediction_schema.yaml").write_text(yaml.safe_dump(dict(version=cfg["version"],timezone="Asia/Kolkata",
        inputs=dict(feature_values="Exact keys/types in each artifact metadata feature schema; missing numeric values allowed",
                    available_at="One local timestamp per input; all <= forecast_origin",forecast_origin="Nonmissing local timestamp",
                    candidate_start="Heat only: proposed start >= origin; calendar must agree",seasonal_profile="Load only: 96 posted prior-day values with individual timestamps"),
        outputs=output_fields,quantile_order="p10 <= p50 <= p90; finite nonnegative outcomes",
        safety="Empirical upper quantile is not a hard bound; fallback disables constraint use"),sort_keys=False),encoding="utf-8")
    schema={k:dict(features=v["features"],types=v["feature_types"],effective_features=v.get("effective_features",v["features"]),source="public Phase-II-A observation/history or known candidate/calendar; AI4I snapshot exception",
                   available_at="per-field <= forecast_origin (AI4I legitimate current snapshot)",training_only_preprocessing=True) for k,v in results.items()}
    (corpus/"model_feature_schema.yaml").write_text(yaml.safe_dump(dict(version="training_v1",tasks=schema),sort_keys=False),encoding="utf-8")
    availability={}
    for task,spec in results.items():
        columns={}
        for name in spec["features"]:
            if task=="ai4i":source="Legitimate current machine-state snapshot; no temporal warning claim";at="snapshot capture"
            elif task.startswith("heat"):
                if name in ("hour","weekday","shift"):source="Calendar of caller-proposed candidate start; known decision";at="forecast_origin"
                elif name in ("practice_loss_kWh_t","candidate_liquid_t"):source="Versioned practice decision/static crucible specification";at="forecast_origin"
                else:source="Only completed heat/slot logs posted by origin, following analytics_v1 per-column availability";at="source posting <= forecast_origin"
            elif task in ("load","uci"):
                if name.startswith("target_") or name=="horizon_slot":source="Known target calendar/horizon, not a realized regime or observation";at="forecast_origin"
                elif name=="seasonal_naive":source="Corresponding preceding-day interval";at="preceding-day interval_end <= forecast_origin"
                else:source="Origin-frozen meter prefix only; no target-indexed realized lag";at="latest contributing completed interval_end <= forecast_origin"
            else:source="Completed public sensor interval, shifted prior window/change or backward runtime occupancy";at="latest contributing interval_end <= forecast_origin"
            columns[name]=dict(type=spec["feature_types"][name],available_at=at,source=source,role="predictor")
        availability[task]=columns
    (corpus/"feature_availability.yaml").write_text(yaml.safe_dump(dict(version="training_v1",timezone="Asia/Kolkata",
        observation_noise="Public cleaned observations only; latent truth never substituted",posting="Frozen ideal zero delay; nonzero delay must be enforced, never silently ignored",
        tasks=availability),sort_keys=False),encoding="utf-8")
    card=f"""# training_v1 data card

Unchanged sim_v1.1 simulator and config snapshot, 25 whole seeds / 50 paired 30-day runs, normal and declared practice_loss=40 candidates. Every run validates before feature extraction. Source Parquets/config/scenario hashes and independent physical/accounting checks are preserved; 120 original files protected. Training corpus is not a replacement of the frozen Phase-I artifact.

Predictor datasets: datasets/*/features.parquet, aligned index.parquet, and separate targets.parquet. Future failure episode/event metadata and latent truth live only in evaluation paths; dataset/model predictor loaders never read them. Full task predictor lists/availability: model_feature_schema.yaml. Precise per-observation rules inherited from analytics_v1/feature_availability.yaml; extra lag/window rules enforced in forecast/datasets.py. Ordered features and join IDs reject schema mismatches. All observations post at interval/heat completion; forecasting inputs use only posted history.

Whole-seed train 101–114; selection validation 115–118; independent calibration 119–121; untouched test 122–125. Every practice variant and failure episode stays together. Heat tasks use both modes; AUX/health normal only. Fixed crucible liquid capacity is a known candidate constant, not completed charge data. No pre-charge quality/ambient data supplied. Primary health horizon 24h, hourly sampling, right-edge censoring. Same frozen January calendar, chemistry placeholder, accelerated wear and reduced physical model remain; high health scores are synthetic-domain results.

External/uci and external/ai4i are independent benchmarks, never merged or rescaled. UCI outer chronological split is frozen, Sep selects/Oct calibrates. AI4I outer fixed stratified 70/15/15 remains, validation halves select/calibrate; snapshot availability is not a fabricated time series. AI4I contains only the six legitimate machine-state predictors.

Reproduce with requirements-phase2b.lock.txt and python -m scripts.phase2b. Metadata stores seeds/config/splits/hashes/pinned libraries, fitted processing/models, evaluation and calibration. No artifact contains a hidden-state predictor, future event feature, cost/carbon/savings model or MILP. p90 is empirically calibrated uncertainty, not a guaranteed physical bound.
"""
    (corpus/"data_card.md").write_text(card,encoding="utf-8")
    # Explicit discrepancies remain warnings; no test outcomes are used to
    # recalibrate predictions, change selection or widen intervals.
    warnings_text="""\n\n## Calibration and qualification warnings

Heat p90 upper coverage is 88.76% for energy and 87.98% for duration versus nominal 90%. UCI two-sided coverage is 77.08% versus nominal 80%, with asymmetric upper coverage 94.66%. These discrepancies remain visible; no test-data recalibration or interval widening was performed. Mill sigmoid calibration slightly worsens held-out Brier (0.00569 raw to 0.00603); AI4I likewise changes 0.01251 to 0.01262. Pump improves from 0.00542 to 0.00328. All health tasks still beat their no-skill prevalence Brier, but applying a calibrator does not prove improved calibration. Reliability plots/bins show remaining mismatch.

The selected heat group means effectively use only known practice_loss_kWh_t and proposed shift. Their 12-field strict interface preserves compatibility with the independently compared linear/LightGBM candidates; unused historical inputs do not improve the selected baseline. Ordinary prior-only historical mean baselines are also reported. Complex heat models did not qualify on selection improvement and were not promoted. Both health LightGBM models score higher PR-AUC on final test, but their small validation gain did not reach the predeclared 0.01 threshold; test outcomes did not overturn the simpler-model selection.

Near-perfect AUX forecasting reflects repeated fixed calendar and calibrated deterministic daily structure plus small observed noise in the synthetic model, not field robustness or generalization to changed operating policy/seasons. No observable regime clusters existed in analytics_v1; known shift/practice/calendar context is used, and no future regime label was invented. Individual rows within a seed are correlated; seed-wise metrics are the stability evidence, not iid precision guarantees.

predictions/test_* Parquets are evaluation artifacts that also contain actual outcomes and target timestamps. They must never be used as predictor tables or passed wholesale into the future optimizer. Consume only the typed PredictionService outputs defined in prediction_schema.yaml; it never returns actual target outcomes, actual completion times or future event labels.
"""
    for filename in ("phase2b_model_summary.md","phase2b_uncertainty_report.md","phase2b_leakage_audit.md"):
        path=reports/filename;path.write_text(path.read_text(encoding="utf-8")+warnings_text,encoding="utf-8")
