"""Deterministic decisions, independent of forecast model implementation."""
from .contracts import OptimizerInput, OptimizerResult, ProductionOrder, HeatOrder, HeatCandidate, TariffSlot, OperatingConstraints, input_from_dict
from .candidates import build_optimizer_input, load_settings
from .solve import optimize
from .checker import check_schedule
