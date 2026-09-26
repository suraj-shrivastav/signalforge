"""SignalAssessment: the LLM's relevance judgement of one signal."""

from enum import StrEnum
from typing import ClassVar
from uuid import UUID

from pydantic import Field

from signalforge.core.artifacts.base import Artifact


class Category(StrEnum):
    MODEL_RELEASE = "model_release"
    RESEARCH = "research"
    TOOL = "tool"
    TECHNIQUE = "technique"
    BENCHMARK = "benchmark"
    INFRASTRUCTURE = "infrastructure"
    OTHER = "other"


class SignalAssessment(Artifact):
    SCHEMA_VERSION: ClassVar[int] = 1

    signal_id: UUID
    is_relevant: bool
    relevance_score: float = Field(ge=0, le=1)
    category: Category
    summary: str = Field(min_length=1, max_length=300)
    why_it_matters: str = Field(min_length=1, max_length=300)
    prompt_version: str = Field(min_length=1)
    model: str = Field(min_length=1)
