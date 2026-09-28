"""Unit tests for auditable human review decisions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from asset_servicing.application import ReviewService
from asset_servicing.domain import (
    CoverageFinding,
    ExtractedVariable,
    FindingReviewStatus,
    ReviewAction,
    ReviewStatus,
    Run,
    RunState,
    SourceKind,
    ValidationResult,
    ValidationVerdict,
)

REVIEWED_AT = datetime(2026, 9, 28, 15, 30, tzinfo=UTC)


class MemoryRunRepository:
    """Persistence seam with copy semantics matching the JSON repository."""

    def __init__(self, run: Run) -> None:
        self.run = run.model_copy(deep=True)

    def load_run(self, run_id: str) -> Run:
        if run_id != self.run.run_id:
            raise FileNotFoundError(run_id)
        return self.run.model_copy(deep=True)

    def save_run(self, run: Run) -> None:
        self.run = run.model_copy(deep=True)


def make_run() -> Run:
    return Run(
        run_id="run-001",
        document_name="regulamento.pdf",
        document_sha256="a" * 64,
        page_count=12,
        created_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        state=RunState.REVIEWING,
        variables=[
            ExtractedVariable(
                id="variable-001",
                canonical_name="prazo_resgate",
                original_name="prazo_resgate",
                original_value="D+30",
                current_name="prazo_resgate",
                current_value="D+30",
                evidence_text="O pagamento do resgate ocorrerá em até trinta dias.",
                source_pages=[7],
                source_kind=SourceKind.PROSE,
                clause_reference="Art. 12",
            )
        ],
        validations=[
            ValidationResult(
                variable_id="variable-001",
                confidence=0.72,
                verdict=ValidationVerdict.PARTIALLY_SUPPORTED,
                rationale="A redação exige revisão humana.",
                issues=["Prazo ambíguo"],
            )
        ],
        coverage_findings=[
            CoverageFinding(
                id="finding-001",
                description="Possível carência de resgate omitida.",
                suggested_name="carencia_resgate",
                evidence_text="A carência consta da tabela.",
                source_pages=[8],
            )
        ],
        preliminary_export_path="exports/preliminary.xlsx",
        final_export_path="exports/final.xlsx",
    )


def make_service(repository: MemoryRunRepository) -> ReviewService:
    return ReviewService(
        repository=repository,
        clock=lambda: REVIEWED_AT,
        variable_id_factory=lambda: "variable-added-001",
    )


def test_confirm_marks_variable_reviewed_and_records_before_and_after() -> None:
    repository = MemoryRunRepository(make_run())
    service = make_service(repository)

    variable = service.confirm("run-001", "variable-001", note="Conferido na fonte.")

    persisted = repository.load_run("run-001")
    decision = persisted.reviews[0]
    assert variable.reviewed is True
    assert variable.review_status is ReviewStatus.CONFIRMED
    assert decision.action is ReviewAction.CONFIRM
    assert (decision.previous_name, decision.previous_value) == ("prazo_resgate", "D+30")
    assert (decision.resulting_name, decision.resulting_value) == ("prazo_resgate", "D+30")
    assert decision.note == "Conferido na fonte."
    assert decision.reviewed_at == REVIEWED_AT
    assert persisted.pending_items()[0].finding_id == "finding-001"


def test_edit_changes_current_fields_without_changing_original_source() -> None:
    repository = MemoryRunRepository(make_run())
    service = make_service(repository)

    variable = service.edit(
        "run-001",
        "variable-001",
        name="prazo_pagamento_resgate",
        value="até D+30",
        note="Padronização após leitura do artigo.",
    )

    persisted = repository.load_run("run-001")
    decision = persisted.reviews[0]
    assert (variable.current_name, variable.current_value) == (
        "prazo_pagamento_resgate",
        "até D+30",
    )
    assert (variable.original_name, variable.original_value) == ("prazo_resgate", "D+30")
    assert variable.evidence_text == "O pagamento do resgate ocorrerá em até trinta dias."
    assert variable.source_pages == [7]
    assert decision.action is ReviewAction.EDIT
    assert (decision.previous_name, decision.previous_value) == ("prazo_resgate", "D+30")
    assert (decision.resulting_name, decision.resulting_value) == (
        "prazo_pagamento_resgate",
        "até D+30",
    )


def test_loading_without_human_action_keeps_variable_unreviewed() -> None:
    repository = MemoryRunRepository(make_run())
    service = make_service(repository)

    run = service.get_run("run-001")

    assert run.variables[0].reviewed is False
    assert run.variables[0].review_status is ReviewStatus.PENDING
    assert run.reviews == []


def test_mark_not_applicable_resolves_variable_and_records_note() -> None:
    repository = MemoryRunRepository(make_run())
    service = make_service(repository)

    variable = service.mark_not_applicable(
        "run-001",
        "variable-001",
        note="Regra não se aplica a esta classe.",
    )

    persisted = repository.load_run("run-001")
    decision = persisted.reviews[0]
    assert variable.reviewed is True
    assert variable.review_status is ReviewStatus.NOT_APPLICABLE
    assert (variable.current_name, variable.current_value) == ("prazo_resgate", "D+30")
    assert decision.action is ReviewAction.NOT_APPLICABLE
    assert decision.note == "Regra não se aplica a esta classe."
    assert persisted.preliminary_export_path is None
    assert persisted.final_export_path is None


def test_add_missing_accepts_finding_and_creates_reviewed_human_variable() -> None:
    run = make_run()
    run.variables = []
    run.validations = []
    repository = MemoryRunRepository(run)
    service = make_service(repository)

    variable = service.add_missing(
        "run-001",
        "finding-001",
        name="carencia_resgate",
        value="30 dias",
        evidence="A carência para resgate é de trinta dias.",
        note="Incluída após conferência da tabela.",
    )

    persisted = repository.load_run("run-001")
    finding = persisted.coverage_findings[0]
    decision = persisted.reviews[0]
    assert variable.id == "variable-added-001"
    assert variable.source_kind is SourceKind.HUMAN_ADDED
    assert variable.source_pages == [8]
    assert variable.evidence_text == "A carência para resgate é de trinta dias."
    assert variable.reviewed is True
    assert variable.review_status is ReviewStatus.CONFIRMED
    assert finding.review_status is FindingReviewStatus.ACCEPTED
    assert decision.variable_id == variable.id
    assert decision.action is ReviewAction.ADD_MISSING
    assert (decision.previous_name, decision.previous_value) == (None, None)
    assert (decision.resulting_name, decision.resulting_value) == (
        "carencia_resgate",
        "30 dias",
    )
    assert persisted.pending_items() == []


def test_review_action_rejects_run_outside_reviewing_state() -> None:
    run = make_run()
    run.state = RunState.EXTRACTED
    repository = MemoryRunRepository(run)
    service = make_service(repository)

    with pytest.raises(ValueError, match="reviewing state"):
        service.confirm("run-001", "variable-001")

    assert repository.load_run("run-001").reviews == []


def test_review_action_rejects_unknown_variable() -> None:
    repository = MemoryRunRepository(make_run())
    service = make_service(repository)

    with pytest.raises(ValueError, match="variable not found"):
        service.confirm("run-001", "variable-unknown")

    assert repository.load_run("run-001").reviews == []


def test_review_action_rejects_variable_already_reviewed() -> None:
    repository = MemoryRunRepository(make_run())
    service = make_service(repository)
    service.confirm("run-001", "variable-001")

    with pytest.raises(ValueError, match="already reviewed"):
        service.confirm("run-001", "variable-001")

    assert len(repository.load_run("run-001").reviews) == 1


def test_add_missing_rejects_unknown_finding() -> None:
    repository = MemoryRunRepository(make_run())
    service = make_service(repository)

    with pytest.raises(ValueError, match="coverage finding not found"):
        service.add_missing(
            "run-001",
            "finding-unknown",
            name="carencia_resgate",
            value="30 dias",
            evidence="A carência é de trinta dias.",
        )

    assert len(repository.load_run("run-001").variables) == 1


def test_add_missing_rejects_finding_already_reviewed() -> None:
    run = make_run()
    run.coverage_findings[0].review_status = FindingReviewStatus.ACCEPTED
    repository = MemoryRunRepository(run)
    service = make_service(repository)

    with pytest.raises(ValueError, match="already reviewed"):
        service.add_missing(
            "run-001",
            "finding-001",
            name="carencia_resgate",
            value="30 dias",
            evidence="A carência é de trinta dias.",
        )

    assert len(repository.load_run("run-001").variables) == 1


@pytest.mark.parametrize(("field", "value"), [("name", ""), ("value", "   ")])
def test_edit_rejects_blank_current_fields(field: str, value: str) -> None:
    repository = MemoryRunRepository(make_run())
    service = make_service(repository)
    arguments = {"name": "prazo_pagamento_resgate", "value": "D+30"}
    arguments[field] = value

    with pytest.raises(ValueError, match=field):
        service.edit("run-001", "variable-001", **arguments)

    persisted = repository.load_run("run-001")
    assert persisted.variables[0].reviewed is False
    assert persisted.reviews == []


def test_mark_not_applicable_requires_a_non_blank_note() -> None:
    repository = MemoryRunRepository(make_run())
    service = make_service(repository)

    with pytest.raises(ValueError, match="note"):
        service.mark_not_applicable("run-001", "variable-001", note="   ")

    assert repository.load_run("run-001").variables[0].reviewed is False


@pytest.mark.parametrize("field", ["name", "value", "evidence"])
def test_add_missing_rejects_blank_manual_fields(field: str) -> None:
    repository = MemoryRunRepository(make_run())
    service = make_service(repository)
    arguments = {
        "name": "carencia_resgate",
        "value": "30 dias",
        "evidence": "A carência é de trinta dias.",
    }
    arguments[field] = "   "

    with pytest.raises(ValueError, match=field):
        service.add_missing("run-001", "finding-001", **arguments)

    persisted = repository.load_run("run-001")
    assert len(persisted.variables) == 1
    assert persisted.coverage_findings[0].review_status is FindingReviewStatus.PENDING


def test_add_missing_rejects_duplicate_generated_variable_id() -> None:
    repository = MemoryRunRepository(make_run())
    service = ReviewService(
        repository=repository,
        clock=lambda: REVIEWED_AT,
        variable_id_factory=lambda: "variable-001",
    )

    with pytest.raises(ValueError, match="variable id already exists"):
        service.add_missing(
            "run-001",
            "finding-001",
            name="carencia_resgate",
            value="30 dias",
            evidence="A carência é de trinta dias.",
        )

    assert len(repository.load_run("run-001").variables) == 1
