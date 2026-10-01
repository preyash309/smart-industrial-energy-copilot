"""Provenance, parameter metadata and the sole random-stream factory."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]


def parameter(value, unit, status, source, notes):
    return dict(value=value, unit=unit, status=status, source=source, notes=notes)


def validate_parameters(node, path="config"):
    if isinstance(node, dict):
        if "value" in node:
            required = {"value", "unit", "status", "source", "notes"}
            if not required <= node.keys() or node["status"] not in {"sourced", "derived", "assumption"}:
                raise ValueError(f"Invalid parameter metadata at {path}")
            if not all(node[k] for k in required - {"value"}):
                raise ValueError(f"Empty parameter provenance at {path}")
            return
        for k, v in node.items():
            validate_parameters(v, f"{path}.{k}")
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            validate_parameters(v, f"{path}[{i}]")
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        raise ValueError(f"Bare numeric parameter at {path}")


def values(node):
    if isinstance(node, dict):
        if "value" in node:
            return node["value"]
        return {k: values(v) for k, v in node.items()}
    if isinstance(node, list):
        return [values(x) for x in node]
    return node


def load_config(path=None):
    path = Path(path or ROOT / "configs/plant_v1.yaml")
    node = yaml.safe_load(path.read_text(encoding="utf-8"))
    validate_parameters(node)
    return node


def rng_streams(seed, names):
    # Stable name-based streams; adding a sensor never shifts weather/charge draws.
    return {name: np.random.default_rng(np.random.SeedSequence(
        [int(seed), int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "little")]
    )) for name in names}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str, allow_nan=False) + "\n", encoding="utf-8")

