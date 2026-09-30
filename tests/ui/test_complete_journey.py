"""Complete offline Streamlit journeys over the real local adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import cycle
from pathlib import Path

import pymupdf
import pytest
import yaml
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from asset_servicing.adapters.export import ExcelExporter
from asset_servicing.adapters.pdf import PdfProcessor
from asset_servicing.adapters.persistence import JsonRunRepository
from asset_servicing.application import (
    AgentModels,
    RegulationPipeline,
    RegulationSectionLocator,
    RegulationVariableExtractor,
    RegulationVariableValidator,
    ReviewService,
    RunDeliveryService,
    UsageLedger,
)
from asset_servicing.domain import ValidationVerdict
from asset_servicing.ports.llm import (
    AtomicVariable,
    EvidenceSupport,
    ExtractionRequest,
    ExtractionResponse,
    ExtractionSourceKind,
    LocateRequest,
    LocateResponse,
    LocationStatus,
    ValidationRequest,
    ValidationResponse,
    VariableValidation,
)
from asset_servicing.ui import app as ui_app

pytestmark = [pytest.mark.ui, pytest.mark.integration]

CREATED_AT = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


class RecordedProvider:
    """Deterministic three-agent provider with no network boundary."""

    def __init__(self) -> None:
        self.location = LocateResponse(
            status=LocationStatus.FOUND,
            title="CAPÍTULO 3 – DA EMISSÃO, APLICAÇÃO E RESGATE DE COTAS",
            page_start=2,
            page_end=3,
            rationale="As páginas concentram as regras de aplicação e resgate.",
        )
        self.extract_failures: list[Exception] = []
        self.locate_requests: list[LocateRequest] = []
        self.extract_requests: list[ExtractionRequest] = []
        self.validate_requests: list[ValidationRequest] = []

    def locate(self, request: LocateRequest) -> LocateResponse:
        self.locate_requests.append(request)
        return self.location

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        self.extract_requests.append(request)
        if self.extract_failures:
            raise self.extract_failures.pop(0)
        return ExtractionResponse(
            variables=[
                AtomicVariable(
                    name="prazo_pagamento_resgate",
                    value="D+30",
                    evidence_text="O pagamento do resgate ocorrerá em até trinta dias.",
                    source_pages=[request.page_start],
                    source_kind=ExtractionSourceKind.PROSE,
                    clause_reference="Art. 10",
                ),
                AtomicVariable(
                    name="aplicacao_minima",
                    value="R$ 1.000,00",
                    evidence_text="A aplicação mínima é de mil reais.",
                    source_pages=[request.page_end],
                    source_kind=ExtractionSourceKind.TABLE,
                ),
            ]
        )

    def validate(self, request: ValidationRequest) -> ValidationResponse:
        self.validate_requests.append(request)
        low_confidence, supported = request.variables
        return ValidationResponse(
            validations=[
                VariableValidation(
                    variable_id=low_confidence.variable_id,
                    confidence=0.72,
                    evidence_support=EvidenceSupport.PARTIAL,
                    verdict=ValidationVerdict.PARTIALLY_SUPPORTED,
                    rationale="O prazo exige confirmação humana.",
                    issues=["Redação ambígua"],
                ),
                VariableValidation(
                    variable_id=supported.variable_id,
                    confidence=0.97,
                    evidence_support=EvidenceSupport.LITERAL,
                    verdict=ValidationVerdict.SUPPORTED,
                    rationale="Valor diretamente sustentado pela tabela.",
                    issues=[],
                ),
            ],
            omissions=[],
        )


@dataclass(slots=True)
class JourneyHarness:
    app: AppTest
    provider: RecordedProvider
    repository: JsonRunRepository
    delivery: RunDeliveryService


def _make_pdf(path: Path, *, pages: int = 4) -> None:
    document = pymupdf.open()
    try:
        for page_number in range(1, pages + 1):
            page = document.new_page()
            page.insert_text((72, 72), f"Página {page_number} do regulamento")
        document.save(path)
    finally:
        document.close()


def _make_harness(
    tmp_path: Path,
    *,
    pages: int = 4,
    additional_pdf: bool = False,
) -> JourneyHarness:
    regulations_dir = tmp_path / "Regulamentos"
    regulations_dir.mkdir()
    _make_pdf(regulations_dir / "regulamento-e2e.pdf", pages=pages)
    if additional_pdf:
        _make_pdf(regulations_dir / "regulamento-seguinte.pdf", pages=pages)
    repository = JsonRunRepository(tmp_path / "runs")
    provider = RecordedProvider()
    variable_ids = cycle(("variable-low", "variable-supported"))
    pipeline = RegulationPipeline(
        repository=repository,
        pdf_processor=PdfProcessor(),
        locator=RegulationSectionLocator(provider),
        extractor=RegulationVariableExtractor(provider, id_factory=lambda: next(variable_ids)),
        validator=RegulationVariableValidator(provider),
        models=AgentModels(
            locator="recorded-locator",
            extractor="recorded-extractor",
            validator="recorded-validator",
        ),
        usage_ledger=UsageLedger(),
        run_id_factory=lambda: "run-e2e",
        clock=lambda: CREATED_AT,
    )
    delivery = RunDeliveryService(repository=repository, exporter=ExcelExporter(repository))
    app = AppTest.from_file(Path(ui_app.__file__), default_timeout=30)
    app.session_state["_asset_servicing_pipeline"] = pipeline
    app.session_state["_asset_servicing_regulations_dir"] = regulations_dir
    app.session_state["_asset_servicing_upload_dir"] = tmp_path / "uploads"
    app.session_state["_asset_servicing_review_service"] = ReviewService(
        repository=repository,
        clock=lambda: CREATED_AT,
    )
    app.session_state["_asset_servicing_delivery_service"] = delivery
    return JourneyHarness(
        app=app.run(),
        provider=provider,
        repository=repository,
        delivery=delivery,
    )


def _locate_confirm_and_process(harness: JourneyHarness) -> AppTest:
    app = harness.app
    app.get_by_key("start_location").click().run()
    app.get_by_key("confirm_location").click().run()
    return app.get_by_key("start_extraction").click().run()


def _reopen_download(data: bytes, destination: Path) -> tuple[list[object], list[object]]:
    destination.write_bytes(data)
    workbook = load_workbook(destination, data_only=False)
    try:
        variables = workbook["Variáveis"]
        headers = [cell.value for cell in variables[1]]
        first_row = [cell.value for cell in variables[2]]
        return headers, first_row
    finally:
        workbook.close()


def test_complete_journey_reviews_low_confidence_and_downloads_workbooks(
    tmp_path: Path,
) -> None:
    harness = _make_harness(tmp_path)

    app = _locate_confirm_and_process(harness)

    assert [request.page_start for request in harness.provider.extract_requests] == [2]
    assert len(harness.provider.validate_requests) == 1
    assert list(app.dataframe[0].value["Variável"]) == [
        "prazo_pagamento_resgate",
        "aplicacao_minima",
    ]
    assert "Execuções salvas" not in [header.value for header in app.header]
    assert "saved_run" not in [selectbox.key for selectbox in app.selectbox]
    assert app.get_by_key("generate_final").disabled is True
    assert any("1 pendência" in warning.value for warning in app.warning)

    app.get_by_key("generate_preliminary").click().run()
    preliminary = harness.delivery.get_export("run-e2e", final=False)
    assert preliminary is not None
    preliminary_headers, preliminary_row = _reopen_download(
        preliminary.data,
        tmp_path / "downloaded-preliminary.xlsx",
    )
    assert preliminary_headers == [
        "Variável",
        "Valor da variável",
        "Trecho da variável",
        "Grau de Confiança",
        "Foi revisado?",
    ]
    assert preliminary_row == [
        "prazo_pagamento_resgate",
        "D+30",
        "O pagamento do resgate ocorrerá em até trinta dias.",
        0.72,
        False,
    ]

    app.get_by_key("edit_name_variable-low").set_value("prazo_resgate")
    app.get_by_key("edit_value_variable-low").set_value("até D+30")
    app.get_by_key("edit_variable-low").click().run()
    assert app.get_by_key("generate_final").disabled is False

    app.get_by_key("generate_final").click().run()
    final = harness.delivery.get_export("run-e2e", final=True)
    assert final is not None
    final_headers, final_row = _reopen_download(
        final.data,
        tmp_path / "downloaded-final.xlsx",
    )
    assert final_headers == preliminary_headers
    assert final_row == [
        "prazo_resgate",
        "até D+30",
        "O pagamento do resgate ocorrerá em até trinta dias.",
        0.72,
        True,
    ]


def test_chapter_six_location_accepts_manual_page_correction(tmp_path: Path) -> None:
    fixture_path = Path(__file__).parents[2] / "evals" / "golden" / "v1" / "chapter_6_fixture.yaml"
    fixture = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))["recorded_output"]
    harness = _make_harness(tmp_path, pages=24)
    harness.provider.location = LocateResponse(
        status=LocationStatus.FOUND,
        title=fixture["title"],
        page_start=fixture["page_start"],
        page_end=fixture["page_end"],
        rationale=fixture["rationale"],
    )

    app = harness.app
    app.get_by_key("chapter_hint").set_value(6).run()
    app.get_by_key("start_location").click().run()
    app.get_by_key("confirmed_page_start").set_value(19).run()
    app.get_by_key("confirmed_page_end").set_value(22).run()
    app.get_by_key("refresh_preview").click().run()
    app.get_by_key("confirm_location").click().run()
    app.get_by_key("start_extraction").click().run()

    assert harness.provider.locate_requests[0].chapter_hint == 6
    assert "CAPÍTULO 6" in app.subheader[0].value
    extraction = harness.provider.extract_requests[0]
    validation = harness.provider.validate_requests[0]
    assert (extraction.page_start, extraction.page_end) == (19, 22)
    assert (validation.page_start, validation.page_end) == (19, 22)
    assert harness.repository.load_run("run-e2e").location is not None
    assert harness.repository.load_run("run-e2e").location.confirmed is True


def test_refresh_restores_review_progress_and_preliminary_download(tmp_path: Path) -> None:
    harness = _make_harness(tmp_path)
    app = _locate_confirm_and_process(harness)
    app.get_by_key("generate_preliminary").click().run()

    app.run()

    assert app.session_state["_asset_servicing_review_run_id"] == "run-e2e"
    assert app.get_by_key("download_preliminary").proto.label == "Baixar Excel preliminar"

    app.get_by_key("confirm_variable-low").click().run()

    app.run()

    persisted = harness.repository.load_run("run-e2e")
    assert persisted.pending_items() == []
    assert persisted.variables[0].reviewed is True
    assert app.session_state["_asset_servicing_review_run_id"] == "run-e2e"
    assert harness.delivery.get_export("run-e2e", final=False) is None
    assert app.get_by_key("generate_final").disabled is False
    assert list(app.dataframe[0].value["Foi revisado?"]) == [True, False]


def test_selecting_another_regulation_clears_the_previous_visible_run(
    tmp_path: Path,
) -> None:
    harness = _make_harness(tmp_path, additional_pdf=True)
    app = _locate_confirm_and_process(harness)

    assert len(app.dataframe) == 1
    assert len(harness.repository.list_runs()) == 1

    app.get_by_key("project_pdf").select("regulamento-seguinte.pdf").run()

    assert "_asset_servicing_review_run_id" not in app.session_state
    assert len(app.dataframe) == 0
    assert len(app.image) == 0
    assert {
        "Resultados e revisão",
        "Resumo operacional",
        "Arquivos da execução",
    }.isdisjoint(header.value for header in app.header)
    assert len(harness.repository.list_runs()) == 1


def test_failed_extraction_can_retry_without_recreating_the_run(tmp_path: Path) -> None:
    harness = _make_harness(tmp_path)
    harness.provider.extract_failures = [RuntimeError("falha transitória gravada")]
    app = harness.app
    app.get_by_key("start_location").click().run()
    app.get_by_key("confirm_location").click().run()

    app.get_by_key("start_extraction").click().run()

    assert any("falha transitória gravada" in error.value for error in app.error)
    assert any("progresso foi preservado" in info.value for info in app.info)
    assert harness.repository.list_runs()[0].run_id == "run-e2e"

    app.get_by_key("start_extraction").click().run()

    assert len(harness.repository.list_runs()) == 1
    assert len(harness.provider.extract_requests) == 2
    assert len(harness.provider.validate_requests) == 1
    assert list(app.dataframe[0].value["Variável"]) == [
        "prazo_pagamento_resgate",
        "aplicacao_minima",
    ]
