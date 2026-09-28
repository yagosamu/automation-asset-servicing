"""Streamlit journeys for results and auditable human review."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from asset_servicing.application import ReviewService
from asset_servicing.domain import (
    CoverageFinding,
    ExtractedVariable,
    ReviewAction,
    ReviewStatus,
    Run,
    RunState,
    SourceKind,
    ValidationResult,
    ValidationVerdict,
)
from asset_servicing.ui import app as ui_app

pytestmark = pytest.mark.ui


class MemoryRunRepository:
    """Copying repository that exposes the same seam as local persistence."""

    def __init__(self, run: Run) -> None:
        self.run = run.model_copy(deep=True)

    def load_run(self, run_id: str) -> Run:
        if run_id != self.run.run_id:
            raise FileNotFoundError(run_id)
        return self.run.model_copy(deep=True)

    def save_run(self, run: Run) -> None:
        self.run = run.model_copy(deep=True)


def make_reviewing_run() -> Run:
    return Run(
        run_id="run-review-001",
        document_name="regulamento.pdf",
        document_sha256="c" * 64,
        page_count=12,
        created_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        state=RunState.REVIEWING,
        variables=[
            ExtractedVariable(
                id="variable-pending",
                canonical_name="prazo_resgate",
                original_name="prazo_resgate",
                original_value="D+30",
                current_name="prazo_resgate",
                current_value="D+30",
                evidence_text="O pagamento do resgate ocorrerá em até trinta dias.",
                source_pages=[7],
                source_kind=SourceKind.PROSE,
            ),
            ExtractedVariable(
                id="variable-supported",
                canonical_name="aplicacao_minima",
                original_name="aplicacao_minima",
                original_value="R$ 1.000,00",
                current_name="aplicacao_minima",
                current_value="R$ 1.000,00",
                evidence_text="A aplicação mínima é de mil reais.",
                source_pages=[8],
                source_kind=SourceKind.TABLE,
            ),
        ],
        validations=[
            ValidationResult(
                variable_id="variable-pending",
                confidence=0.72,
                verdict=ValidationVerdict.PARTIALLY_SUPPORTED,
                rationale="A redação exige revisão humana.",
                issues=["Prazo ambíguo"],
            ),
            ValidationResult(
                variable_id="variable-supported",
                confidence=0.97,
                verdict=ValidationVerdict.SUPPORTED,
                rationale="Valor integralmente suportado pela tabela.",
                issues=[],
            ),
        ],
        coverage_findings=[
            CoverageFinding(
                id="finding-pending",
                description="Possível carência de resgate omitida.",
                suggested_name="carencia_resgate",
                evidence_text="A carência consta da tabela.",
                source_pages=[9],
            )
        ],
    )


def make_app(run: Run | None = None) -> tuple[AppTest, MemoryRunRepository]:
    repository = MemoryRunRepository(run or make_reviewing_run())
    service = ReviewService(
        repository=repository,
        clock=lambda: datetime(2026, 9, 28, 18, 0, tzinfo=UTC),
        variable_id_factory=lambda: "variable-added",
    )
    app = AppTest.from_file(Path(ui_app.__file__), default_timeout=30)
    app.session_state["_asset_servicing_review_service"] = service
    app.session_state["_asset_servicing_review_run_id"] = repository.run.run_id
    return app.run(), repository


def test_results_overview_shows_every_variable_and_initial_counters() -> None:
    app, _ = make_app()

    overview = app.dataframe[0].value

    assert list(overview["Variável"]) == ["prazo_resgate", "aplicacao_minima"]
    assert list(overview["Valor"]) == ["D+30", "R$ 1.000,00"]
    assert list(overview["Foi revisado?"]) == [False, False]


def test_results_overview_includes_source_and_independent_validation() -> None:
    app, _ = make_app()

    overview = app.dataframe[0].value

    assert list(overview.columns) == [
        "Variável",
        "Valor",
        "Trecho-fonte",
        "Páginas",
        "Confiança",
        "Veredito",
        "Foi revisado?",
    ]
    assert overview.iloc[0].to_dict() == {
        "Variável": "prazo_resgate",
        "Valor": "D+30",
        "Trecho-fonte": "O pagamento do resgate ocorrerá em até trinta dias.",
        "Páginas": "7",
        "Confiança": 0.72,
        "Veredito": "partially_supported",
        "Foi revisado?": False,
    }


def test_loading_results_without_human_action_keeps_review_count_zero() -> None:
    app, repository = make_app()

    persisted = repository.load_run("run-review-001")

    assert [metric.value for metric in app.metric[:3]] == ["2", "2", "0"]
    assert [variable.reviewed for variable in persisted.variables] == [False, False]
    assert persisted.reviews == []


def test_review_queue_contains_only_pending_variables_and_omissions() -> None:
    app, _ = make_app()

    headings = [heading.value for heading in app.subheader]

    assert headings == [
        "Fila de revisão",
        "prazo_resgate",
        "Possível omissão",
    ]
    assert "aplicacao_minima" not in headings


def test_pending_variable_shows_value_page_score_verdict_and_rationale() -> None:
    app, _ = make_app()

    assert app.get_by_key("pending_name_variable-pending").value == "prazo_resgate"
    assert app.get_by_key("pending_value_variable-pending").value == "D+30"
    assert any("Página(s): 7" in caption.value for caption in app.caption)
    assert any("0,72" in item.value for item in app.markdown)
    assert any("parcialmente suportado" in item.value for item in app.markdown)
    assert any("A redação exige revisão humana." in item.value for item in app.info)


def test_pending_variable_evidence_is_visible_and_immutable() -> None:
    app, _ = make_app()

    evidence = app.get_by_key("evidence_variable-pending")

    assert evidence.value == "O pagamento do resgate ocorrerá em até trinta dias."
    assert evidence.disabled is True


def test_confirm_keeps_current_value_and_updates_persisted_counters() -> None:
    app, repository = make_app()

    app.get_by_key("confirm_note_variable-pending").set_value("Conferido na fonte.")
    app.get_by_key("confirm_variable-pending").click().run()

    persisted = repository.load_run("run-review-001")
    variable = persisted.variables[0]
    assert (variable.current_name, variable.current_value) == ("prazo_resgate", "D+30")
    assert variable.reviewed is True
    assert variable.review_status is ReviewStatus.CONFIRMED
    assert persisted.reviews[0].action is ReviewAction.CONFIRM
    assert persisted.reviews[0].note == "Conferido na fonte."
    assert [metric.value for metric in app.metric[:3]] == ["2", "1", "1"]
    assert any("Variável confirmada" in message.value for message in app.success)


def test_edit_changes_current_fields_and_preserves_original_evidence() -> None:
    app, repository = make_app()

    app.get_by_key("edit_name_variable-pending").set_value("prazo_pagamento_resgate")
    app.get_by_key("edit_value_variable-pending").set_value("até D+30")
    app.get_by_key("edit_note_variable-pending").set_value("Padronizado após leitura.")
    app.get_by_key("edit_variable-pending").click().run()

    persisted = repository.load_run("run-review-001")
    variable = persisted.variables[0]
    assert (variable.current_name, variable.current_value) == (
        "prazo_pagamento_resgate",
        "até D+30",
    )
    assert (variable.original_name, variable.original_value) == ("prazo_resgate", "D+30")
    assert variable.evidence_text == "O pagamento do resgate ocorrerá em até trinta dias."
    assert variable.review_status is ReviewStatus.EDITED
    assert persisted.reviews[0].action is ReviewAction.EDIT
    assert [metric.value for metric in app.metric[:3]] == ["2", "1", "1"]


def test_not_applicable_keeps_record_and_removes_it_from_the_queue() -> None:
    app, repository = make_app()

    app.get_by_key("not_applicable_note_variable-pending").set_value(
        "Regra não aplicável à classe."
    )
    app.get_by_key("not_applicable_variable-pending").click().run()

    persisted = repository.load_run("run-review-001")
    variable = persisted.variables[0]
    assert len(persisted.variables) == 2
    assert (variable.original_name, variable.original_value) == ("prazo_resgate", "D+30")
    assert variable.reviewed is True
    assert variable.review_status is ReviewStatus.NOT_APPLICABLE
    assert persisted.reviews[0].action is ReviewAction.NOT_APPLICABLE
    assert persisted.reviews[0].note == "Regra não aplicável à classe."
    assert [metric.value for metric in app.metric[:3]] == ["2", "1", "1"]


def test_omission_shows_source_context_and_editable_manual_fields() -> None:
    app, _ = make_app()

    description = app.get_by_key("finding_description_finding-pending")
    source_evidence = app.get_by_key("finding_evidence_finding-pending")
    manual_evidence = app.get_by_key("missing_evidence_finding-pending")

    assert description.value == "Possível carência de resgate omitida."
    assert description.disabled is True
    assert source_evidence.value == "A carência consta da tabela."
    assert source_evidence.disabled is True
    assert app.get_by_key("missing_name_finding-pending").value == "carencia_resgate"
    assert manual_evidence.value == "A carência consta da tabela."
    assert manual_evidence.disabled is False
    assert any("Página(s): 9" in caption.value for caption in app.caption)


def test_add_missing_creates_reviewed_variable_and_resolves_omission() -> None:
    app, repository = make_app()

    app.get_by_key("missing_value_finding-pending").set_value("30 dias")
    app.get_by_key("missing_evidence_finding-pending").set_value(
        "A carência para resgate é de trinta dias."
    )
    app.get_by_key("missing_note_finding-pending").set_value("Incluída após conferência.")
    app.get_by_key("add_missing_finding-pending").click().run()

    persisted = repository.load_run("run-review-001")
    added = persisted.variables[-1]
    assert (added.current_name, added.current_value) == ("carencia_resgate", "30 dias")
    assert (added.original_name, added.original_value) == ("carencia_resgate", "30 dias")
    assert added.evidence_text == "A carência para resgate é de trinta dias."
    assert added.source_pages == [9]
    assert added.source_kind is SourceKind.HUMAN_ADDED
    assert added.reviewed is True
    assert persisted.reviews[0].action is ReviewAction.ADD_MISSING
    assert persisted.coverage_findings[0].review_status.value == "accepted"
    assert list(app.dataframe[0].value["Variável"])[-1] == "carencia_resgate"
    assert [metric.value for metric in app.metric[:3]] == ["3", "1", "1"]


def test_completed_review_shows_empty_queue_state() -> None:
    run = make_reviewing_run()
    run.variables = [run.variables[1]]
    run.validations = [run.validations[1]]
    run.coverage_findings = []

    app, _ = make_app(run)

    assert [metric.value for metric in app.metric[:3]] == ["1", "0", "0"]
    assert app.subheader == []
    assert any("Não há pendências" in message.value for message in app.success)
