"""Fail-closed public-data preparation. No fitted predictive models."""
from __future__ import annotations
import shutil
import stat
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
import yaml

from energy_copilot.common import ROOT, sha256, write_json, parameter, values, load_config

STEEL = "Steel_industry_data.csv"
AI4I = "ai4i2020.csv"
FORBIDDEN = ["TWF", "HDF", "PWF", "OSF", "RNF", "UDI", "Product ID"]
FEATURES = ["Type", "Air temperature [K]", "Process temperature [K]", "Rotational speed [rpm]", "Torque [Nm]", "Tool wear [min]"]


def acquire():
    dest = ROOT / "data/raw"
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, url in [(STEEL,"https://archive.ics.uci.edu/dataset/851/steel+industry+energy+consumption"),
                      (AI4I,"https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset")]:
        src, target = ROOT / "Datasets" / name, dest / name
        source_hash = sha256(src)
        if target.exists():
            if sha256(target) != source_hash:
                raise ValueError(f"Immutable raw data mismatch: {target}")
        else:
            shutil.copyfile(src, target)
            target.chmod(stat.S_IREAD)
        manifest[name] = dict(sha256=source_hash, bytes=src.stat().st_size, input_path=f"Datasets/{name}",
                              raw_path=f"data/raw/{name}", source=url, licence="CC BY 4.0 per supplied Data Workflow D1",
                              nature="real Korean steel plant" if name==STEEL else "synthetic machine snapshots")
    old = dest / "source_hashes.json"
    if old.exists():
        import json
        if json.loads(old.read_text()) != manifest:
            raise ValueError("Source provenance changed; create a new data version")
    write_json(old, manifest)
    return manifest


def temporal_stats(frame, energy="Usage_kWh"):
    x = frame[energy].astype(float)
    ts = pd.to_datetime(frame["timestamp"])
    slot = ts.dt.hour * 4 + ts.dt.minute // 15
    profile = x.groupby(slot).mean().reindex(range(96)).fillna(x.mean()) / x.mean()
    weekend = ts.dt.dayofweek >= 5
    weekday_profile = x[~weekend].groupby(slot[~weekend]).mean().reindex(range(96)).fillna(x.mean()) / x[~weekend].mean()
    weekend_profile = x[weekend].groupby(slot[weekend]).mean().reindex(range(96)).fillna(x.mean()) / x[weekend].mean()
    ramps = x.diff().dropna() / x.mean()
    # Within contiguous low-ramp runs; pooling different operating levels inflates CV.
    stable = x.diff().abs() < x.mean() * 0.05
    groups=(~stable).cumsum()
    run_cvs=[]
    for _,run in x[stable].groupby(groups[stable]):
        if len(run)>=4 and run.mean()>0:
            run_cvs.append(float(run.std()/run.mean()))
    return dict(daily_profile=profile.tolist(), weekday_profile=weekday_profile.tolist(), weekend_profile=weekend_profile.tolist(),
                weekend_weekday_ratio=float(x[weekend].mean()/x[~weekend].mean()),
                lag_1=float(x.autocorr(1)), lag_4=float(x.autocorr(4)),
                ramp_quantiles=ramps.quantile([0.01,0.1,0.5,0.9,0.99]).tolist(), ramp_sd=float(ramps.std()),
                steady_process_cv=float(np.median(run_cvs)) if run_cvs else 0.,
                consecutive_repeat_fraction=float(x.diff().eq(0).mean()))


def tariff_bands(ts, config):
    ts = pd.Series(pd.to_datetime(ts))
    h = ts.dt.hour
    mmdd = ts.dt.strftime("%m-%d")
    season = mmdd.between(config["peak_season_start"],config["peak_season_end"])
    return np.where((h >= config["night_start"]) | (h < config["night_end"]), "night",
                    np.where(season & (h>=config["peak_start"]) & (h<config["peak_end"]),"peak","normal"))


def prepare_steel(config, manifest):
    raw = pd.read_csv(ROOT / "data/raw" / STEEL)
    df = raw.copy()
    df.insert(0,"source_row_id",np.arange(len(df)))
    ts = pd.to_datetime(df["date"], format="%d/%m/%Y %H:%M", dayfirst=True, errors="raise")
    nsm = ts.dt.hour * 3600 + ts.dt.minute * 60
    if not (nsm == df["NSM"]).all():
        raise ValueError("Steel NSM disagrees with original timestamp")
    # Verify the source's midnight-at-end convention BEFORE correcting it.
    midnight = ts.dt.hour.eq(0) & ts.dt.minute.eq(0)
    previous = ts.shift(1)
    convention = midnight & previous.dt.hour.eq(23) & previous.dt.minute.eq(45) & ts.dt.date.eq(previous.dt.date)
    if not midnight.equals(convention):
        raise ValueError("Ambiguous midnight convention; manual review required")
    ends = ts + pd.to_timedelta(midnight.astype(int),unit="D")
    starts = ends - pd.Timedelta(minutes=15)
    if ends.duplicated().any() or not ends.is_monotonic_increasing or not ends.diff().dropna().eq(pd.Timedelta(minutes=15)).all():
        raise ValueError("Steel coverage/duplicate gate failed")
    missing = raw.isna().sum().to_dict()
    if sum(missing.values()):
        raise ValueError("Missing source data requires explicit cleaning policy")
    numeric = raw.select_dtypes("number")
    nonnegative = [c for c in numeric if c!="NSM"]
    if (numeric[nonnegative] < 0).any().any():
        raise ValueError("Negative energy/PF values")
    pfcols = [c for c in raw if "Power_Factor" in c]
    if not raw[pfcols].apply(lambda x:x.between(0,100)).all().all():
        raise ValueError("Invalid source PF")
    if not ends.iloc[-1] - starts.iloc[0] == pd.Timedelta(days=365):
        raise ValueError("Expected non-leap full year")
    df["source_timestamp"] = ts
    df["timestamp"] = starts
    df["interval_end"] = ends
    df["weekday"] = starts.dt.dayofweek
    df["weekend"] = starts.dt.dayofweek >= 5
    df["lagging_pf"] = df[pfcols[0]] / 100
    df["leading_pf"] = df[pfcols[1]] / 100
    df["tariff_band"] = tariff_bands(starts,config["tariff"])
    out = ROOT / "data/interim"
    out.mkdir(parents=True,exist_ok=True)
    df.to_parquet(out / "uci_steel_clean.parquet",index=False)
    audit = dict(rows=len(df), raw_timestamp_backward_jumps=int((ts.diff()<pd.Timedelta(0)).sum()),
                 midnight_rows_shifted=int(midnight.sum()),duplicate_rows=int(raw.duplicated().sum()),
                 duplicate_timestamps=int(ends.duplicated().sum()),gap_count=int((ends.diff().dropna()!=pd.Timedelta(minutes=15)).sum()),
                 missing_by_column=missing, ranges={c:dict(min=float(numeric[c].min()),max=float(numeric[c].max())) for c in numeric},
                 start=str(starts.iloc[0]),end_exclusive=str(ends.iloc[-1]), nsm_mismatches=0,
                 consecutive_repeats=int(df["Usage_kWh"].diff().eq(0).sum()),
                 source_hash=manifest[STEEL]["sha256"],lagging_pf_below_09=float(df.lagging_pf.lt(.9).mean()),
                 leading_pf_below_09=float(df.leading_pf.lt(.9).mean()))
    split = pd.DataFrame(dict(source_row_id=df.source_row_id,timestamp=starts,
                             split=np.where(starts.dt.month<=8,"train",np.where(starts.dt.month<=10,"validation","test"))))
    split.to_parquet(out / "uci_steel_split_manifest.parquet",index=False)
    write_json(out / "uci_steel_split_manifest.json",dict(source_sha256=audit["source_hash"],timestamp_basis="interval_start",
               manifest_sha256=sha256(out / "uci_steel_split_manifest.parquet"),rows=split.groupby("split").size().to_dict(),
               windows={"train":"2018-01-01 through 2018-08-31", "validation":"2018-09-01 through 2018-10-31","test":"2018-11-01 through 2018-12-31"}))
    write_json(ROOT / "reports/uci_steel_audit.json",audit)
    # Freeze training-only behavioural calibration. Held-out months never set parameters.
    train = df[starts.dt.month<=8]
    stats = temporal_stats(train)
    cal = {"version":"calibration_v1", "source_sha256":audit["source_hash"], "fit_window":"Jan-Aug 2018 only",
           "normalization":"kWh divided by training mean; per-day-type profiles divided by that type mean"}
    for key,value in stats.items():
        cal[key]=parameter(value,"normalized load" if "profile" in key else "dimensionless","derived",
                           "UCI Steel, Jan-Aug training partition",f"Computed by temporal_stats: {key}; no absolute plant-size transfer.")
    for prefix,col in [("lagging_pf","lagging_pf"),("leading_pf","leading_pf")]:
        for name,q in [("median",.5),("p10",.1)]:
            cal[f"{prefix}_{name}"]=parameter(float(train[col].quantile(q)),"dimensionless","derived",
                                             "UCI Steel training PF divided by 100",f"{name} quantile; not assumed per-asset PF.")
    cal["missing_fraction"] = parameter(0.0,"fraction","derived","UCI Steel source audit","No missing values; simulated 0.5% is a stress-test assumption.")
    cal["gap_fraction"] = parameter(0.0,"fraction","derived","UCI Steel corrected interval audit","No gaps after midnight convention correction.")
    (ROOT / "configs/calibration_v1.yaml").write_text(yaml.safe_dump(cal,sort_keys=False),encoding="utf-8")
    plot_dir = ROOT / "reports/figures"
    plot_dir.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({"figure.figsize":(10,4),"axes.spines.top":False,"axes.spines.right":False})
    allstats=temporal_stats(df)
    fig,ax=plt.subplots()
    for key,label in [("weekday_profile","Weekday"),("weekend_profile","Weekend")]:
        ax.plot(np.arange(96)/4,allstats[key],label=label)
    ax.set(xlabel="Hour (interval start)",ylabel="Mean load / day-type mean",title="UCI Steel: normalized weekday/weekend profile")
    ax.legend();fig.tight_layout();fig.savefig(plot_dir / "uci_daily_profile.png",dpi=160);plt.close(fig)
    totals=df.groupby("tariff_band").Usage_kWh.sum().reindex(["night","normal","peak"])
    fig,ax=plt.subplots();totals.div(1000).plot.bar(ax=ax,color=["#326b96","#58a282","#d99554"],rot=0)
    ax.set(ylabel="Observed electricity (MWh)",title="UCI Steel energy classified by Punjab ToD clock bands")
    ax.text(.01,.98,"Band illustration only; Korean consumption is not an Indian bill",transform=ax.transAxes,va="top",fontsize=9)
    fig.tight_layout();fig.savefig(plot_dir / "uci_tariff_energy.png",dpi=160);plt.close(fig)
    fig,ax=plt.subplots()
    for col,label in [("lagging_pf","Lagging PF"),("leading_pf","Leading PF")]:
        ax.hist(df[col],bins=40,alpha=.55,label=label,density=True)
    ax.axvline(.9,color="black",ls="--",lw=1);ax.set(xlabel="Power factor (fraction)",ylabel="Density",title="UCI Steel power factor distribution")
    ax.legend();fig.tight_layout();fig.savefig(plot_dir / "uci_pf_distribution.png",dpi=160);plt.close(fig)
    fig,ax=plt.subplots();ax.plot(df.timestamp,df.Usage_kWh,lw=.4)
    ax.set(ylabel="kWh / 15 min",title="Full-year source inspection: retained spikes and low-load periods")
    fig.tight_layout();fig.savefig(plot_dir / "uci_full_year.png",dpi=160);plt.close(fig)
    text = f"""# UCI Steel audit

Source: supplied immutable CSV, SHA256 `{audit['source_hash']}`. Real Korean plant; different size/product from this reference plant.

{len(df):,} rows, zero missing values, duplicates or 15-minute gaps after the documented interval correction. Coverage: {audit['start']} to {audit['end_exclusive']} exclusive. All numeric energy/reactive/PF ranges valid; NSM matches original clock time. Full ranges are in uci_steel_audit.json.

The file has {audit['raw_timestamp_backward_jumps']} backward timestamp jumps: every day's 00:00 row follows 23:45 with the same printed date. Verified this pattern on all {audit['midnight_rows_shifted']} days. Interpret 00:00 as next-day interval end and subtract 15 minutes for interval-start timestamps. Keep original date, source_timestamp and source_row_id. Day labels now agree with interval starts; no values removed or imputed. Midnight correction is a documented inferred convention, not supplied timezone evidence. Source time is timezone-naive Korean local clock; simulator uses separate Indian local clock.

Jan-Aug training, Sep-Oct validation, Nov-Dec test are frozen by interval-start date. Calibration uses training only. All-year EDA is descriptive; do not use its held-out insights for model selection. Repeated adjacent loads ({audit['consecutive_repeats']} pairs), low-load periods and spikes are retained; repeated kWh alone is not a duplicate record.

- Normalized profile: weekend/weekday mean load ratio {allstats['weekend_weekday_ratio']:.3f}; this is operating behaviour, not evidence of avoidable waste.
- Tariff-band view: {totals['peak']/totals.sum():.1%} of annual observed energy falls in the illustrative seasonal Punjab evening band; no monetary conversion or shifting/savings claim.
- Lagging PF is below 0.90 in {audit['lagging_pf_below_09']:.1%} of rows; leading PF below 0.90 in {audit['leading_pf_below_09']:.1%}. These channels are distinct, not interchangeable site PF.

## Leakage boundary
CO2 is derived/rounded from same-slot energy. Both reactive-energy columns and both PF columns describe the same electrical interval and can reveal same-slot Usage_kWh through power identities. Drop them for contemporaneous prediction or use strictly past lags available before the forecast origin. Do not include Load_Type if defined from contemporaneous load. Backward-only windows, train-only scaling and forecast-horizon purging remain requirements for Phase II. No model or savings estimate is produced in Phase I.
"""
    (ROOT / "reports/uci_steel_audit.md").write_text(text,encoding="utf-8")
    return df


def prepare_ai4i(seed,manifest):
    df=pd.read_csv(ROOT / "data/raw" / AI4I)
    if df.isna().any().any() or df.UDI.duplicated().any() or df.duplicated().any():
        raise ValueError("AI4I missingness/duplicate gate failed")
    binary=["Machine failure","TWF","HDF","PWF","OSF","RNF"]
    if not all(set(df[c]) <= {0,1} for c in binary) or not set(df.Type)<={"L","M","H"}:
        raise ValueError("Invalid AI4I categories/targets")
    if (df[FEATURES[1:]]<0).any().any() or not np.isfinite(df[FEATURES[1:]]).all().all():
        raise ValueError("Invalid machine physical features")
    ids=np.arange(len(df))
    train,rest=train_test_split(ids,test_size=.30,stratify=df["Machine failure"],random_state=seed)
    val,test=train_test_split(rest,test_size=.50,stratify=df.iloc[rest]["Machine failure"],random_state=seed)
    splits=np.full(len(df),"",dtype=object)
    for name,rows in [("train",train),("validation",val),("test",test)]:
        splits[rows]=name
    split=pd.DataFrame(dict(source_row_id=ids,split=splits,target=df["Machine failure"]))
    out=ROOT / "data/interim"
    split.to_parquet(out / "ai4i_split_manifest.parquet",index=False)
    safe=df[FEATURES+["Machine failure"]].copy()
    safe.insert(0,"source_row_id",ids)  # join key, explicitly excluded from features
    safe.to_parquet(out / "ai4i_clean.parquet",index=False)
    write_json(out / "ai4i_feature_contract.json",dict(features=FEATURES,target="Machine failure",join_key="source_row_id",
               forbidden_features=FORBIDDEN+["source_row_id","Machine failure"],seed=seed,source_sha256=manifest[AI4I]["sha256"],
               split_manifest_sha256=sha256(out / "ai4i_split_manifest.parquet")))
    audit=dict(rows=len(df),missing_by_column=df.isna().sum().to_dict(),duplicate_rows=0,duplicate_udi=0,
               failure_prevalence=float(df["Machine failure"].mean()),
               failure_type_disagreements=int(df[binary[1:]].max(axis=1).ne(df["Machine failure"]).sum()),
               split_counts=split.groupby("split").size().to_dict(),split_failures=split.groupby("split").target.sum().to_dict(),
               ranges={c:dict(min=float(df[c].min()),max=float(df[c].max())) for c in FEATURES[1:]})
    write_json(ROOT / "reports/ai4i_audit.json",audit)
    (ROOT / "reports/ai4i_audit.md").write_text(f"""# AI4I audit

10,000 synthetic independent machine snapshots; not this steel plant and not a longitudinal failure-warning benchmark. Target Machine failure preserved exactly; prevalence {audit['failure_prevalence']:.2%}. Zero missing rows, duplicate rows or UDI values; numeric physical features nonnegative and finite. Ranges and split class counts: ai4i_audit.json.

Fixed seed-{seed} stratified 70/15/15 manifest: {audit['split_counts']}. Safe feature allowlist: {FEATURES}. TWF/HDF/PWF/OSF/RNF, UDI, Product ID, source_row_id and the target are prohibited as inputs. source_row_id is an audit/join key only. Failure-type OR differs from the preserved target in {audit['failure_type_disagreements']} rows; do not rewrite the target from these columns. No classifier trained.
""",encoding="utf-8")


def main():
    manifest=acquire()
    config=values(load_config())
    prepare_steel(config,manifest)
    prepare_ai4i(config["seed"],manifest)


if __name__=="__main__":
    main()
