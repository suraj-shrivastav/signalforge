"""Typed, versioned artifacts passed between pipeline stages (PRD §33)."""

from signalforge.core.artifacts.base import VOLATILE_FIELDS, Artifact
from signalforge.core.artifacts.signal import RawSignal

__all__ = ["VOLATILE_FIELDS", "Artifact", "RawSignal"]
