"""Transparent report card: hard physical gates and cross-plant diagnostics."""
import importlib.metadata
import platform
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from energy_copilot.common import ROOT, values, write_json, sha256
from energy_copilot.data.prepare import temporal_stats


TEMPORAL_NOTE="Lag-4 autocorrelation is outside the declared cross-plant diagnostic envelope. A dominant single IF alternates 78 powered and 27 non-powered minutes (approximately seven slots per cycle); four-slot separation therefore often crosses charging breaks. UCI aggregates a different coils/plates plant with smoother load. Preserve the physical cycle rather than add fictitious power or fit held-out data. This discrepancy limits transfer of forecasting results; physical feasibility remains independently tested."


def compare_temporal(result):
    cal=values(yaml.safe_load((ROOT / "configs/calibration_v1.yaml").read_text(encoding="utf-8")))
    truth=result.latent_truth
    site=truth[truth.asset_id.eq("MAIN")].rename(columns={"kWh":"Usage_kWh"})
    sim=temporal_stats(site)
    c=values(result.config);a=c["acceptance"]
    rmse=float(np.sqrt(np.mean((np.array(sim["daily_profile"])-np.array(cal["daily_profile"]))**2)))
    ratio=sim["ramp_sd"]/cal["ramp_sd"]
    diagnostics={"profile_rmse":dict(value=rmse,envelope=a["profile_rmse"],in_envelope=rmse<=a["profile_rmse"]),
                 "lag_1_difference":dict(value=abs(sim["lag_1"]-cal["lag_1"]),envelope=a["acf_absolute"],in_envelope=abs(sim["lag_1"]-cal["lag_1"])<=a["acf_absolute"]),
                 "lag_4_difference":dict(value=abs(sim["lag_4"]-cal["lag_4"]),envelope=a["acf_absolute"],in_envelope=abs(sim["lag_4"]-cal["lag_4"])<=a["acf_absolute"]),
                 "ramp_sd_ratio":dict(value=ratio,envelope=a["ramp_ratio"],in_envelope=a["ramp_ratio"][0]<=ratio<=a["ramp_ratio"][1])}
    comparison=dict(simulated=sim,uci_training=cal,diagnostics=diagnostics,scope="training-only UCI; simulator true MAIN; unitless normalization",
                    interpretation=TEMPORAL_NOTE,decision="Physical acceptance is mandatory; UCI similarity is diagnostic, not a plant identity constraint. No post-hoc parameter fitting.")
    write_json(ROOT / "reports/temporal_validation.json",comparison)
    fig,ax=plt.subplots(figsize=(10,4))
    ax.plot(np.arange(96)/4,cal["daily_profile"],label="UCI Jan-Aug, real Korean plant")
    ax.plot(np.arange(96)/4,sim["daily_profile"],label="Simulated reference plant")
    ax.set(xlabel="Local hour",ylabel="Load / each dataset mean",title="Normalized daily behaviour: different processes, shared clock")
    ax.legend(fontsize=9);fig.tight_layout()
    fig.savefig(ROOT / "reports/figures/sim_uci_profile.png",dpi=160);plt.close(fig)
    return comparison


def report(result, comparison, reproducibility):
    s=result.summary
    checks="\n".join(f"| {name} | PASS |" for name,passed in s["checks"].items())
    cal=comparison["uci_training"];sim=comparison["simulated"]
    diagnostics="\n".join(f"| {name} | {row['value']:.4f} | {row['envelope']} | {'within' if row['in_envelope'] else 'OUTSIDE - documented'} |" for name,row in comparison["diagnostics"].items())
    text=f"""# Phase-I simulator report card

**Physical and baseline gates: PASS. Same-seed replay: PASS. Temporal similarity: partial; lag-4 divergence explicitly retained.** This is a simulated reference plant, not validated field performance. No predictive model, optimiser, dashboard or savings claim is implemented.

Seed {s['seed']}; {s['days']} calendar days, {s['working_days']} working days, {s['heats']} completed heats. Sundays are off. All daily energy and coal baseline targets below refer to working days; calendar mean electricity is {s['mean_calendar_day_MWh']:.3f} MWh/day.

| Baseline metric | Result | Required envelope |
|---|---:|---|
| IF SEC, true energy / tapped liquid | {s['mean_if_sec_kWh_t']:.3f} kWh/t | 640-660 |
| Heats / working day | {s['heats_per_working_day']:.1f} | 12-13 |
| Electricity / working day | {s['mean_working_day_MWh']:.3f} MWh | 96.9-107.1 |
| IF electricity share | {s['if_working_day_share']:.2%} | 75-85% |
| Coal / working day | {s['mean_coal_t_working_day']:.3f} t | 7-9 t; spec approximately 7.7 |
| Billets / working day | {s['mean_billet_t_working_day']:.2f} t | 123.5 configured; spec approximately 120 |
| Bars / working day | {s['mean_bar_t_working_day']:.2f} t | 118.56 configured; spec approximately 115 |
| Worst subslot demand | {s['peak_kVA']:.2f} kVA | <=7000 |
| Yard inventory | {s['min_yard_t']:.2f}-{s['max_yard_t']:.2f} t | 0-200 |
| Max incomer/branch balance error | {s['electrical_balance_max_error_kWh']:.3g} kWh | <=1e-8 |

## Physical gates

| Check | Status |
|---|---|
{checks}

Electricity bookkeeping uses actual powered intervals; MAIN apparent demand is the vector sum of active/reactive power. Peak demand also checks conservative full-power concurrency within each slot. Casting is a zero-delay reduced-order transfer; rolling consumes opening stock before same-slot taps. Fuel ledger is coal mass times NCV, apportioned into the sourced baseline fuel requirement, added fouling loss and holding loss in internal truth. The baseline SEC includes process losses; this bookkeeping does not validate furnace wall/zone thermodynamics.

## Temporal comparison, not a fit target

| Diagnostic | Value | Predeclared envelope | Assessment |
|---|---:|---|---|
{diagnostics}

UCI lag-1/lag-4: {cal['lag_1']:.3f}/{cal['lag_4']:.3f}; simulator: {sim['lag_1']:.3f}/{sim['lag_4']:.3f}. Normalized ramp SD: UCI {cal['ramp_sd']:.3f}, simulated {sim['ramp_sd']:.3f}. Weekend/weekday mean: UCI {cal['weekend_weekday_ratio']:.3f}, simulated {sim['weekend_weekday_ratio']:.3f}; Saturday works and Sunday is off. Ramp quantiles and complete profiles are in temporal_validation.json.

{TEMPORAL_NOTE}

The default absolute ACF diagnostic tolerance was not widened after comparison. Profile/ramp similarities do not establish public-dataset model accuracy. UCI process CV is not sensor accuracy; instrument errors and missingness are separately labelled assumptions.

## Fault and measurement audit

Physical mechanism tests separately force each IF fault and check energy, duration and superheat temperature changes. Wear crosses a physical threshold before a failure/repair event, changes vibration/temperature and pump flow, and resets after replacement. Calendar-age degradation is an accelerated demonstration assumption: roughly two-week cycles imply far more than the workflow's 3-4 annual failures; no reliability or warning-lead-time claim is made. No IMS dataset was acquired or fitted.

Fault counts: {s['event_counts']}. Bernoulli occurrence counts are checked against a three-standard-deviation finite-sample envelope, rather than an unrealistic +/-10% count gate for a rare fault over 30 days. Fault loss magnitudes come from the supplied spec; occurrence probabilities, repair duration and transfer to this plant require pilot confirmation.

Meter errors, glitches and gaps are applied after physical truth. Heat kWh/t is a noisy observed heat-counter value; baseline gates use latent heat energy. Observed branch and MAIN meters need not sum exactly. Internal latent truth, latent heat components, fault labels, events and future failure information are denied to the feature loader.

Same-seed output verification: {reproducibility}. Acceptance tests include corrupted-ledger rejection, infeasible schedule rejection, future-scenario replay, observation isolation, wear/repair coupling, frozen schemas, raw hashes and split separation.

## Scope and limitations

Chemistry is an unmodelled operator-register placeholder (chem_ok=True), not a metallurgy prediction. Tap window, 98% melt yield, pump flow/limits, compressor pressure, RHF electrical/holding loads, wear curves and quick repairs are explicitly assumed. RHF temperature is controlled at 1200 C; richer thermal dynamics require measured coefficients. The 30-day export is a feasibility demonstration; annual operation and field savings remain outside Phase I.
"""
    (ROOT / "reports/sim_report_card.md").write_text(text,encoding="utf-8")
    write_json(ROOT / "reports/validation_report.json",dict(physical_checks=s["checks"],reproducibility=reproducibility,temporal_diagnostics=comparison["diagnostics"],temporal_note=TEMPORAL_NOTE,scope="Phase I"))
    return text


def assumption_register():
    cfg=yaml.safe_load((ROOT / "configs/plant_v1.yaml").read_text(encoding="utf-8"))
    rows=[]
    def walk(node,path=""):
        if isinstance(node,dict):
            if "value" in node:
                rows.append(f"| {path} | {node['value']} | {node['unit']} | {node['status']} | {node['source']} | {node['notes']} |")
            else:
                for k,v in node.items():
                    walk(v,f"{path}.{k}".strip("."))
    walk(cfg)
    prefix="""# Phase-I assumption register

Read all four supplied PDFs before implementation: Smart_Industrial_Energy_Copilot_Roadmap.pdf, Reference_Plant_Spec_v2.pdf, Data_Workflow (1).pdf and Challenge04_Simple_Workflow.pdf. The current user's Phase-I scope overrides later-stage models/optimisation/savings work in those PDFs. The spec's cited benchmarks are secondary sources; they are not independent measurements at this proposed plant.

## Reconciliation and feasibility

- IF energy: 10 t tapped liquid * 650 kWh/t = 6500 kWh. Rated 5000 kW gives 1.3 h = 78 powered minutes. Approximate 105-minute cycle minus 78 gives 27 minutes charging/tapping/non-powered work. Discard the conflicting ~90-minute power-on approximation. Changes in energy change powered duration through energy/power; non-powered time stays independent. Partial half-power malfunction lasts an assumed 20 powered minutes, adding 10 minutes versus delivering that portion at rated power, plus its specified heat loss. Fault periods are explicit exceptions to ordinary full-power operation.
- Ten tonnes denotes crucible/tapped liquid, not gross charge: assumed 98% melt yield gives 10/0.98 = 10.2041 t charge; 0.2041 t melt loss. Liquid-to-billet yield is 95%, rolling yield 96%; losses are explicit mass sinks.
- Thirteen 10 t heats give 130 t liquid, 123.5 t billets and 118.56 t bars. These are close to, but above, the spec's approximate 125/120/115 figures. They avoid an impossible half heat while retaining 12-13 heats/day. Baseline nominal IF energy is 84.5 MWh/working day versus approximate 81.3 in the spec.
- Fifteen hours at 8 t/h handles only 120 t billets. Use a disclosed 16 h rolling window, capacity 128 t, to meet 123.5 t plus short repair interruptions. Fifty tonnes of opening stock bridges the timing mismatch before late furnace taps. The initial 30 t trial failed throughput; stopped and corrected before extending the run. Maximum yard remains 200 t.
- RHF blower/pusher power is missing from the spec's daily electricity breakdown. Explicitly add an assumed 40 kW during the rolling window rather than silently omit feeder M4. MAIN is not a seventh consuming asset; it aggregates six consuming branches. Caster mechanics belong to AUX electricity and a separate mass-transfer stage.
- Electrical PF uses compensated per-feeder assumptions, not the very different UCI whole-plant PF. Sum complex powers for MAIN kVA and test full-power subslot concurrency against 7000 kVA; do not divide all loads by an invented universal PF.
- Quick 15-30-minute replacement of worn parts is assumed with spare parts. Wear ramps over about two weeks, giving accelerated failure cycles in the demonstration, not 3-4 annual failures. Repair assumptions materially limit production conclusions.

## Evidence and data boundaries

The UCI midnight-row convention is inferred from every day's source order; retain original timestamps and use corrected interval starts. Calibration only uses Jan-Aug. Full-year EDA includes held-out descriptive observations and does not fit parameters. UCI dimensions transfer normalized rhythm to AUX only; absolute consumption and public PF do not set reference plant size. Process fluctuations do not identify meter accuracy. AI4I is synthetic and never row-merged with plant data.

Punjab is the selected tariff jurisdiction and kVAh the billing basis. The current official FY2026-27 tariff was inspected at https://docs.pspcl.in/docs/cecommercial2620260310162642809.pdf ; the supplied workflow's seasonal peak/night clock bands are used for an energy view only. No billing rate, fuel price, emissions total, payback or savings claim is implemented; applicable rates/customer class need a later explicit pricing stage.

Detailed chemistry, measured pump curves, RHF transient coefficients, holidays and real ambient data are absent. They remain disclosed reduced-order assumptions or unimplemented details. No latent health/fault severity/future failure timestamps may become downstream features.

## Complete plant parameter register

| Parameter | Value | Unit | Status | Source | Notes |
|---|---|---|---|---|---|
"""
    (ROOT / "reports/assumption_register.md").write_text(prefix+"\n".join(rows)+"\n",encoding="utf-8")


def runtime_manifest():
    requirements=(ROOT / "requirements.lock.txt").read_text().splitlines()
    return dict(python=platform.python_version(),platform=platform.system(),dependencies={line.split("==")[0]:importlib.metadata.version(line.split("==")[0]) for line in requirements if "==" in line})
