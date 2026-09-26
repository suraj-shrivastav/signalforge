"""TopicCard: an editor-facing article pitch derived from one relevant signal."""

from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import Field

from signalforge.core.artifacts.base import Artifact


class ArticleFormat(StrEnum):
    EXPLAINER = "explainer"
    DEEP_DIVE = "deep_dive"
    COMPARISON = "comparison"


class RiskFlag(StrEnum):
    UNVERIFIED_CLAIM = "unverified_claim"
    SINGLE_SOURCE = "single_source"
    HYPE = "hype"
    PAYWALLED = "paywalled"
    STALE = "stale"


class TopicCard(Artifact):
    SCHEMA_VERSION: ClassVar[int] = 1

    signal_id: UUID
    what_happened: str = Field(min_length=1, max_length=400)
    why_it_matters: str = Field(min_length=1, max_length=300)
    novelty: float = Field(ge=0, le=1)
    signal_strength: float = Field(ge=0, le=1)
    coverage_gap: str = Field(max_length=300)
    suggested_angle: str = Field(min_length=1, max_length=200)
    format: ArticleFormat
    evergreen_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    risk_flags: tuple[RiskFlag, ...]
    prompt_version: str = Field(min_length=1)
    model: str = Field(min_length=1)
