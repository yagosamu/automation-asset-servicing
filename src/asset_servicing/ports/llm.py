"""Strict contracts for the locator, extractor, and independent validator agents."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from asset_servicing.domain.models import EvidenceSupport, ValidationVerdict

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PageNumber = Annotated[int, Field(strict=True, gt=0)]


class _ContractModel(BaseModel):
    """Shared structural guarantees for data crossing the LLM boundary."""

    model_config = ConfigDict(extra="forbid", validate_default=True)


class AgentDocument(_ContractModel):
    """PDF payload supplied to one agent call without provider-specific details."""

    filename: NonEmptyText
    content: bytes = Field(min_length=1)


class LocationStatus(StrEnum):
    """Whether the locator found a semantically compatible section."""

    FOUND = "found"
    NOT_FOUND = "not_found"


class ExtractionSourceKind(StrEnum):
    """Document origin allowed for a machine-extracted fact."""

    TABLE = "table"
    PROSE = "prose"


class LocateRequest(_ContractModel):
    """Input for semantic section location over the complete document."""

    document: AgentDocument
    instructions: NonEmptyText
    prompt_version: NonEmptyText
    chapter_hint: Annotated[int, Field(strict=True, gt=0)] | None = None


class LocateResponse(_ContractModel):
    """Structured locator result, including an explicit recoverable miss."""

    status: LocationStatus
    title: NonEmptyText | None = None
    page_start: PageNumber | None = None
    page_end: PageNumber | None = None
    rationale: NonEmptyText

    @model_validator(mode="after")
    def validate_location(self) -> Self:
        location_fields = (self.title, self.page_start, self.page_end)
        if self.status is LocationStatus.FOUND:
            if any(value is None for value in location_fields):
                raise ValueError("found location requires title, page_start, and page_end")
            if (
                self.page_start is not None
                and self.page_end is not None
                and self.page_end < self.page_start
            ):
                raise ValueError("page_end must be greater than or equal to page_start")
        elif any(value is not None for value in location_fields):
            raise ValueError("not_found location cannot include title or pages")
        return self


class _SelectedPagesRequest(_ContractModel):
    """Common source fields for agents restricted to confirmed pages."""

    document: AgentDocument
    page_start: PageNumber
    page_end: PageNumber
    instructions: NonEmptyText
    prompt_version: NonEmptyText

    @model_validator(mode="after")
    def validate_page_range(self) -> Self:
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class ExtractionRequest(_SelectedPagesRequest):
    """Input for extracting atomic facts from confirmed source pages."""

    preferred_vocabulary: list[NonEmptyText]


class AtomicVariable(_ContractModel):
    """One independent fact returned by the extractor with source evidence."""

    name: NonEmptyText
    value: NonEmptyText
    evidence_text: NonEmptyText
    source_pages: list[PageNumber] = Field(min_length=1)
    source_kind: ExtractionSourceKind
    clause_reference: NonEmptyText | None = None


class ExtractionResponse(_ContractModel):
    """Complete structured output of one extractor call."""

    variables: list[AtomicVariable]


class ValidationCandidate(_ContractModel):
    """Extracted fact shown to the validator without extractor judgment."""

    variable_id: NonEmptyText
    name: NonEmptyText
    value: NonEmptyText
    evidence_text: NonEmptyText
    source_pages: list[PageNumber] = Field(min_length=1)
    source_kind: ExtractionSourceKind
    clause_reference: NonEmptyText | None = None


class ValidationRequest(_SelectedPagesRequest):
    """Input for comparing extracted facts independently with their source."""

    variables: list[ValidationCandidate]


class VariableValidation(_ContractModel):
    """Independent validator assessment for one extracted variable."""

    variable_id: NonEmptyText
    confidence: float = Field(strict=True, ge=0, le=1)
    evidence_support: EvidenceSupport
    verdict: ValidationVerdict
    rationale: NonEmptyText
    issues: list[NonEmptyText]
    has_conflict: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def validate_evidence_support(self) -> Self:
        expected: dict[EvidenceSupport, tuple[float, float, ValidationVerdict]] = {
            EvidenceSupport.LITERAL: (0.95, 1.01, ValidationVerdict.SUPPORTED),
            EvidenceSupport.NORMALIZED: (0.85, 0.95, ValidationVerdict.SUPPORTED),
            EvidenceSupport.PARTIAL: (0.60, 0.85, ValidationVerdict.PARTIALLY_SUPPORTED),
            EvidenceSupport.UNSUPPORTED: (0.00, 0.60, ValidationVerdict.UNSUPPORTED),
        }
        minimum, exclusive_maximum, verdict = expected[self.evidence_support]
        if not minimum <= self.confidence < exclusive_maximum or self.verdict is not verdict:
            raise ValueError("evidence support, confidence band, and verdict must be coherent")
        return self


class OmissionFinding(_ContractModel):
    """Possible source fact missing from the extractor output."""

    description: NonEmptyText
    suggested_name: NonEmptyText | None = None
    evidence_text: NonEmptyText
    source_pages: list[PageNumber] = Field(min_length=1)


class ValidationResponse(_ContractModel):
    """Validator results and possible omissions from one independent call."""

    validations: list[VariableValidation]
    omissions: list[OmissionFinding]


@runtime_checkable
class LLMProvider(Protocol):
    """Provider-neutral port with one operation per independent agent."""

    def locate(self, request: LocateRequest) -> LocateResponse:
        """Locate a semantically compatible section in the full document."""

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        """Extract atomic facts from the confirmed page interval."""

    def validate(self, request: ValidationRequest) -> ValidationResponse:
        """Validate extracted facts independently and identify omissions."""


__all__ = [
    "AgentDocument",
    "AtomicVariable",
    "EvidenceSupport",
    "ExtractionRequest",
    "ExtractionResponse",
    "ExtractionSourceKind",
    "LLMProvider",
    "LocateRequest",
    "LocateResponse",
    "LocationStatus",
    "OmissionFinding",
    "ValidationCandidate",
    "ValidationRequest",
    "ValidationResponse",
    "ValidationVerdict",
    "VariableValidation",
]
