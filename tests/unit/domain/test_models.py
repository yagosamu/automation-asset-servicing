"""Domain behavior derived from the regulation extraction specification."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from asset_servicing.domain.models import (
    ConfidenceBasis,
    CoverageFinding,
    ExtractedVariable,
    FindingReviewStatus,
    ReviewAction,
    ReviewDecision,
    ReviewItem,
    ReviewItemKind,
    ReviewReason,
    ReviewStatus,
    Run,
    RunState,
    SectionLocation,
    SourceKind,
    ValidationResult,
    ValidationVerdict,
)

pytestmark = pytest.mark.unit


def make_run(*, state: RunState = RunState.CREATED) -> Run:
    return Run(
        run_id="run-001",
        document_name="regulamento.pdf",
        document_sha256="a" * 64,
        page_count=12,
        created_at=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
        state=state,
    )


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunState.CREATED, RunState.LOCATING),
        (RunState.LOCATING, RunState.LOCATION_READY),
        (RunState.LOCATING, RunState.FAILED_LOCATION),
        (RunState.FAILED_LOCATION, RunState.LOCATING),
        (RunState.LOCATION_READY, RunState.LOCATION_CONFIRMED),
        (RunState.LOCATION_CONFIRMED, RunState.EXTRACTING),
        (RunState.EXTRACTING, RunState.EXTRACTED),
        (RunState.EXTRACTING, RunState.FAILED_EXTRACTION),
        (RunState.FAILED_EXTRACTION, RunState.EXTRACTING),
        (RunState.EXTRACTED, RunState.VALIDATING),
        (RunState.VALIDATING, RunState.REVIEWING),
        (RunState.VALIDATING, RunState.FAILED_VALIDATION),
        (RunState.FAILED_VALIDATION, RunState.VALIDATING),
        (RunState.REVIEWING, RunState.LOCATING),
        (RunState.REVIEWING, RunState.EXTRACTING),
        (RunState.REVIEWING, RunState.VALIDATING),
        (RunState.REVIEWING, RunState.REVIEWING),
        (RunState.REVIEWING, RunState.FINAL_READY),
    ],
)
def test_run_accepts_state_diagram_transitions(current: RunState, target: RunState) -> None:
    run = make_run(state=current)

    transitioned = run.transition(target)

    assert transitioned is run
    assert run.state is target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (RunState.CREATED, RunState.EXTRACTING),
        (RunState.LOCATION_READY, RunState.VALIDATING),
        (RunState.LOCATING, RunState.EXTRACTING),
        (RunState.EXTRACTING, RunState.VALIDATING),
        (RunState.FINAL_READY, RunState.LOCATING),
    ],
)
def test_run_rejects_transitions_outside_state_diagram(current: RunState, target: RunState) -> None:
    run = make_run(state=current)

    with pytest.raises(ValueError, match=f"{current.value}.*{target.value}"):
        run.transition(target)

    assert run.state is current


def make_variable(**updates: object) -> ExtractedVariable:
    data: dict[str, object] = {
        "id": "variable-001",
        "canonical_name": "prazo_resgate",
        "original_name": "Prazo para pagamento do resgate",
        "original_value": "D+30",
        "current_name": "prazo_resgate",
        "current_value": "D+30",
        "evidence_text": "O pagamento do resgate será realizado em até 30 dias.",
        "source_pages": [7],
        "source_kind": SourceKind.PROSE,
        "clause_reference": "Art. 12",
    }
    data.update(updates)
    return ExtractedVariable.model_validate(data)


def test_section_location_requires_an_ordered_positive_page_range() -> None:
    with pytest.raises(ValidationError):
        SectionLocation(
            title="Capítulo 3",
            page_start=8,
            page_end=7,
            rationale="A seção contém regras de emissão e resgate.",
        )


def test_extracted_variable_records_required_source_fields() -> None:
    variable = make_variable()

    assert variable.evidence_text == "O pagamento do resgate será realizado em até 30 dias."
    assert variable.source_pages == [7]
    assert variable.source_kind is SourceKind.PROSE
    assert variable.clause_reference == "Art. 12"


def test_extracted_variable_rejects_blank_evidence() -> None:
    with pytest.raises(ValidationError):
        make_variable(evidence_text="   ")


def test_extracted_variable_rejects_invalid_source_kind() -> None:
    with pytest.raises(ValidationError):
        make_variable(source_kind="spreadsheet")


def test_extracted_variable_rejects_non_positive_source_page() -> None:
    with pytest.raises(ValidationError):
        make_variable(source_pages=[0])


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_validation_rejects_confidence_outside_closed_unit_interval(confidence: float) -> None:
    with pytest.raises(ValidationError):
        ValidationResult(
            variable_id="variable-001",
            confidence=confidence,
            verdict=ValidationVerdict.SUPPORTED,
            rationale="Valor sustentado pela cláusula.",
            issues=[],
        )


def test_validation_rejects_unknown_verdict() -> None:
    with pytest.raises(ValidationError):
        ValidationResult(
            variable_id="variable-001",
            confidence=0.9,
            verdict="probably_supported",
            rationale="Veredito fora do contrato.",
            issues=[],
        )


def test_validation_identifies_confidence_as_llm_rubric() -> None:
    validation = ValidationResult(
        variable_id="variable-001",
        confidence=0.91,
        verdict=ValidationVerdict.SUPPORTED,
        rationale="Valor diretamente sustentado.",
        issues=[],
    )

    assert validation.confidence == 0.91
    assert validation.confidence_basis is ConfidenceBasis.LLM_RUBRIC


@pytest.mark.parametrize(
    ("reviewed", "review_status"),
    [
        (True, ReviewStatus.PENDING),
        (False, ReviewStatus.CONFIRMED),
        (False, ReviewStatus.EDITED),
        (False, ReviewStatus.NOT_APPLICABLE),
    ],
)
def test_variable_rejects_review_flag_without_matching_human_status(
    reviewed: bool, review_status: ReviewStatus
) -> None:
    with pytest.raises(ValidationError):
        make_variable(reviewed=reviewed, review_status=review_status)


def make_validation(**updates: object) -> ValidationResult:
    data: dict[str, object] = {
        "variable_id": "variable-001",
        "confidence": 0.95,
        "verdict": ValidationVerdict.SUPPORTED,
        "rationale": "O valor está explícito no trecho-fonte.",
        "issues": [],
    }
    data.update(updates)
    return ValidationResult.model_validate(data)


def make_location(*, page_start: int = 4, page_end: int = 6) -> SectionLocation:
    return SectionLocation(
        title="Da emissão, aplicação e resgate de cotas",
        page_start=page_start,
        page_end=page_end,
        rationale="A seção reúne regras de aplicação e resgate.",
        confirmed=True,
    )


def test_pending_items_aggregates_score_verdict_and_conflict_reasons() -> None:
    run = make_run(state=RunState.REVIEWING)
    run.variables = [make_variable()]
    run.validations = [
        make_validation(
            confidence=0.7,
            verdict=ValidationVerdict.PARTIALLY_SUPPORTED,
            has_conflict=True,
        )
    ]

    pending = run.pending_items()

    assert len(pending) == 1
    assert pending[0].variable_id == "variable-001"
    assert set(pending[0].reasons) == {
        ReviewReason.LOW_CONFIDENCE,
        ReviewReason.VERDICT,
        ReviewReason.CONFLICT,
    }


def test_confidence_at_threshold_with_supported_verdict_is_not_pending() -> None:
    run = make_run(state=RunState.REVIEWING)
    run.variables = [make_variable()]
    run.validations = [make_validation(confidence=0.85)]

    assert run.pending_items() == []


def test_unsupported_verdict_is_pending_even_with_high_confidence() -> None:
    run = make_run(state=RunState.REVIEWING)
    run.variables = [make_variable()]
    run.validations = [make_validation(confidence=0.99, verdict=ValidationVerdict.UNSUPPORTED)]

    assert run.pending_items()[0].reasons == [ReviewReason.VERDICT]


def test_possible_omission_creates_its_own_pending_item() -> None:
    run = make_run(state=RunState.REVIEWING)
    run.coverage_findings = [
        CoverageFinding(
            id="finding-001",
            description="A seção cita uma carência sem variável correspondente.",
            suggested_name="carencia_resgate",
            evidence_text="O prazo de carência será de 30 dias.",
            source_pages=[5],
        )
    ]

    pending = run.pending_items()

    assert len(pending) == 1
    assert pending[0].finding_id == "finding-001"
    assert pending[0].reasons == [ReviewReason.OMISSION]


def test_explicit_human_review_marks_variable_and_resolves_pending_item() -> None:
    variable = make_variable()
    decision = ReviewDecision(
        variable_id=variable.id,
        action=ReviewAction.CONFIRM,
        previous_name=variable.current_name,
        previous_value=variable.current_value,
        resulting_name=variable.current_name,
        resulting_value=variable.current_value,
        reviewed_at=datetime(2026, 9, 27, 13, 0, tzinfo=UTC),
    )
    run = make_run(state=RunState.REVIEWING)
    run.variables = [variable.apply_review(decision)]
    run.validations = [make_validation(confidence=0.4)]

    assert variable.reviewed is True
    assert variable.review_status is ReviewStatus.CONFIRMED
    assert run.pending_items() == []


def test_final_export_is_blocked_while_any_review_item_is_pending() -> None:
    run = make_run(state=RunState.REVIEWING)
    run.variables = [make_variable()]
    run.validations = [make_validation(confidence=0.84)]

    assert run.can_export_final() is False
    with pytest.raises(ValueError, match="pending review items"):
        run.transition(RunState.FINAL_READY)


def test_final_export_is_allowed_when_no_review_item_is_pending() -> None:
    run = make_run(state=RunState.REVIEWING)
    run.variables = [make_variable()]
    run.validations = [make_validation(confidence=0.85)]

    assert run.can_export_final() is True
    assert run.transition(RunState.FINAL_READY).state is RunState.FINAL_READY


def test_changing_confirmed_pages_invalidates_all_downstream_artifacts() -> None:
    variable = make_variable(reviewed=True, review_status=ReviewStatus.CONFIRMED)
    run = make_run(state=RunState.FINAL_READY)
    run.location = make_location()
    run.variables = [variable]
    run.validations = [make_validation()]
    run.coverage_findings = [
        CoverageFinding(
            id="finding-001",
            description="Possível omissão.",
            evidence_text="Trecho de evidência.",
            source_pages=[5],
        )
    ]
    run.reviews = [
        ReviewDecision(
            variable_id=variable.id,
            action=ReviewAction.CONFIRM,
            resulting_name=variable.current_name,
            resulting_value=variable.current_value,
            reviewed_at=datetime(2026, 9, 27, 13, 0, tzinfo=UTC),
        )
    ]
    run.preliminary_export_path = "exports/preliminary.xlsx"
    run.final_export_path = "exports/final.xlsx"

    run.confirm_location(page_start=5, page_end=7)

    assert run.state is RunState.LOCATION_CONFIRMED
    assert (run.location.page_start, run.location.page_end) == (5, 7)
    assert run.variables == []
    assert run.validations == []
    assert run.coverage_findings == []
    assert run.reviews == []
    assert run.preliminary_export_path is None
    assert run.final_export_path is None


@pytest.mark.parametrize(
    "processing_state",
    [RunState.LOCATING, RunState.EXTRACTING, RunState.VALIDATING],
)
def test_confirming_pages_is_blocked_during_an_external_call(
    processing_state: RunState,
) -> None:
    run = make_run(state=processing_state)
    run.location = make_location()

    with pytest.raises(ValueError, match="external call is in progress"):
        run.confirm_location(page_start=5, page_end=7)


def make_decision(
    *,
    action: ReviewAction,
    variable_id: str = "variable-001",
    resulting_name: str | None = None,
    resulting_value: str | None = None,
) -> ReviewDecision:
    return ReviewDecision(
        variable_id=variable_id,
        action=action,
        resulting_name=resulting_name,
        resulting_value=resulting_value,
        reviewed_at=datetime(2026, 9, 27, 13, 0, tzinfo=UTC),
    )


def test_edit_review_changes_current_values_and_preserves_originals() -> None:
    variable = make_variable()

    variable.apply_review(
        make_decision(
            action=ReviewAction.EDIT,
            resulting_name="prazo_pagamento_resgate",
            resulting_value="30 dias corridos",
        )
    )

    assert variable.current_name == "prazo_pagamento_resgate"
    assert variable.current_value == "30 dias corridos"
    assert variable.original_name == "Prazo para pagamento do resgate"
    assert variable.original_value == "D+30"
    assert variable.review_status is ReviewStatus.EDITED


def test_not_applicable_review_sets_human_review_state() -> None:
    variable = make_variable()

    variable.apply_review(make_decision(action=ReviewAction.NOT_APPLICABLE))

    assert variable.reviewed is True
    assert variable.review_status is ReviewStatus.NOT_APPLICABLE


def test_review_rejects_a_decision_for_another_variable() -> None:
    variable = make_variable()

    with pytest.raises(ValueError, match="different variable"):
        variable.apply_review(
            make_decision(action=ReviewAction.CONFIRM, variable_id="variable-999")
        )


def test_existing_variable_rejects_add_missing_action() -> None:
    variable = make_variable()

    with pytest.raises(ValueError, match="creates a new variable"):
        variable.apply_review(make_decision(action=ReviewAction.ADD_MISSING))


def test_edit_review_requires_resulting_name_and_value() -> None:
    variable = make_variable()

    with pytest.raises(ValueError, match="requires resulting name and value"):
        variable.apply_review(make_decision(action=ReviewAction.EDIT))


@pytest.mark.parametrize(
    ("variable_id", "finding_id"),
    [(None, None), ("variable-001", "finding-001")],
)
def test_review_item_requires_exactly_one_target(
    variable_id: str | None, finding_id: str | None
) -> None:
    with pytest.raises(ValidationError):
        ReviewItem(
            item_id="review-001",
            kind=ReviewItemKind.VARIABLE,
            reasons=[ReviewReason.CONFLICT],
            variable_id=variable_id,
            finding_id=finding_id,
        )


def test_confirm_location_requires_a_candidate_location() -> None:
    run = make_run(state=RunState.LOCATION_READY)

    with pytest.raises(ValueError, match="section location is required"):
        run.confirm_location(page_start=4, page_end=6)


def test_confirming_unchanged_pages_preserves_downstream_artifacts() -> None:
    run = make_run(state=RunState.REVIEWING)
    run.location = make_location()
    run.variables = [make_variable()]
    run.validations = [make_validation()]

    run.confirm_location(page_start=4, page_end=6)

    assert len(run.variables) == 1
    assert len(run.validations) == 1


def test_pending_items_ignore_variables_that_have_not_been_validated() -> None:
    run = make_run(state=RunState.EXTRACTED)
    run.variables = [make_variable()]

    assert run.pending_items() == []


def test_pending_items_ignore_resolved_coverage_findings() -> None:
    run = make_run(state=RunState.REVIEWING)
    run.coverage_findings = [
        CoverageFinding(
            id="finding-001",
            description="Possível omissão já descartada.",
            evidence_text="Trecho de evidência.",
            source_pages=[5],
            review_status=FindingReviewStatus.DISMISSED,
        )
    ]

    assert run.pending_items() == []
