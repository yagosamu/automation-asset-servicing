"""Streamlit journeys for the active run, exports, and operational summaries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from asset_servicing.adapters.export import ExcelExporter
from asset_servicing.adapters.persistence import JsonRunRepository, RunEvent
from asset_servicing.application import ReviewService, RunDeliveryService
from asset_servicing.domain import (
    ExtractedVariable,
    ReviewStatus,
    Run,
    RunState,
    SectionLocation,
    SourceKind,
    ValidationResult,
    ValidationVerdict,
)
from asset_servicing.ui import app as ui_app

pytestmark = pytest.mark.ui

CREATED_AT = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def make_run(
    run_id: str,
    *,
    document_name: str,
    created_at: datetime,
    confidence: float = 0.72,
    verdict: ValidationVerdict = ValidationVerdict.PARTIALLY_SUPPORTED,
    value: str = "D+30",
) -> Run:
    return Run(
        run_id=run_id,
        document_name=document_name,
        document_sha256=run_id[-1] * 64,
        page_count=12,
        created_at=created_at,
        state=RunState.REVIEWING,
        location=SectionLocation(
            title="Emissão, aplicação e resgate",
            page_start=7,
            page_end=9,
            rationale="Intervalo confirmado pelo operador.",
            confirmed=True,
        ),
        variables=[
            ExtractedVariable(
                id=f"variable-{run_id}",
                canonical_name="prazo_resgate",
                original_name="prazo_resgate",
                original_value=value,
                current_name="prazo_resgate",
                current_value=value,
                evidence_text="O pagamento do resgate ocorrerá em até trinta dias.",
                source_pages=[8],
                source_kind=SourceKind.PROSE,
            )
        ],
        validations=[
            ValidationResult(
                variable_id=f"variable-{run_id}",
                confidence=confidence,
                verdict=verdict,
                rationale="Resultado confrontado com a fonte.",
                issues=[] if verdict is ValidationVerdict.SUPPORTED else ["Revisar contexto"],
            )
        ],
    )


def make_app(tmp_path: Path) -> tuple[AppTest, JsonRunRepository]:
    repository = JsonRunRepository(tmp_path / "runs")
    repository.save_run(
        make_run(
            "run-001",
            document_name="regulamento-antigo.pdf",
            created_at=CREATED_AT,
        )
    )
    repository.save_run(
        make_run(
            "run-002",
            document_name="regulamento-recente.pdf",
            created_at=CREATED_AT + timedelta(hours=1),
            value="D+5",
        )
    )
    delivery_service = RunDeliveryService(
        repository=repository,
        exporter=ExcelExporter(repository),
    )
    app = AppTest.from_file(Path(ui_app.__file__), default_timeout=30)
    app.session_state["_asset_servicing_delivery_service"] = delivery_service
    app.session_state["_asset_servicing_review_service"] = ReviewService(repository=repository)
    app.session_state["_asset_servicing_review_run_id"] = "run-002"
    return app.run(), repository


def make_summary_run() -> Run:
    run = make_run(
        "run-002",
        document_name="regulamento-recente.pdf",
        created_at=CREATED_AT + timedelta(hours=1),
        confidence=0.92,
        verdict=ValidationVerdict.SUPPORTED,
        value="D+5",
    )
    run.variables[0] = run.variables[0].model_copy(
        update={"reviewed": True, "review_status": ReviewStatus.CONFIRMED}
    )
    for suffix, confidence, verdict in (
        ("medium", 0.72, ValidationVerdict.PARTIALLY_SUPPORTED),
        ("low", 0.40, ValidationVerdict.UNSUPPORTED),
    ):
        variable_id = f"variable-{suffix}"
        run.variables.append(
            ExtractedVariable(
                id=variable_id,
                canonical_name=f"campo_{suffix}",
                original_name=f"campo_{suffix}",
                original_value=suffix,
                current_name=f"campo_{suffix}",
                current_value=suffix,
                evidence_text=f"Evidência {suffix}.",
                source_pages=[9],
                source_kind=SourceKind.TABLE,
            )
        )
        run.validations.append(
            ValidationResult(
                variable_id=variable_id,
                confidence=confidence,
                verdict=verdict,
                rationale=f"Validação {suffix}.",
                issues=["Revisar"],
            )
        )
    return run


def add_summary_events(repository: JsonRunRepository) -> None:
    for stage, duration_ms, model, prompt_version, total_tokens, attempts in (
        ("location", 1000, "locator-model", "locator-v1", 10, 1),
        ("extraction", 2000, "extractor-model", "extractor-v1", 20, 2),
        ("validation", 3000, "validator-model", "validator-v1", 30, 1),
    ):
        repository.append_event(
            RunEvent(
                run_id="run-002",
                stage=stage,
                event="stage_completed",
                status="success",
                started_at=CREATED_AT,
                duration_ms=duration_ms,
                model=model,
                prompt_version=prompt_version,
                input_pages=[7, 8, 9],
                usage={"total_tokens": total_tokens, "attempts": attempts},
            )
        )


def test_saved_run_selector_is_not_rendered_in_the_primary_flow(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)

    assert "Execuções salvas" not in [header.value for header in app.header]
    assert "saved_run" not in [selectbox.key for selectbox in app.selectbox]


def test_active_run_results_render_without_a_recovery_selection(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)

    overview = app.dataframe[0].value
    assert list(overview["Valor"]) == ["D+5"]
    assert list(overview["Confiança"]) == [0.72]
    assert list(overview["Nível"]) == ["🟡 Média"]


def test_variable_without_validation_is_visibly_unrated(tmp_path: Path) -> None:
    app, repository = make_app(tmp_path)
    run = repository.load_run("run-002")
    run.validations = []
    repository.save_run(run)

    app.run()

    assert list(app.dataframe[0].value["Nível"]) == ["⚪ Não avaliada"]


def test_refresh_preserves_the_active_run_and_progress(tmp_path: Path) -> None:
    app, _ = make_app(tmp_path)

    app.run()

    assert app.session_state["_asset_servicing_review_run_id"] == "run-002"
    assert list(app.dataframe[0].value["Valor"]) == ["D+5"]
    assert [metric.value for metric in app.metric[:3]] == ["1", "1", "0"]


def test_preliminary_workbook_is_generated_and_offered_with_pending_review(
    tmp_path: Path,
) -> None:
    app, repository = make_app(tmp_path)

    app.get_by_key("generate_preliminary").click().run()

    persisted = repository.load_run("run-002")
    assert persisted.pending_items()
    assert persisted.preliminary_export_path is not None
    export_path = Path(persisted.preliminary_export_path)
    assert export_path.is_file()
    assert export_path.name == "preliminary.xlsx"
    assert export_path.parent == repository.root / "run-002" / "exports"
    assert app.get_by_key("download_preliminary").proto.label == "Baixar Excel preliminar"


def test_preliminary_download_belongs_to_the_active_run(tmp_path: Path) -> None:
    app, repository = make_app(tmp_path)
    app.session_state["_asset_servicing_review_run_id"] = "run-001"
    app.run()

    app.get_by_key("generate_preliminary").click().run()

    selected = repository.load_run("run-001")
    untouched = repository.load_run("run-002")
    assert selected.preliminary_export_path is not None
    assert Path(selected.preliminary_export_path).parent == (
        repository.root / "run-001" / "exports"
    )
    assert untouched.preliminary_export_path is None


def test_final_workbook_is_blocked_and_pending_count_is_visible(tmp_path: Path) -> None:
    app, repository = make_app(tmp_path)

    final_button = app.get_by_key("generate_final")

    assert len(repository.load_run("run-002").pending_items()) == 1
    assert final_button.disabled is True
    assert any("1 pendência" in message.value for message in app.warning)
    assert len(app.download_button) == 0


def test_final_workbook_is_generated_after_the_queue_is_clear(tmp_path: Path) -> None:
    app, repository = make_app(tmp_path)
    repository.save_run(
        make_run(
            "run-002",
            document_name="regulamento-recente.pdf",
            created_at=CREATED_AT + timedelta(hours=1),
            confidence=0.97,
            verdict=ValidationVerdict.SUPPORTED,
            value="D+5",
        )
    )
    app.run()

    assert app.get_by_key("generate_final").disabled is False
    app.get_by_key("generate_final").click().run()

    persisted = repository.load_run("run-002")
    assert persisted.pending_items() == []
    assert persisted.final_export_path is not None
    final_path = Path(persisted.final_export_path)
    assert final_path.is_file()
    assert final_path.name == "final.xlsx"
    assert final_path.parent == repository.root / "run-002" / "exports"
    assert app.get_by_key("download_final").proto.label == "Baixar Excel final"


def test_existing_download_is_restored_after_refresh(tmp_path: Path) -> None:
    app, repository = make_app(tmp_path)
    app.get_by_key("generate_preliminary").click().run()
    persisted_path = repository.load_run("run-002").preliminary_export_path

    app.run()

    assert persisted_path is not None
    assert Path(persisted_path).is_file()
    assert app.get_by_key("download_preliminary").proto.label == "Baixar Excel preliminar"


def test_summary_shows_durations_counts_and_score_distribution(tmp_path: Path) -> None:
    app, repository = make_app(tmp_path)
    repository.save_run(make_summary_run())
    add_summary_events(repository)

    app.run()

    metrics = {metric.proto.label: metric.value for metric in app.metric}
    assert metrics["Duração total"] == "6,00 s"
    assert metrics["Variáveis extraídas"] == "3"
    assert metrics["Aprovadas"] == "1"
    assert metrics["Revisadas"] == "1"
    operational_details = next(
        expander for expander in app.expander if expander.label == "Detalhes operacionais"
    )
    assert operational_details.proto.expanded is False
    assert app.table[0].value.to_dict("records") == [
        {"Etapa": "location", "Duração": "1,00 s"},
        {"Etapa": "extraction", "Duração": "2,00 s"},
        {"Etapa": "validation", "Duração": "3,00 s"},
    ]
    assert any(
        "Alta (≥ 0,85): 1 · Média (0,50–0,84): 1 · Baixa (< 0,50): 1" in item.value
        for item in app.markdown
    )


def test_summary_shows_calls_retries_usage_models_and_prompts(tmp_path: Path) -> None:
    app, repository = make_app(tmp_path)
    repository.save_run(make_summary_run())
    add_summary_events(repository)

    app.run()

    metrics = {metric.proto.label: metric.value for metric in app.metric}
    assert metrics["Chamadas"] == "3"
    assert metrics["Retries"] == "1"
    assert any("total_tokens: 60" in item.value for item in app.markdown)
    assert any(
        "Modelos: locator-model, extractor-model, validator-model" in item.value
        for item in app.caption
    )
    assert any(
        "Versões de prompt: locator-v1, extractor-v1, validator-v1" in item.value
        for item in app.caption
    )
