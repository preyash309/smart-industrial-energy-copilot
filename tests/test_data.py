import json
import pandas as pd
from energy_copilot.common import ROOT, sha256, load_config, validate_parameters
from energy_copilot.data.prepare import FEATURES, FORBIDDEN


def test_raw_hashes_and_canonical_coverage():
    hashes=json.loads((ROOT / "data/raw/source_hashes.json").read_text())
    for name,meta in hashes.items():
        assert sha256(ROOT / meta["raw_path"])==meta["sha256"]
        assert sha256(ROOT / meta["input_path"])==meta["sha256"]
    steel=pd.read_parquet(ROOT / "data/interim/uci_steel_clean.parquet")
    assert len(steel)==35040
    assert steel.timestamp.is_monotonic_increasing and steel.timestamp.is_unique
    assert steel.timestamp.diff().dropna().eq(pd.Timedelta(minutes=15)).all()
    assert steel.timestamp.min()==pd.Timestamp("2018-01-01")
    assert steel.interval_end.max()==pd.Timestamp("2019-01-01")
    assert not steel.isna().any().any()


def test_frozen_time_splits_and_training_calibration():
    import yaml
    s=pd.read_parquet(ROOT / "data/interim/uci_steel_split_manifest.parquet")
    assert len(s)==35040 and s.source_row_id.is_unique
    assert s[s.split.eq("train")].timestamp.dt.month.le(8).all()
    assert s[s.split.eq("validation")].timestamp.dt.month.between(9,10).all()
    assert s[s.split.eq("test")].timestamp.dt.month.ge(11).all()
    cal=yaml.safe_load((ROOT / "configs/calibration_v1.yaml").read_text())
    assert cal["fit_window"]=="Jan-Aug 2018 only"
    validate_parameters(cal)
    assert len(cal["daily_profile"]["value"])==96


def test_ai4i_preserves_target_and_blocks_leakage():
    df=pd.read_parquet(ROOT / "data/interim/ai4i_clean.parquet")
    raw=pd.read_csv(ROOT / "Datasets/ai4i2020.csv")
    assert df["Machine failure"].equals(raw["Machine failure"])
    assert not set(FORBIDDEN)&set(df.columns)
    contract=json.loads((ROOT / "data/interim/ai4i_feature_contract.json").read_text())
    assert contract["features"]==FEATURES
    assert "source_row_id" not in FEATURES
    s=pd.read_parquet(ROOT / "data/interim/ai4i_split_manifest.parquet")
    assert s.source_row_id.is_unique and set(s.source_row_id)==set(range(10000))
    assert s.groupby("split").size().to_dict()=={"test":1500,"train":7000,"validation":1500}
    assert max(abs(x-raw["Machine failure"].mean()) for x in s.groupby("split").target.mean())<0.001


def test_plant_numeric_metadata():
    validate_parameters(load_config())
