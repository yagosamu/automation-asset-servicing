"""Persisted orchestration for the regulation-processing stages."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock, local
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from asset_servicing.adapters.pdf import PagePreview, PdfProcessor
from asset_servicing.adapters.persistence import JsonRunRepository, RunEvent
from asset_servicing.application.extractor import (
    EXTRACTOR_PROMPT_VERSION,
    RegulationVariableExtractor,
)
from asset_servicing.application.locator import (
    LOCATOR_PROMPT_VERSION,
    RegulationSectionLocator,
)
from asset_servicing.application.validator import (
    VALIDATOR_PROMPT_VERSION,
    RegulationVariableValidator,
    ValidationBatch,
)
from asset_servicing.domain import ExtractedVariable, Run, RunState, SectionLocation
from asset_servicing.ports.llm import AgentDocument


class _UsageRecord(Protocol):
    agent: str
    model: str
    prompt_version: str
    response_id: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    attempts: int


@dataclass(frozen=True, slots=True)
class AgentUsage:
    """Provider-neutral usage captured for one completed agent call."""

    agent: str
    model: str
    prompt_version: str
    response_id: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    attempts: int


class _UsageContext(local):
    """Agent usage records isolated to one synchronous execution context."""

    def __init__(self) -> None:
        self.records: dict[str, AgentUsage] = {}


class UsageLedger:
    """Context-local handoff of usage from an LLM adapter to the pipeline."""

    def __init__(self) -> None:
        self._context = _UsageContext()

    def record(self, usage: _UsageRecord) -> None:
        """Store the latest provider usage for an agent."""

        record = AgentUsage(
            agent=usage.agent,
            model=usage.model,
            prompt_version=usage.prompt_version,
            response_id=usage.response_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            attempts=usage.attempts,
        )
        self._context.records[record.agent] = record

    def take(self, agent: str) -> AgentUsage | None:
        """Consume usage so it cannot leak into a later stage event."""

        return self._context.records.pop(agent, None)

    def clear(self, agent: str) -> None:
        """Discard stale usage before starting a new agent call."""

        self._context.records.pop(agent, None)


@dataclass(frozen=True, slots=True)
class AgentModels:
    """Configured model identifiers for operational audit events."""

    locator: str
    extractor: str
    validator: str


class PipelineBusyError(RuntimeError):
    """Raised when the same run is already executing in this process."""


def _new_run_id() -> str:
    return str(uuid4())


class RegulationPipeline:
    """Coordinate application services while persisting every state boundary."""

    def __init__(
        self,
        *,
        repository: JsonRunRepository,
        pdf_processor: PdfProcessor,
        locator: RegulationSectionLocator,
        extractor: RegulationVariableExtractor,
        validator: RegulationVariableValidator,
        models: AgentModels,
        usage_ledger: UsageLedger,
        run_id_factory: Callable[[], str] = _new_run_id,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        timer: Callable[[], float] = perf_counter,
    ) -> None:
        self._repository = repository
        self._pdf = pdf_processor
        self._locator = locator
        self._extractor = extractor
        self._validator = validator
        self._models = models
        self._usage = usage_ledger
        self._run_id_factory = run_id_factory
        self._clock = clock
        self._timer = timer
        self._active_run_ids: set[str] = set()
        self._active_lock = Lock()

    def create_run(self, source_pdf: Path) -> Run:
        """Validate a source PDF and persist a restartable processing run."""

        metadata = self._pdf.inspect(source_pdf)
        run = Run(
            run_id=self._run_id_factory(),
            document_name=metadata.filename,
            document_sha256=metadata.sha256,
            page_count=metadata.page_count,
            created_at=self._clock(),
        )
        self._repository.save_run(run, source_pdf=source_pdf)
        return run

    def locate_section(
        self, run_id: str, *, chapter_hint: int | None = None
    ) -> SectionLocation | None:
        """Locate and persist an unconfirmed semantic section candidate."""

        with self._claim(run_id):
            run = self._repository.load_run(run_id)
            run.transition(RunState.LOCATING)
            self._repository.save_run(run)
            started_at = self._clock()
            started = self._timer()
            self._usage.clear("locator")
            try:
                outcome = self._locator.locate(self._full_document(run), chapter_hint=chapter_hint)
            except Exception as error:
                run.transition(RunState.FAILED_LOCATION)
                self._repository.save_run(run)
                self._append_event(
                    run=run,
                    stage="location",
                    agent="locator",
                    event="stage_failed",
                    status="failure",
                    started_at=started_at,
                    started=started,
                    model=self._models.locator,
                    prompt_version=LOCATOR_PROMPT_VERSION,
                    input_pages=list(range(1, run.page_count + 1)),
                    error=error,
                )
                raise
            if outcome.location is None:
                run.transition(RunState.FAILED_LOCATION)
                self._repository.save_run(run)
                self._append_event(
                    run=run,
                    stage="location",
                    agent="locator",
                    event="stage_completed",
                    status="manual_required",
                    started_at=started_at,
                    started=started,
                    model=self._models.locator,
                    prompt_version=LOCATOR_PROMPT_VERSION,
                    input_pages=list(range(1, run.page_count + 1)),
                )
                return None
            run.location = outcome.location
            self._invalidate_after_location(run)
            run.transition(RunState.LOCATION_READY)
            self._repository.save_run(run)
            self._append_event(
                run=run,
                stage="location",
                agent="locator",
                event="stage_completed",
                status="success",
                started_at=started_at,
                started=started,
                model=self._models.locator,
                prompt_version=LOCATOR_PROMPT_VERSION,
                input_pages=list(range(1, run.page_count + 1)),
            )
            return outcome.location

    def confirm_location(self, run_id: str, *, page_start: int, page_end: int) -> Run:
        """Persist the page interval explicitly confirmed by the operator."""

        with self._claim(run_id):
            run = self._repository.load_run(run_id)
            if page_start < 1 or page_end < page_start or page_end > run.page_count:
                raise ValueError(f"page range must be between 1 and {run.page_count}")
            if run.location is None:
                run.location = SectionLocation(
                    title="Seleção manual",
                    page_start=page_start,
                    page_end=page_end,
                    rationale="Intervalo informado manualmente após localização inconclusiva.",
                )
            run.confirm_location(page_start=page_start, page_end=page_end)
            self._repository.save_run(run)
            return run

    def preview_pages(
        self,
        run_id: str,
        *,
        page_start: int,
        page_end: int,
    ) -> list[PagePreview]:
        """Render an inclusive source interval for human confirmation."""

        with self._claim(run_id):
            run = self._repository.load_run(run_id)
            return self._pdf.render_pages(
                self._repository.source_path(run_id),
                pages=list(range(page_start, page_end + 1)),
                output_dir=self._repository.root / run.run_id / "previews",
            )

    def extract(
        self,
        run_id: str,
        *,
        preferred_vocabulary: list[str] | None = None,
    ) -> list[ExtractedVariable]:
        """Extract variables from the persisted, confirmed page interval."""

        with self._claim(run_id):
            run = self._repository.load_run(run_id)
            location = self._confirmed_location(run)
            run.transition(RunState.EXTRACTING)
            self._repository.save_run(run)
            started_at = self._clock()
            started = self._timer()
            self._usage.clear("extractor")
            try:
                variables = self._extractor.extract(
                    self._selected_document(run, location),
                    page_start=location.page_start,
                    page_end=location.page_end,
                    preferred_vocabulary=preferred_vocabulary,
                )
            except Exception as error:
                run.transition(RunState.FAILED_EXTRACTION)
                self._repository.save_run(run)
                self._append_event(
                    run=run,
                    stage="extraction",
                    agent="extractor",
                    event="stage_failed",
                    status="failure",
                    started_at=started_at,
                    started=started,
                    model=self._models.extractor,
                    prompt_version=EXTRACTOR_PROMPT_VERSION,
                    input_pages=self._page_interval(location),
                    error=error,
                )
                raise
            run.variables = variables
            run.validations = []
            run.coverage_findings = []
            run.reviews = []
            run.preliminary_export_path = None
            run.final_export_path = None
            run.transition(RunState.EXTRACTED)
            self._repository.save_run(run)
            self._append_event(
                run=run,
                stage="extraction",
                agent="extractor",
                event="stage_completed",
                status="success",
                started_at=started_at,
                started=started,
                model=self._models.extractor,
                prompt_version=EXTRACTOR_PROMPT_VERSION,
                input_pages=self._page_interval(location),
            )
            return variables

    def validate(self, run_id: str) -> ValidationBatch:
        """Validate persisted variables independently against confirmed pages."""

        with self._claim(run_id):
            run = self._repository.load_run(run_id)
            location = self._confirmed_location(run)
            run.transition(RunState.VALIDATING)
            self._repository.save_run(run)
            started_at = self._clock()
            started = self._timer()
            self._usage.clear("validator")
            try:
                batch = self._validator.validate(
                    self._selected_document(run, location),
                    page_start=location.page_start,
                    page_end=location.page_end,
                    variables=run.variables,
                )
            except Exception as error:
                run.transition(RunState.FAILED_VALIDATION)
                self._repository.save_run(run)
                self._append_event(
                    run=run,
                    stage="validation",
                    agent="validator",
                    event="stage_failed",
                    status="failure",
                    started_at=started_at,
                    started=started,
                    model=self._models.validator,
                    prompt_version=VALIDATOR_PROMPT_VERSION,
                    input_pages=self._page_interval(location),
                    error=error,
                )
                raise
            run.validations = batch.validations
            run.coverage_findings = batch.coverage_findings
            run.reviews = []
            run.preliminary_export_path = None
            run.final_export_path = None
            run.transition(RunState.REVIEWING)
            self._repository.save_run(run)
            self._append_event(
                run=run,
                stage="validation",
                agent="validator",
                event="stage_completed",
                status="success",
                started_at=started_at,
                started=started,
                model=self._models.validator,
                prompt_version=VALIDATOR_PROMPT_VERSION,
                input_pages=self._page_interval(location),
            )
            return batch

    @staticmethod
    def _invalidate_after_location(run: Run) -> None:
        run.variables = []
        run.validations = []
        run.coverage_findings = []
        run.reviews = []
        run.preliminary_export_path = None
        run.final_export_path = None

    @staticmethod
    def _page_interval(location: SectionLocation) -> list[int]:
        return list(range(location.page_start, location.page_end + 1))

    def _append_event(
        self,
        *,
        run: Run,
        stage: str,
        agent: str,
        event: str,
        status: str,
        started_at: datetime,
        started: float,
        model: str,
        prompt_version: str,
        input_pages: list[int],
        error: Exception | None = None,
    ) -> None:
        usage = self._usage.take(agent)
        usage_payload: dict[str, object] = {}
        if usage is not None:
            model = usage.model
            prompt_version = usage.prompt_version
            usage_payload = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
                "attempts": usage.attempts,
                "response_id": usage.response_id,
            }
        duration_ms = max(0, round((self._timer() - started) * 1000))
        self._repository.append_event(
            RunEvent(
                run_id=run.run_id,
                stage=stage,
                event=event,
                status=status,
                started_at=started_at,
                duration_ms=duration_ms,
                model=model,
                prompt_version=prompt_version,
                input_pages=input_pages,
                usage=usage_payload,
                error=None if error is None else f"{type(error).__name__}: {error}",
            )
        )

    def _full_document(self, run: Run) -> AgentDocument:
        source = self._repository.source_path(run.run_id)
        return AgentDocument(filename=run.document_name, content=source.read_bytes())

    def _selected_document(self, run: Run, location: SectionLocation) -> AgentDocument:
        content = self._pdf.select_pages(
            self._repository.source_path(run.run_id),
            start=location.page_start,
            end=location.page_end,
        )
        return AgentDocument(filename=run.document_name, content=content)

    @staticmethod
    def _confirmed_location(run: Run) -> SectionLocation:
        if run.location is None or not run.location.confirmed:
            raise ValueError("a confirmed section location is required")
        return run.location

    @contextmanager
    def _claim(self, run_id: str) -> Iterator[None]:
        with self._active_lock:
            if run_id in self._active_run_ids:
                raise PipelineBusyError(f"run is already active: {run_id}")
            self._active_run_ids.add(run_id)
        try:
            yield
        finally:
            with self._active_lock:
                self._active_run_ids.remove(run_id)


__all__ = ["AgentModels", "PipelineBusyError", "RegulationPipeline", "UsageLedger"]
