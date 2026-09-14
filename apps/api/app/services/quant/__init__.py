"""Quantitative inventory & decision-support module (spec v4–v7).

Deterministic engines only — the LLM never produces the numbers. Every figure
carries provenance and the config/model version used, so results are reproducible
and replayable. Gated by settings.QUANT_INVENTORY_ENABLED.
"""
from app.core.config import settings

MODEL_NAMESPACE = "quant"


def enabled() -> bool:
    return bool(settings.QUANT_INVENTORY_ENABLED)


def config_version() -> str:
    return settings.QUANT_CONFIG_VERSION
