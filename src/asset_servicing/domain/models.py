"""Core domain records and state transitions."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PageNumber = Annotated[int, Field(gt=0)]


class RunState(StrEnum):
    """Lifecycle stages for one document-processing run."""

    CREATED = "created"
    LOCATING = "locating"
    LOCATION_READY = "location_ready"
    LOCATION_CONFIRMED = "location_confirmed"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    VALIDATING = "validating"
    REVIEWING = "reviewing"
    FINAL_READY = "final_ready"
    FAILED_LOCATION = "failed_location"
    FAILED_EXTRACTION = "failed_extraction"
    FAILED_VALIDATION = "failed_validation"


class SourceKind(StrEnum):
    """Origin of an extracted variable."""

    TABLE = "table"
    PROSE = "prose"
    HUMAN_ADDED = "human_added"


class ReviewStatus(StrEnum):
    """Human-review state for an extracted variable."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    EDITED = "edited"
    NOT_APPLICABLE = "not_applicable"


class ValidationVerdict(StrEnum):
    """Independent validator conclusion for one variable."""

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"


class ConfidenceBasis(StrEnum):
    """Meaning assigned to the validator's confidence score."""

    LLM_RUBRIC = "llm_rubric"


class EvidenceSupport(StrEnum):
    """How directly the source supports one validated value."""

    LITERAL = "literal"
    NORMALIZED = "normalized"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


class FindingReviewStatus(StrEnum):
    """Human-review state for a possible omission."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DISMISSED = "dismissed"


class ReviewAction(StrEnum):
    """Explicit actions a human reviewer can take."""

    CONFIRM = "confirm"
    EDIT = "edit"
    NOT_APPLICABLE = "not_applicable"
    ADD_MISSING = "add_missing"
    DISMISS_OMISSION = "dismiss_omission"


class ReviewReason(StrEnum):
    """Independent reasons that require human review."""

    LOW_CONFIDENCE = "low_confidence"
    VERDICT = "verdict"
    CONFLICT = "conflict"
    OMISSION = "omission"


class ReviewItemKind(StrEnum):
    """Type of source record represented in the review queue."""

    VARIABLE = "variable"
    OMISSION = "omission"


class SectionLocation(BaseModel):
    """Candidate or confirmed document section."""

    title: NonEmptyText
    page_start: PageNumber
    page_end: PageNumber
    rationale: NonEmptyText
    confirmed: bool = False

    @model_validator(mode="after")
    def validate_page_range(self) -> Self:
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return self


class ExtractedVariable(BaseModel):
    """Atomic fact extracted from a table, prose, or human review."""

    id: NonEmptyText
    canonical_name: NonEmptyText
    original_name: NonEmptyText
    original_value: NonEmptyText
    current_name: NonEmptyText
    current_value: NonEmptyText
    evidence_text: NonEmptyText
    source_pages: list[PageNumber] = Field(min_length=1)
    source_kind: SourceKind
    clause_reference: str | None = None
    reviewed: bool = False
    review_status: ReviewStatus = ReviewStatus.PENDING

    @model_validator(mode="after")
    def validate_review_state(self) -> Self:
        was_reviewed = self.review_status is not ReviewStatus.PENDING
        if self.reviewed is not was_reviewed:
            raise ValueError("reviewed must match an explicit non-pending review status")
        return self

    def apply_review(self, decision: ReviewDecision) -> Self:
        """Apply one explicit human decision while preserving original fields."""

        if decision.variable_id != self.id:
            raise ValueError("review decision targets a different variable")
        if decision.action is ReviewAction.ADD_MISSING:
            raise ValueError("add_missing creates a new variable")

        current_name = self.current_name
        current_value = self.current_value
        review_status = ReviewStatus.CONFIRMED
        if decision.action is ReviewAction.EDIT:
            if not decision.resulting_name or not decision.resulting_value:
                raise ValueError("edit review requires resulting name and value")
            current_name = decision.resulting_name
            current_value = decision.resulting_value
            review_status = ReviewStatus.EDITED
        elif decision.action is ReviewAction.NOT_APPLICABLE:
            review_status = ReviewStatus.NOT_APPLICABLE

        updated = type(self).model_validate(
            {
                **self.model_dump(),
                "current_name": current_name,
                "current_value": current_value,
                "reviewed": True,
                "review_status": review_status,
            }
        )
        for field_name in type(self).model_fields:
            object.__setattr__(self, field_name, getattr(updated, field_name))
        return self


class ValidationResult(BaseModel):
    """Independent assessment of one extracted variable."""

    variable_id: NonEmptyText
    confidence: float = Field(ge=0, le=1)
    evidence_support: EvidenceSupport | None = None
    verdict: ValidationVerdict
    rationale: NonEmptyText
    issues: list[str]
    has_conflict: bool = False
    confidence_basis: ConfidenceBasis = ConfidenceBasis.LLM_RUBRIC


class CoverageFinding(BaseModel):
    """Possible omission found while comparing extraction with the source."""

    id: NonEmptyText
    description: NonEmptyText
    suggested_name: str | None = None
    evidence_text: NonEmptyText
    source_pages: list[PageNumber] = Field(min_length=1)
    review_status: FindingReviewStatus = FindingReviewStatus.PENDING


class ReviewDecision(BaseModel):
    """Auditable record of an explicit human action."""

    variable_id: NonEmptyText | None = None
    finding_id: NonEmptyText | None = None
    action: ReviewAction
    previous_name: str | None = None
    previous_value: str | None = None
    resulting_name: str | None = None
    resulting_value: str | None = None
    note: str | None = None
    reviewed_at: datetime

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if (self.variable_id is None) is (self.finding_id is None):
            raise ValueError("review decision must target exactly one variable or finding")
        return self


class ReviewItem(BaseModel):
    """One queue entry with all reasons that require human attention."""

    item_id: NonEmptyText
    kind: ReviewItemKind
    reasons: list[ReviewReason] = Field(min_length=1)
    variable_id: str | None = None
    finding_id: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        has_variable = self.variable_id is not None
        has_finding = self.finding_id is not None
        if has_variable is has_finding:
            raise ValueError("review item must target exactly one variable or finding")
        return self


class Run(BaseModel):
    """Aggregate root for a single regulation-processing run."""

    model_config = ConfigDict(validate_assignment=True)

    _ALLOWED_TRANSITIONS: ClassVar[dict[RunState, frozenset[RunState]]] = {
        RunState.CREATED: frozenset({RunState.LOCATING}),
        RunState.LOCATING: frozenset({RunState.LOCATION_READY, RunState.FAILED_LOCATION}),
        RunState.FAILED_LOCATION: frozenset({RunState.LOCATING}),
        RunState.LOCATION_READY: frozenset({RunState.LOCATING, RunState.LOCATION_CONFIRMED}),
        RunState.LOCATION_CONFIRMED: frozenset({RunState.LOCATING, RunState.EXTRACTING}),
        RunState.EXTRACTING: frozenset({RunState.EXTRACTED, RunState.FAILED_EXTRACTION}),
        RunState.FAILED_EXTRACTION: frozenset({RunState.LOCATING, RunState.EXTRACTING}),
        RunState.EXTRACTED: frozenset(
            {RunState.LOCATING, RunState.EXTRACTING, RunState.VALIDATING}
        ),
        RunState.VALIDATING: frozenset({RunState.REVIEWING, RunState.FAILED_VALIDATION}),
        RunState.FAILED_VALIDATION: frozenset(
            {RunState.LOCATING, RunState.EXTRACTING, RunState.VALIDATING}
        ),
        RunState.REVIEWING: frozenset(
            {
                RunState.LOCATING,
                RunState.EXTRACTING,
                RunState.VALIDATING,
                RunState.REVIEWING,
                RunState.FINAL_READY,
            }
        ),
        RunState.FINAL_READY: frozenset(),
    }

    run_id: str = Field(min_length=1)
    document_name: str = Field(min_length=1)
    document_sha256: str = Field(min_length=64, max_length=64)
    page_count: int = Field(gt=0)
    created_at: datetime
    state: RunState = RunState.CREATED
    location: SectionLocation | None = None
    variables: list[ExtractedVariable] = Field(default_factory=list)
    validations: list[ValidationResult] = Field(default_factory=list)
    coverage_findings: list[CoverageFinding] = Field(default_factory=list)
    reviews: list[ReviewDecision] = Field(default_factory=list)
    preliminary_export_path: str | None = None
    final_export_path: str | None = None

    def transition(self, target: RunState) -> Self:
        """Move the run only through an edge declared in the state diagram."""

        if target not in self._ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"invalid run transition: {self.state.value} -> {target.value}")
        if target is RunState.FINAL_READY and self.pending_items():
            raise ValueError("final export is blocked by pending review items")
        self.state = target
        return self

    def confirm_location(self, *, page_start: int, page_end: int) -> Self:
        """Confirm selected pages and invalidate dependent artifacts when they change."""

        if self.state in {
            RunState.LOCATING,
            RunState.EXTRACTING,
            RunState.VALIDATING,
        }:
            raise ValueError("cannot confirm pages while an external call is in progress")
        if self.location is None:
            raise ValueError("a section location is required before confirmation")

        pages_changed = (page_start, page_end) != (
            self.location.page_start,
            self.location.page_end,
        )
        self.location = SectionLocation(
            title=self.location.title,
            page_start=page_start,
            page_end=page_end,
            rationale=self.location.rationale,
            confirmed=True,
        )
        if pages_changed:
            self.variables = []
            self.validations = []
            self.coverage_findings = []
            self.reviews = []
            self.preliminary_export_path = None
            self.final_export_path = None
        self.state = RunState.LOCATION_CONFIRMED
        return self

    def pending_items(self) -> list[ReviewItem]:
        """Return unresolved variables and omissions requiring a human decision."""

        validation_by_variable = {
            validation.variable_id: validation for validation in self.validations
        }
        pending: list[ReviewItem] = []
        for variable in self.variables:
            if variable.review_status is not ReviewStatus.PENDING:
                continue
            validation = validation_by_variable.get(variable.id)
            if validation is None:
                continue

            reasons: list[ReviewReason] = []
            if validation.confidence < 0.85:
                reasons.append(ReviewReason.LOW_CONFIDENCE)
            if validation.verdict is not ValidationVerdict.SUPPORTED:
                reasons.append(ReviewReason.VERDICT)
            if validation.has_conflict:
                reasons.append(ReviewReason.CONFLICT)
            if reasons:
                pending.append(
                    ReviewItem(
                        item_id=f"variable:{variable.id}",
                        kind=ReviewItemKind.VARIABLE,
                        variable_id=variable.id,
                        reasons=reasons,
                    )
                )

        for finding in self.coverage_findings:
            if finding.review_status is FindingReviewStatus.PENDING:
                pending.append(
                    ReviewItem(
                        item_id=f"finding:{finding.id}",
                        kind=ReviewItemKind.OMISSION,
                        finding_id=finding.id,
                        reasons=[ReviewReason.OMISSION],
                    )
                )
        return pending

    def can_export_final(self) -> bool:
        """Allow final export only when the review queue is empty."""

        return not self.pending_items()
