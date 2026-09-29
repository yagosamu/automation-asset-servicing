"""Integration tests for the persisted, resumable processing pipeline."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier, Event, Thread
from types import SimpleNamespace

import pymupdf
import pytest

from asset_servicing.adapters.export import ExcelExporter
from asset_servicing.adapters.pdf import PdfProcessor
from asset_servicing.adapters.persistence import JsonRunRepository
from asset_servicing.application import (
    AgentModels,
    PipelineBusyError,
    RegulationPipeline,
    RegulationSectionLocator,
    RegulationVariableExtractor,
    RegulationVariableValidator,
    UsageLedger,
)
from asset_servicing.domain import RunState, ValidationVerdict
from asset_servicing.ports.llm import (
    AtomicVariable,
    ExtractionRequest,
    ExtractionResponse,
    ExtractionSourceKind,
    LocateRequest,
    LocateResponse,
    LocationStatus,
    OmissionFinding,
    ValidationRequest,
    ValidationResponse,
    VariableValidation,
)

pytestmark = pytest.mark.integration


class StepTimer:
    def __init__(self, step: float = 0.125) -> None:
        self.value = 10.0 - step
        self.step = step

    def __call__(self) -> float:
        self.value += self.step
        return self.value


class FakeLLMProvider:
    """Deterministic provider with one outcome queue per independent agent."""

    def __init__(self, usage_ledger: UsageLedger) -> None:
        self.usage_ledger = usage_ledger
        self.locate_outcomes: list[LocateResponse | Exception] = [
            LocateResponse(
                status=LocationStatus.FOUND,
                title="Seção de movimentações",
                page_start=2,
                page_end=3,
                rationale="As páginas reúnem aplicação e resgate.",
            )
        ]
        self.extract_outcomes: list[ExtractionResponse | Exception] = [
            ExtractionResponse(
                variables=[
                    AtomicVariable(
                        name="prazo_pagamento_resgate",
                        value="D+5",
                        evidence_text="O pagamento ocorrerá em até cinco dias.",
                        source_pages=[2],
                        source_kind=ExtractionSourceKind.PROSE,
                        clause_reference="Art. 10",
                    )
                ]
            )
        ]
        self.validate_outcomes: list[ValidationResponse | Exception] = [
            ValidationResponse(
                validations=[
                    VariableValidation(
                        variable_id="variable-001",
                        confidence=0.97,
                        verdict=ValidationVerdict.SUPPORTED,
                        rationale="Valor diretamente sustentado.",
                        issues=[],
                    )
                ],
                omissions=[],
            )
        ]
        self.locate_requests: list[LocateRequest] = []
        self.extract_requests: list[ExtractionRequest] = []
        self.validate_requests: list[ValidationRequest] = []
        self.on_call: Callable[[str], None] | None = None

    def locate(self, request: LocateRequest) -> LocateResponse:
        self.locate_requests.append(request)
        return self._complete("locator", self.locate_outcomes)

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        self.extract_requests.append(request)
        return self._complete("extractor", self.extract_outcomes)

    def validate(self, request: ValidationRequest) -> ValidationResponse:
        self.validate_requests.append(request)
        return self._complete("validator", self.validate_outcomes)

    def _complete(self, agent: str, outcomes: list[object]) -> object:
        if self.on_call is not None:
            self.on_call(agent)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        self.usage_ledger.record(
            SimpleNamespace(
                agent=agent,
                model=f"{agent}-model",
                prompt_version=f"{agent}-v1",
                response_id=f"response-{agent}",
                input_tokens=100,
                output_tokens=25,
                total_tokens=125,
                attempts=1,
            )
        )
        return outcome


@dataclass(slots=True)
class PipelineHarness:
    pipeline: RegulationPipeline
    repository: JsonRunRepository
    provider: FakeLLMProvider
    source_pdf: Path


def make_pdf(path: Path, *, pages: int = 4) -> None:
    document = pymupdf.open()
    try:
        for page_number in range(1, pages + 1):
            page = document.new_page()
            page.insert_text((72, 72), f"Página {page_number} do regulamento")
        document.save(path)
    finally:
        document.close()


def make_harness(
    tmp_path: Path,
    *,
    run_id_factory: Callable[[], str] = lambda: "run-001",
) -> PipelineHarness:
    source_pdf = tmp_path / "regulamento.pdf"
    make_pdf(source_pdf)
    repository = JsonRunRepository(tmp_path / "runs")
    usage_ledger = UsageLedger()
    provider = FakeLLMProvider(usage_ledger)
    pipeline = RegulationPipeline(
        repository=repository,
        pdf_processor=PdfProcessor(),
        locator=RegulationSectionLocator(provider),
        extractor=RegulationVariableExtractor(
            provider,
            id_factory=lambda: "variable-001",
        ),
        validator=RegulationVariableValidator(
            provider,
            finding_id_factory=lambda: "finding-001",
        ),
        models=AgentModels(
            locator="locator-model",
            extractor="extractor-model",
            validator="validator-model",
        ),
        usage_ledger=usage_ledger,
        run_id_factory=run_id_factory,
        clock=lambda: datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        timer=StepTimer(),
    )
    return PipelineHarness(pipeline, repository, provider, source_pdf)


def create_and_locate(harness: PipelineHarness) -> None:
    harness.pipeline.create_run(harness.source_pdf)
    harness.pipeline.locate_section("run-001", chapter_hint=3)


def create_confirm_and_extract(harness: PipelineHarness) -> None:
    create_and_locate(harness)
    harness.pipeline.confirm_location("run-001", page_start=2, page_end=3)
    harness.pipeline.extract("run-001", preferred_vocabulary=["prazo_pagamento_resgate"])


def test_create_run_persists_metadata_and_restartable_source(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)

    run = harness.pipeline.create_run(harness.source_pdf)

    assert run.run_id == "run-001"
    assert run.document_name == "regulamento.pdf"
    assert run.document_sha256 == hashlib.sha256(harness.source_pdf.read_bytes()).hexdigest()
    assert run.state is RunState.CREATED
    assert run.page_count == 4
    assert run.created_at == datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    assert harness.repository.load_run("run-001") == run
    assert harness.repository.source_path("run-001").read_bytes() == harness.source_pdf.read_bytes()


def test_reprocessing_a_completed_run_creates_new_history(tmp_path: Path) -> None:
    run_ids = iter(("run-001", "run-002"))
    harness = make_harness(tmp_path, run_id_factory=run_ids.__next__)
    create_confirm_and_extract(harness)
    harness.pipeline.validate("run-001")
    ExcelExporter(harness.repository).export_final(harness.repository.load_run("run-001"))
    completed = harness.repository.load_run("run-001")
    completed.transition(RunState.FINAL_READY)
    harness.repository.save_run(completed)
    completed_snapshot = completed.model_dump(mode="json")

    reprocessed = harness.pipeline.create_run(harness.source_pdf)

    assert reprocessed.run_id == "run-002"
    assert reprocessed.document_sha256 == completed.document_sha256
    assert harness.repository.load_run("run-001").model_dump(mode="json") == completed_snapshot
    assert {run.run_id for run in harness.repository.list_runs()} == {"run-001", "run-002"}
    assert harness.repository.source_path("run-001").is_file()
    assert harness.repository.source_path("run-002").is_file()


def test_location_result_is_persisted_before_confirmation(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    harness.pipeline.create_run(harness.source_pdf)

    location = harness.pipeline.locate_section("run-001", chapter_hint=3)

    persisted = harness.repository.load_run("run-001")
    assert location.title == "Seção de movimentações"
    assert persisted.state is RunState.LOCATION_READY
    assert persisted.location == location
    assert persisted.location is not None and persisted.location.confirmed is False


def test_extraction_is_blocked_until_location_confirmation(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    create_and_locate(harness)

    with pytest.raises(ValueError, match="confirmed"):
        harness.pipeline.extract("run-001")

    assert harness.repository.load_run("run-001").state is RunState.LOCATION_READY


def test_confirmation_persists_the_operator_page_interval(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    create_and_locate(harness)

    run = harness.pipeline.confirm_location("run-001", page_start=2, page_end=3)

    persisted = harness.repository.load_run("run-001")
    assert run.state is RunState.LOCATION_CONFIRMED
    assert persisted.location is not None
    assert persisted.location.confirmed is True
    assert (persisted.location.page_start, persisted.location.page_end) == (2, 3)


def test_extraction_uses_only_confirmed_pages_and_persists_variables(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    create_and_locate(harness)
    harness.pipeline.confirm_location("run-001", page_start=2, page_end=3)

    variables = harness.pipeline.extract(
        "run-001",
        preferred_vocabulary=["prazo_pagamento_resgate"],
    )

    persisted = harness.repository.load_run("run-001")
    selected = pymupdf.open(stream=harness.provider.extract_requests[0].document.content)
    try:
        assert selected.page_count == 2
    finally:
        selected.close()
    assert persisted.state is RunState.EXTRACTED
    assert persisted.variables == variables
    assert variables[0].current_value == "D+5"


def test_validation_persists_results_and_enters_reviewing_state(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    create_confirm_and_extract(harness)

    batch = harness.pipeline.validate("run-001")

    persisted = harness.repository.load_run("run-001")
    assert persisted.state is RunState.REVIEWING
    assert persisted.validations == batch.validations
    assert persisted.coverage_findings == batch.coverage_findings
    assert persisted.validations[0].confidence == 0.97


def test_location_failure_is_persisted_and_can_be_resumed(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    harness.pipeline.create_run(harness.source_pdf)
    successful = harness.provider.locate_outcomes[0]
    harness.provider.locate_outcomes = [RuntimeError("locator unavailable"), successful]

    with pytest.raises(RuntimeError, match="locator unavailable"):
        harness.pipeline.locate_section("run-001")

    assert harness.repository.load_run("run-001").state is RunState.FAILED_LOCATION
    location = harness.pipeline.locate_section("run-001")
    assert location is not None
    assert harness.repository.load_run("run-001").state is RunState.LOCATION_READY


def test_extraction_failure_is_persisted_and_can_be_resumed(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    create_and_locate(harness)
    harness.pipeline.confirm_location("run-001", page_start=2, page_end=3)
    successful = harness.provider.extract_outcomes[0]
    harness.provider.extract_outcomes = [RuntimeError("extractor unavailable"), successful]

    with pytest.raises(RuntimeError, match="extractor unavailable"):
        harness.pipeline.extract("run-001")

    failed = harness.repository.load_run("run-001")
    assert failed.state is RunState.FAILED_EXTRACTION
    assert failed.variables == []
    variables = harness.pipeline.extract("run-001")
    assert variables[0].current_value == "D+5"
    assert harness.repository.load_run("run-001").state is RunState.EXTRACTED


def test_validation_failure_is_persisted_and_can_be_resumed(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    create_confirm_and_extract(harness)
    successful = harness.provider.validate_outcomes[0]
    harness.provider.validate_outcomes = [RuntimeError("validator unavailable"), successful]

    with pytest.raises(RuntimeError, match="validator unavailable"):
        harness.pipeline.validate("run-001")

    failed = harness.repository.load_run("run-001")
    assert failed.state is RunState.FAILED_VALIDATION
    assert failed.variables
    batch = harness.pipeline.validate("run-001")
    assert batch.validations[0].confidence == 0.97
    assert harness.repository.load_run("run-001").state is RunState.REVIEWING


def test_locator_not_found_allows_manual_page_confirmation(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    harness.provider.locate_outcomes = [
        LocateResponse(
            status=LocationStatus.NOT_FOUND,
            rationale="Não foi possível delimitar a seção.",
        )
    ]
    harness.pipeline.create_run(harness.source_pdf)

    location = harness.pipeline.locate_section("run-001")
    confirmed = harness.pipeline.confirm_location("run-001", page_start=1, page_end=4)

    assert location is None
    assert confirmed.state is RunState.LOCATION_CONFIRMED
    assert confirmed.location is not None
    assert confirmed.location.confirmed is True
    assert confirmed.location.title == "Seleção manual"


@pytest.mark.parametrize(
    ("agent", "expected_state"),
    [
        ("locator", RunState.LOCATING),
        ("extractor", RunState.EXTRACTING),
        ("validator", RunState.VALIDATING),
    ],
)
def test_in_progress_state_is_persisted_before_each_agent_call(
    tmp_path: Path,
    agent: str,
    expected_state: RunState,
) -> None:
    harness = make_harness(tmp_path)
    if agent == "locator":
        harness.pipeline.create_run(harness.source_pdf)
    elif agent == "extractor":
        create_and_locate(harness)
        harness.pipeline.confirm_location("run-001", page_start=2, page_end=3)
    else:
        create_confirm_and_extract(harness)

    def assert_persisted(called_agent: str) -> None:
        if called_agent == agent:
            assert harness.repository.load_run("run-001").state is expected_state

    harness.provider.on_call = assert_persisted
    if agent == "locator":
        harness.pipeline.locate_section("run-001")
    elif agent == "extractor":
        harness.pipeline.extract("run-001")
    else:
        harness.pipeline.validate("run-001")


def test_rerunning_location_replaces_location_and_invalidates_all_dependents(
    tmp_path: Path,
) -> None:
    harness = make_harness(tmp_path)
    create_confirm_and_extract(harness)
    harness.pipeline.validate("run-001")
    harness.provider.locate_outcomes = [
        LocateResponse(
            status=LocationStatus.FOUND,
            title="Novo capítulo de cotas",
            page_start=1,
            page_end=2,
            rationale="Nova delimitação sustentada pelo documento.",
        )
    ]

    location = harness.pipeline.locate_section("run-001", chapter_hint=6)

    persisted = harness.repository.load_run("run-001")
    assert location is not None and location.title == "Novo capítulo de cotas"
    assert persisted.state is RunState.LOCATION_READY
    assert persisted.variables == []
    assert persisted.validations == []
    assert persisted.coverage_findings == []


def test_rerunning_extraction_replaces_variables_and_invalidates_validation(
    tmp_path: Path,
) -> None:
    harness = make_harness(tmp_path)
    create_confirm_and_extract(harness)
    harness.pipeline.validate("run-001")
    harness.provider.extract_outcomes = [
        ExtractionResponse(
            variables=[
                AtomicVariable(
                    name="prazo_pagamento_resgate",
                    value="D+10",
                    evidence_text="O pagamento ocorrerá em até dez dias.",
                    source_pages=[3],
                    source_kind=ExtractionSourceKind.PROSE,
                )
            ]
        )
    ]

    variables = harness.pipeline.extract("run-001")

    persisted = harness.repository.load_run("run-001")
    assert variables[0].current_value == "D+10"
    assert persisted.state is RunState.EXTRACTED
    assert persisted.validations == []
    assert persisted.coverage_findings == []


def test_rerunning_validation_replaces_only_validation_outputs(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    create_confirm_and_extract(harness)
    harness.pipeline.validate("run-001")
    original_variables = harness.repository.load_run("run-001").variables
    harness.provider.validate_outcomes = [
        ValidationResponse(
            validations=[
                VariableValidation(
                    variable_id="variable-001",
                    confidence=0.42,
                    verdict=ValidationVerdict.PARTIALLY_SUPPORTED,
                    rationale="O contexto não confirma integralmente o prazo.",
                    issues=["Contexto incompleto"],
                )
            ],
            omissions=[
                OmissionFinding(
                    description="Possível carência de resgate omitida.",
                    suggested_name="carencia_resgate",
                    evidence_text="A carência aplicável consta da tabela.",
                    source_pages=[2],
                )
            ],
        )
    ]

    batch = harness.pipeline.validate("run-001")

    persisted = harness.repository.load_run("run-001")
    assert persisted.variables == original_variables
    assert batch.validations[0].confidence == 0.42
    assert persisted.validations == batch.validations
    assert persisted.coverage_findings == batch.coverage_findings


def test_concurrent_call_for_the_same_run_is_refused(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    harness.pipeline.create_run(harness.source_pdf)
    call_started = Event()
    release_call = Event()
    thread_errors: list[Exception] = []

    def block_locator(agent: str) -> None:
        if agent == "locator":
            call_started.set()
            assert release_call.wait(timeout=3)

    def locate_in_thread() -> None:
        try:
            harness.pipeline.locate_section("run-001")
        except Exception as error:  # pragma: no cover - diagnostic collection
            thread_errors.append(error)

    harness.provider.on_call = block_locator
    worker = Thread(target=locate_in_thread)
    worker.start()
    assert call_started.wait(timeout=3)
    try:
        with pytest.raises(PipelineBusyError, match="already active"):
            harness.pipeline.locate_section("run-001")
    finally:
        release_call.set()
        worker.join(timeout=3)

    assert not worker.is_alive()
    assert thread_errors == []
    assert harness.repository.load_run("run-001").state is RunState.LOCATION_READY


def test_agent_calls_write_structured_success_events(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    create_confirm_and_extract(harness)
    harness.pipeline.validate("run-001")

    events = harness.repository.load_events("run-001")

    assert [event.stage for event in events] == ["location", "extraction", "validation"]
    assert all(event.event == "stage_completed" for event in events)
    assert all(event.status == "success" for event in events)
    assert all(event.duration_ms == 125 for event in events)
    assert [event.model for event in events] == [
        "locator-model",
        "extractor-model",
        "validator-model",
    ]
    assert [event.input_pages for event in events] == [[1, 2, 3, 4], [2, 3], [2, 3]]
    assert all(event.usage["total_tokens"] == 125 for event in events)
    assert all(event.usage["attempts"] == 1 for event in events)
    assert all(event.error is None for event in events)


def test_failure_event_is_sanitized_and_contains_retry_context(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    harness.pipeline.create_run(harness.source_pdf)
    harness.provider.locate_outcomes = [RuntimeError("api_key=sk-supersecret unavailable")]

    with pytest.raises(RuntimeError):
        harness.pipeline.locate_section("run-001")

    event = harness.repository.load_events("run-001")[0]
    assert event.stage == "location"
    assert event.event == "stage_failed"
    assert event.status == "failure"
    assert event.duration_ms == 125
    assert event.usage == {}
    assert event.error is not None
    assert "[REDACTED]" in event.error
    assert "supersecret" not in event.error


def test_usage_ledger_keeps_parallel_run_metrics_isolated() -> None:
    ledger = UsageLedger()
    synchronized = Barrier(2)
    captured: dict[str, str | None] = {}

    def record_and_take(model: str) -> None:
        ledger.record(
            SimpleNamespace(
                agent="locator",
                model=model,
                prompt_version="locator-v1",
                response_id=f"response-{model}",
                input_tokens=10,
                output_tokens=2,
                total_tokens=12,
                attempts=1,
            )
        )
        synchronized.wait(timeout=3)
        usage = ledger.take("locator")
        captured[model] = None if usage is None else usage.model

    workers = [
        Thread(target=record_and_take, args=("model-a",)),
        Thread(target=record_and_take, args=("model-b",)),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=3)

    assert all(not worker.is_alive() for worker in workers)
    assert captured == {"model-a": "model-a", "model-b": "model-b"}


def test_preview_pages_renders_the_requested_original_interval(tmp_path: Path) -> None:
    harness = make_harness(tmp_path)
    harness.pipeline.create_run(harness.source_pdf)

    previews = harness.pipeline.preview_pages("run-001", page_start=2, page_end=3)

    assert [preview.page_number for preview in previews] == [2, 3]
    assert all(preview.path.is_file() for preview in previews)
    assert all(preview.path.parent.name == "previews" for preview in previews)
