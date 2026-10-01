"""Small independent baseline/linear/LightGBM experiments with held-out selection."""
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder, FunctionTransformer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, average_precision_score, roc_auc_score, brier_score_loss, precision_recall_fscore_support, confusion_matrix
from sklearn.calibration import calibration_curve
from lightgbm import LGBMRegressor, LGBMClassifier
from energy_copilot.common import write_json, sha256
from .contracts import validate_inputs
from .uncertainty import residual_quantiles, prediction_quantiles, interval_metrics


class GroupMean(BaseEstimator, RegressorMixin):
    def fit(self,X,y):
        self.mean_=float(np.mean(y)); self.columns_=[c for c in ("practice_loss_kWh_t","shift") if c in X]
        df=X[self.columns_].copy(); df["y"]=np.asarray(y)
        self.groups_=df.groupby(self.columns_).y.mean().to_dict() if self.columns_ else {}
        return self

    def predict(self,X):
        if not self.columns_:return np.full(len(X),self.mean_)
        return np.array([self.groups_.get(tuple(row) if len(row)>1 else row[0],self.mean_) for row in X[self.columns_].itertuples(index=False,name=None)])


class Naive(BaseEstimator, RegressorMixin):
    def __init__(self,column):self.column=column
    def fit(self,X,y):self.mean_=float(np.mean(y));return self
    def predict(self,X):return X[self.column].fillna(self.mean_).to_numpy(dtype=float)


class HistoricalMean(BaseEstimator, RegressorMixin):
    def __init__(self,energy=True):self.energy=energy
    def fit(self,X,y):self.mean_=float(np.mean(y));return self
    def predict(self,X):
        p=X.rolling_mean_SEC*X.candidate_liquid_t if self.energy else X.historical_duration_mean
        return p.fillna(self.mean_).to_numpy(dtype=float)


def preprocessing(X):
    numeric=list(X.select_dtypes("number").columns)
    categorical=[c for c in X if c not in numeric]
    transformers=[("numeric",Pipeline([("impute",SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True)),("scale",StandardScaler())]),numeric)]
    if categorical:
        transformers.append(("category",Pipeline([("impute",SimpleImputer(strategy="most_frequent")),("encode",OneHotEncoder(handle_unknown="ignore",sparse_output=False))]),categorical))
    return ColumnTransformer(transformers)


def named_matrix(array):
    """Stable transformed feature names for LightGBM's sklearn validation."""
    return pd.DataFrame(array,columns=[f"feature_{i}" for i in range(array.shape[1])])


def pipeline(X,kind,config,classification=False):
    if kind=="linear":model=LogisticRegression(C=config["logistic_C"],max_iter=config["max_iter"],random_state=config["seed"]) if classification else Ridge(alpha=config["ridge_alpha"])
    else:
        klass=LGBMClassifier if classification else LGBMRegressor
        model=klass(n_estimators=config["trees"],num_leaves=config["leaves"],learning_rate=config["learning_rate"],
                    min_child_samples=config["min_child_samples"],reg_lambda=config["reg_lambda"],random_state=config["seed"],
                    n_jobs=1,deterministic=True,force_col_wise=True,verbosity=-1)
    steps=[("preprocessing",preprocessing(X))]
    if kind!="linear":steps.append(("named_matrix",FunctionTransformer(named_matrix,validate=False)))
    return Pipeline([*steps,("model",model)])


def regression_metrics(y,p):
    y=np.asarray(y);p=np.asarray(p)
    return dict(MAE=float(mean_absolute_error(y,p)),RMSE=float(np.sqrt(mean_squared_error(y,p))),
                WAPE=float(np.abs(y-p).sum()/max(np.abs(y).sum(),1e-12)),R2=float(r2_score(y,p)))


def classification_metrics(y,p,threshold=.5):
    y=np.asarray(y);pred=np.asarray(p)>=threshold
    pr,rc,f1,_=precision_recall_fscore_support(y,pred,average="binary",zero_division=0)
    frac,mean=calibration_curve(y,p,n_bins=10,strategy="quantile")
    return dict(PR_AUC=float(average_precision_score(y,p)),ROC_AUC=float(roc_auc_score(y,p)),
                precision=float(pr),recall=float(rc),F1=float(f1),Brier=float(brier_score_loss(y,p)),
                prevalence=float(y.mean()),threshold=float(threshold),confusion_matrix=confusion_matrix(y,pred,labels=[0,1]).tolist(),
                calibration_bins=[dict(predicted=float(a),observed=float(b)) for a,b in zip(mean,frac)])


def fit_regression(dataset,name,directory,config,load=False):
    audit=dataset.audit(); X=dataset.X;y=dataset.y;meta=dataset.meta
    masks={s:meta.split.eq(s).to_numpy() for s in ("train","validation","calibration","test")}
    candidates={"last_value":Naive("load_lag_1"),"seasonal_naive":Naive("seasonal_naive")} if load else {"historical_mean":HistoricalMean(name=="heat_energy"),"group_mean":GroupMean()}
    candidates.update(linear=pipeline(X,"linear",config),lightgbm=pipeline(X,"lightgbm",config))
    metrics={}; predictions={}; deterministic={};replay_hashes={}
    directory.mkdir(parents=True,exist_ok=True)
    for kind,model in candidates.items():
        model.fit(X.loc[masks["train"]],y.loc[masks["train"]])
        predictions[kind]=np.maximum(0,model.predict(X))
        # Independently fit a second estimator: serialization alone is not a training replay.
        from sklearn.base import clone
        again=clone(model).fit(X.loc[masks["train"]],y.loc[masks["train"]])
        replay=np.maximum(0,again.predict(X))[masks["test"]]
        deterministic[kind]=bool(np.array_equal(replay,predictions[kind][masks["test"]]))
        if not deterministic[kind]:raise ValueError(f"Nonreproducible fitted model {name}/{kind}")
        joblib.dump(model,directory/f"{kind}.joblib",compress=0,protocol=5)
        joblib.dump(again,directory/f"{kind}_replay.joblib",compress=0,protocol=5)
        replay_hashes[kind]=dict(original=sha256(directory/f"{kind}.joblib"),replay=sha256(directory/f"{kind}_replay.joblib"))
        metrics[kind]={s:regression_metrics(y.loc[m],predictions[kind][m]) for s,m in masks.items() if s!="train"}
    # Retain the simpler candidate unless the next complexity tier improves selection MAE by >=2%.
    order=list(candidates);selected=min(order[:2],key=lambda k:metrics[k]["validation"]["MAE"])
    for kind in ("linear","lightgbm"):
        if metrics[kind]["validation"]["MAE"] < metrics[selected]["validation"]["MAE"]*(1-config["minimum_improvement"]): selected=kind
    p=predictions[selected]
    calibration=residual_quantiles(y.loc[masks["calibration"]],p[masks["calibration"]])
    by_horizon={}
    if load:
        for h in sorted(meta.horizon_slot.unique()):
            m=masks["calibration"]&meta.horizon_slot.eq(h).to_numpy()
            by_horizon[str(h)]=residual_quantiles(y.loc[m],p[m]) if m.sum()>=config["min_calibration_group"] else calibration
    def quantiles(indices):
        if not load:return prediction_quantiles(p[indices],calibration)
        rows=np.flatnonzero(indices)
        return {q:np.array([max(0,p[i]+by_horizon[str(meta.horizon_slot.iloc[i])][q]) for i in rows]) for q in ("p10","p50","p90")}
    test=meta.loc[masks["test"]].reset_index(drop=True).copy(); q=quantiles(masks["test"])
    test["actual"]=y.loc[masks["test"]].to_numpy()
    for k,v in q.items():test[k]=v
    test["model_version"]=config["version"];test["selected_model"]=selected
    for kind in candidates:test[f"{kind}_prediction"]=predictions[kind][masks["test"]]
    # Point metrics refer to central calibrated predictions handed to the API.
    interval=interval_metrics(test.actual,q)
    grouped={}
    for col in ("seed","practice_loss_kWh_t","horizon_slot"):
        if col in test:
            grouped[col]={str(k):dict(regression_metrics(g.actual,g.p50),**interval_metrics(g.actual,{q:g[q].to_numpy() for q in ("p10","p50","p90")})) for k,g in test.groupby(col)}
    if load:
        peaks=test.groupby(["run_id","forecast_origin"])[["actual","p50"]].max()
        interval["peak_load_MAE"]=float(np.abs(peaks.actual-peaks.p50).mean())
    fallback=dict(central=float(y.loc[masks["train"]].mean()),calibration=calibration)
    bundle=dict(name=name,version=config["version"],features=list(X),model=candidates[selected],calibration=calibration,
                by_horizon=by_horizon,fallback=fallback,selected=selected)
    joblib.dump(bundle,directory/"production.joblib",compress=0,protocol=5)
    metadata=dict(task=name,selected=selected,features=list(X),effective_features=candidates[selected].columns_ if isinstance(candidates[selected],GroupMean) else list(X),feature_types={c:"number" if pd.api.types.is_numeric_dtype(X[c]) else "string" for c in X},dataset_audit=audit,candidates=metrics,
                  central_test=regression_metrics(test.actual,test.p50),interval=interval,grouped_test=grouped,
                  calibration=calibration,by_horizon=by_horizon,config=config,deterministic_training=deterministic,
                  artifact_replay_hashes=replay_hashes,fallback=fallback,
                  selection_rule="Whole-run validation MAE; >=2% improvement required for a higher complexity tier. Test never selects or calibrates.")
    write_json(directory/"metadata.json",metadata)
    test.to_parquet(directory/"test_predictions.parquet",index=False)
    return metadata,test


def logit(p):
    p=np.clip(p,1e-8,1-1e-8);return np.log(p/(1-p)).reshape(-1,1)


def fit_health(dataset,name,directory,config):
    audit=dataset.audit();X=dataset.X;y=dataset.y;meta=dataset.meta
    masks={s:meta.split.eq(s).to_numpy() for s in ("train","validation","calibration","test")}
    models={k:pipeline(X,k,config,classification=True) for k in ("linear","lightgbm")}
    ps={};metrics={};deterministic={}
    directory.mkdir(parents=True,exist_ok=True)
    from sklearn.base import clone
    for kind,model in models.items():
        model.fit(X.loc[masks["train"]],y.loc[masks["train"]]);p=model.predict_proba(X)[:,1];ps[kind]=p
        metrics[kind]={s:classification_metrics(y.loc[m],p[m]) for s,m in masks.items() if s!="train"}
        again=clone(model).fit(X.loc[masks["train"]],y.loc[masks["train"]])
        deterministic[kind]=bool(np.array_equal(p[masks["test"]],again.predict_proba(X)[:,1][masks["test"]]))
        if not deterministic[kind]:raise ValueError("Nondeterministic classification training")
        joblib.dump(model,directory/f"{kind}.joblib",compress=0,protocol=5)
        joblib.dump(again,directory/f"{kind}_replay.joblib",compress=0,protocol=5)
    selected="linear"
    if metrics["lightgbm"]["validation"]["PR_AUC"]>metrics["linear"]["validation"]["PR_AUC"]+config["health_minimum_pr_gain"]:selected="lightgbm"
    p=ps[selected];cal=LogisticRegression(C=config["calibrator_C"],max_iter=config["max_iter"],random_state=config["seed"])
    cal.fit(logit(p[masks["calibration"]]),y.loc[masks["calibration"]])
    calibrated=cal.predict_proba(logit(p))[:,1]
    # Threshold chosen on selection validation ONLY; final test untouched.
    grid=np.asarray(config["threshold_grid"])
    scores=[classification_metrics(y.loc[masks["validation"]],calibrated[masks["validation"]],t)["F1"] for t in grid]
    threshold=float(grid[int(np.argmax(scores))])
    test=meta.loc[masks["test"]].reset_index(drop=True).copy();test["actual"]=y.loc[masks["test"]].to_numpy()
    test["failure_probability"]=p[masks["test"]];test["calibrated_probability"]=calibrated[masks["test"]]
    test["model_version"]=config["version"];test["selected_model"]=selected;test["threshold"]=threshold
    grouped={str(k):classification_metrics(g.actual,g.calibrated_probability,threshold) for k,g in test.groupby("seed")} if "seed" in test else {}
    prevalence=float(y.loc[masks["train"]].mean())
    metadata=dict(task=name,selected=selected,features=list(X),feature_types={c:"number" if pd.api.types.is_numeric_dtype(X[c]) else "string" for c in X},dataset_audit=audit,candidates=metrics,
                  raw_test=classification_metrics(test.actual,test.failure_probability,threshold),
                  calibrated_test=classification_metrics(test.actual,test.calibrated_probability,threshold),
                  validation_calibrated=classification_metrics(y.loc[masks["validation"]],calibrated[masks["validation"]],threshold),
                  grouped_test=grouped,deterministic_training=deterministic,config=config,threshold=threshold,
                  fallback=dict(prevalence=prevalence,calibrated=False),
                  no_skill_Brier=float(np.mean((test.actual-prevalence)**2)))
    bundle=dict(name=name,version=config["version"],features=list(X),model=models[selected],calibrator=cal,
                threshold=threshold,fallback=metadata["fallback"],horizon_hours=config["health_horizon_hours"])
    joblib.dump(bundle,directory/"production.joblib",compress=0,protocol=5)
    write_json(directory/"metadata.json",metadata);test.to_parquet(directory/"test_predictions.parquet",index=False)
    return metadata,test
