"""Integration tests for persisted and restartable human review."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from asset_servicing.adapters.persistence import JsonRunRepository
from asset_servicing.application import ReviewService
from asset_servicing.application.review_service import RunRepository
from asset_servicing.domain import (
    CoverageFinding,
    ExtractedVariable,
    FindingReviewStatus,
    ReviewAction,
    ReviewStatus,
    Run,
    RunState,
    SectionLocation,
    SourceKind,
    ValidationResult,
    ValidationVerdict,
)

pytestmark = pytest.mark.integration


def make_reviewing_run() -> Run:
    return Run(
        run_id="run-001",
        document_name="regulamento.pdf",
        document_sha256="b" * 64,
        page_count=10,
        created_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        state=RunState.REVIEWING,
        location=SectionLocation(
            title="Movimentação de cotas",
            page_start=7,
            page_end=8,
            rationale="Intervalo confirmado pelo operador.",
            confirmed=True,
        ),
        variables=[
            ExtractedVariable(
                id="variable-001",
                canonical_name="prazo_resgate",
                original_name="prazo_resgate",
                original_value="D+30",
                current_name="prazo_resgate",
                current_value="D+30",
                evidence_text="O resgate será pago em até trinta dias.",
                source_pages=[7],
                source_kind=SourceKind.PROSE,
            )
        ],
        validations=[
            ValidationResult(
                variable_id="variable-001",
                confidence=0.62,
                verdict=ValidationVerdict.PARTIALLY_SUPPORTED,
                rationale="A redação requer confirmação.",
                issues=["Prazo condicionado"],
            )
        ],
        coverage_findings=[
            CoverageFinding(
                id="finding-001",
                description="Possível taxa de saída omitida.",
                suggested_name="taxa_saida",
                evidence_text="A tabela prevê taxa de saída.",
                source_pages=[8],
            )
        ],
    )


def make_service(repository: RunRepository) -> ReviewService:
    return ReviewService(
        repository=repository,
        clock=lambda: datetime(2026, 9, 28, 16, 0, tzinfo=UTC),
        variable_id_factory=lambda: "variable-added-001",
    )


def test_new_service_instance_restores_pages_results_queue_and_decisions(tmp_path: Path) -> None:
    repository = JsonRunRepository(tmp_path / "runs")
    repository.save_run(make_reviewing_run())
    service = make_service(repository)
    service.edit(
        "run-001",
        "variable-001",
        name="prazo_pagamento_resgate",
        value="até D+30",
        note="Confirmado no artigo.",
    )
    service.add_missing(
        "run-001",
        "finding-001",
        name="taxa_saida",
        value="2%",
        evidence="A taxa de saída será de dois por cento.",
    )

    reopened = make_service(JsonRunRepository(tmp_path / "runs")).get_run("run-001")

    assert reopened.location is not None
    assert (reopened.location.page_start, reopened.location.page_end) == (7, 8)
    assert reopened.location.confirmed is True
    assert [(item.current_name, item.current_value) for item in reopened.variables] == [
        ("prazo_pagamento_resgate", "até D+30"),
        ("taxa_saida", "2%"),
    ]
    assert reopened.validations[0].confidence == 0.62
    assert [decision.action for decision in reopened.reviews] == [
        ReviewAction.EDIT,
        ReviewAction.ADD_MISSING,
    ]
    assert reopened.pending_items() == []


def test_failed_save_does_not_expose_an_unpersisted_review(tmp_path: Path) -> None:
    repository = JsonRunRepository(tmp_path / "runs")
    repository.save_run(make_reviewing_run())

    class FailingSaveRepository:
        def load_run(self, run_id: str) -> Run:
            return repository.load_run(run_id)

        def save_run(self, run: Run) -> None:
            raise OSError("storage unavailable")

    service = make_service(FailingSaveRepository())

    with pytest.raises(OSError, match="storage unavailable"):
        service.confirm("run-001", "variable-001")

    persisted = repository.load_run("run-001")
    assert persisted.variables[0].reviewed is False
    assert persisted.variables[0].review_status is ReviewStatus.PENDING
    assert persisted.reviews == []


def test_dismissed_omission_is_restored_without_reentering_the_queue(tmp_path: Path) -> None:
    run = make_reviewing_run()
    run.variables = []
    run.validations = []
    repository = JsonRunRepository(tmp_path / "runs")
    repository.save_run(run)

    make_service(repository).dismiss_omission(
        "run-001",
        "finding-001",
        note="Fora da seção-alvo.",
    )

    reopened = make_service(JsonRunRepository(tmp_path / "runs")).get_run("run-001")
    decision = reopened.reviews[0]
    assert reopened.coverage_findings[0].review_status is FindingReviewStatus.DISMISSED
    assert decision.action is ReviewAction.DISMISS_OMISSION
    assert decision.finding_id == "finding-001"
    assert decision.note == "Fora da seção-alvo."
    assert reopened.pending_items() == []
