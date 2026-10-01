"""Create versioned optimizer settings without touching prior-phase settings."""
from pathlib import Path
import json
import yaml
from energy_copilot.common import parameter, sha256, validate_parameters


def setup():
    p = lambda v, u, note: parameter(v, u, 'assumption', 'Phase II-C deterministic planning contract', note)
    cfg = dict(version='optimizer_v1', plant_config='data/processed/sim_v1.1/config_snapshot.yaml',
               prediction_directory='models/phase2b_v1', prediction_version='forecast_v1',
               prediction_schema_sha256=sha256('models/phase2b_v1/prediction_schema.yaml'),
               prediction_contract_sha256=sha256('models/phase2b_v1/prediction_contract.json'),
               timezone='Asia/Kolkata',
               slot_minutes=p(15,'min','96 quarter-hour accounting, rolling and availability slots.'),
               horizon_slots=p(96,'slot','One local day; no DST in declared timezone.'),
               candidate_step_minutes=p(5,'min','Subslot start grid: avoids rounding a 105.2-min prediction to 120 min. Strict 15-min policy is tested separately; not a simulator change.'),
               tolerance=p(1e-6,'numeric ledger tolerance','Independent checker tolerance; does not relax safety interlocks.'),
               sec_target=None,
               sec_target_notes='No target supplied. Disabled explicitly; caller may supply an explicit kWh/t-liquid cap.',
               allowed_practices=['normal','practice_loss_40'],
               practice_notes='normal is reference; practice_loss_40 is a synthetic, physically coupled experiment, not a validated shop-floor recommendation.',
               solver=dict(library='pyomo.appsi.highs',pyomo_version='6.9.5',highspy_version='1.12.0',threads=p(1,'thread','Deterministic serial solver.'),
                           seed=p(42,'dimensionless','Fixed solver random seed, not plant randomness.'),
                           time_limit_seconds=p(60,'s','Incumbent requires independent check; limit is never reported as optimal.'),
                           relative_gap=p(0.0,'fraction','Request proven optimum.'),
                           absolute_gap=p(1e-6,'objective unit','Numerical certificate tolerance.')),
               tariff=dict(version='synthetic_tou_v1',source='Phase II-C synthetic experiment; not a DISCOM tariff',
                           unit='Rs/kWh',period_rates={k:p(v,'Rs/kWh','Explicit synthetic test rate, no billing claim.') for k,v in [('offpeak',4),('normal',8),('peak',12)]},
                           offpeak_hours=p([0,6,22,24],'h','Half-open [0,6), [22,24).'),peak_hours=p([18,22],'h','Half-open synthetic evening band.')),
               policy=dict(heat_order='input order',pump='continuous whenever externally available',
                           rhf='fixed configured-temperature readiness throughout allowed rolling window',
                           compressor='configured loaded duty during allowed rolling window, idle otherwise',
                           inventory_release='billets available at first accounting boundary after predicted completion; rolling uses opening stock only',
                           demand='additive asset apparent-power upper bound with full IF/mill/compressor nameplate reserves in active slots',
                           energy_allocation='forecast heat kWh at rated IF power at end of predicted cycle; preceding time nonpowered',
                           quality='only frozen supported practice modes; fixed RHF setpoint, no metallurgical decision variables'))
    validate_parameters(cfg)
    Path('configs/optimizer_v1.yaml').write_text(yaml.safe_dump(cfg,sort_keys=False),encoding='utf-8')
    lock=Path('requirements-phase2b.lock.txt').read_text().rstrip()+'\npyomo==6.9.5\nhighspy==1.12.0\nply==3.11\n'
    Path('requirements-phase2c.lock.txt').write_text(lock,encoding='utf-8')


if __name__=='__main__': setup()
