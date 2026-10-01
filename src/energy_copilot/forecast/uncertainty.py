"""Held-out empirical prediction quantiles, not model-mean confidence intervals."""
import numpy as np


def residual_quantiles(y, prediction):
    residual=np.sort(np.asarray(y)-np.asarray(prediction))
    if len(residual)<20:
        raise ValueError("Insufficient independent calibration partition")
    # Finite-sample signed ranks. No Gaussian residual assumption.
    def rank(q):
        return float(residual[max(0,min(len(residual)-1,int(np.ceil((len(residual)+1)*q))-1))])
    return {"p10":rank(.1),"p50":rank(.5),"p90":rank(.9),"n":len(residual)}


def prediction_quantiles(prediction, calibration):
    p=np.asarray(prediction,dtype=float)
    return {q:np.maximum(0,p+calibration[q]) for q in ("p10","p50","p90")}


def interval_metrics(y, quantiles):
    y=np.asarray(y)
    return {"requested_two_sided_coverage":.8,"requested_upper_coverage":.9,
            "actual_two_sided_coverage":float(np.mean((y>=quantiles["p10"])&(y<=quantiles["p90"]))),
            "actual_upper_coverage":float(np.mean(y<=quantiles["p90"])),
            "mean_width":float(np.mean(quantiles["p90"]-quantiles["p10"]))}
