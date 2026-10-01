"""B01 checks using observed/true tables and independent numpy arithmetic."""
import numpy as np


def temperature_boundary(readings, truth, config):
    zone = config["rhf"]["temp"]["value"]
    flue = config["rhf"]["flue_temp"]["value"]
    sensitivity = config["faults"]["fouling_flue"]["value"]
    r = readings[readings.asset_id.eq("RHF_01")].set_index("timestamp")
    t = truth[truth.asset_id.eq("RHF_01")].set_index("timestamp").loc[r.index]
    # Same attack population as the audit: active, finite, ordinary zone readings.
    # Exclude gross glitches; do not exclude rows according to recovery error.
    valid = (t.kW.gt(0) & r.temp_C.between(zone-100, zone+100)
             & np.isfinite(r.flue_temp_C))
    r = r.loc[valid]; t = t.loc[valid]
    recovered = (zone*r.flue_temp_C/r.temp_C-flue)/sensitivity
    error = np.abs(recovered-t.latent_fouling)
    zone_residual = r.temp_C/t.temp_C-1
    flue_residual = r.flue_temp_C/t.flue_temp_C-1
    return dict(rows=len(r), median_error=float(error.median()), max_error=float(error.max()),
                exact_rows=int(error.lt(1e-10).sum()),
                residual_max_difference=float(np.abs(zone_residual-flue_residual).max()),
                residual_correlation=float(zone_residual.corr(flue_residual)),
                zone_relative_noise_sd=float(zone_residual.std()),
                flue_relative_noise_sd=float(flue_residual.std()),
                observed_flue_fouling_correlation=float(r.flue_temp_C.corr(t.latent_fouling)),
                formula=f"({zone} * observed_flue / observed_zone - {flue}) / {sensitivity}")


def assert_b01_resolved(metrics, noise_scale):
    # Explicitly reject a return to floating-point recovery, not just column leakage.
    assert metrics["rows"] > 1000
    assert metrics["median_error"] > 1e-6, "B01: median near-exact fouling recovery"
    assert metrics["max_error"] > 1e-5, "B01: maximum near-exact fouling recovery"
    assert metrics["exact_rows"] == 0
    assert metrics["residual_max_difference"] > 1e-5
    assert abs(metrics["residual_correlation"]) < .1
    for channel in ("zone", "flue"):
        assert .85*noise_scale < metrics[f"{channel}_relative_noise_sd"] < 1.15*noise_scale
    # The specified fouling signal remains informative at the existing 0.5% scale.
    assert metrics["observed_flue_fouling_correlation"] > .3
