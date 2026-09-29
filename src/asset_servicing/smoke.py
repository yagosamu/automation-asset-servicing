"""Opt-in live smoke orchestration with a deliberately small report surface."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from asset_servicing.adapters.llm.openai_responses import (
    LLMUsage,
    OpenAIConfig,
    OpenAIResponsesProvider,
)
from asset_servicing.adapters.pdf import PdfProcessor
from asset_servicing.adapters.persistence import JsonRunRepository, RunEvent
from asset_servicing.application import (
    AgentModels,
    RegulationPipeline,
    RegulationSectionLocator,
    RegulationVariableExtractor,
    RegulationVariableValidator,
    UsageLedger,
)
from asset_servicing.ports.llm import LLMProvider

DEFAULT_SMOKE_PDF = "DOC_REGUL_23183_193223_2026_05.pdf"


class SmokeConfigurationError(ValueError):
    """Raised when the live smoke is not explicitly configured."""


@dataclass(frozen=True, slots=True)
class SmokeSettings:
    """Explicit external-call settings for one live smoke execution."""

    openai: OpenAIConfig
    source_pdf: Path
    work_dir: Path
    report_path: Path

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str],
        *,
        project_root: Path,
    ) -> SmokeSettings:
        required_names = (
            "OPENAI_API_KEY",
            "LOCATOR_MODEL",
            "EXTRACTOR_MODEL",
            "VALIDATOR_MODEL",
        )
        missing = [name for name in required_names if not environ.get(name)]
        if missing:
            raise SmokeConfigurationError(f"missing live smoke configuration: {', '.join(missing)}")
        root = project_root.resolve()
        work_dir = Path(environ.get("OPENAI_SMOKE_WORK_DIR", root / "tmp" / "live-smoke"))
        source_pdf = Path(
            environ.get("OPENAI_SMOKE_PDF", root / "Regulamentos" / DEFAULT_SMOKE_PDF)
        )
        report_path = Path(environ.get("OPENAI_SMOKE_REPORT", work_dir / "live-smoke-report.json"))
        return cls(
            openai=OpenAIConfig.from_env(environ),
            source_pdf=source_pdf,
            work_dir=work_dir,
            report_path=report_path,
        )


class SmokeDocumentReport(BaseModel):
    """Non-content document identifiers safe to retain as smoke evidence."""

    model_config = ConfigDict(extra="forbid")

    name: str
    sha256: str
    page_count: int
    selected_pages: list[int]


class SmokeUsageReport(BaseModel):
    """Provider usage allowed in the sanitized report."""

    model_config = ConfigDict(extra="forbid")

    input_tokens: int
    output_tokens: int
    total_tokens: int
    attempts: int


class LiveSmokeReport(BaseModel):
    """Whitelisted evidence from one successful three-agent execution."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    status: Literal["passed"] = "passed"
    run_id: str
    document: SmokeDocumentReport
    duration_ms: int
    models: dict[str, str]
    prompt_versions: dict[str, str]
    counts: dict[str, int]
    usage: dict[str, SmokeUsageReport]


class ProviderFactory(Protocol):
    def __call__(
        self,
        config: OpenAIConfig,
        usage_sink: Callable[[LLMUsage], None],
    ) -> LLMProvider: ...


def _openai_provider(
    config: OpenAIConfig,
    usage_sink: Callable[[LLMUsage], None],
) -> LLMProvider:
    return OpenAIResponsesProvider.from_config(
        config,
        usage_sink=usage_sink,
    )


def run_live_smoke(
    settings: SmokeSettings,
    *,
    provider_factory: ProviderFactory = _openai_provider,
) -> LiveSmokeReport:
    """Execute location, extraction, and validation and persist safe evidence."""

    started = perf_counter()
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    repository = JsonRunRepository(settings.work_dir / "runs")
    usage_ledger = UsageLedger()

    def record_usage(usage: LLMUsage) -> None:
        usage_ledger.record(
            SimpleNamespace(
                agent=usage.agent,
                model=usage.model,
                prompt_version=usage.prompt_version,
                response_id=usage.response_id,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
                attempts=usage.attempts,
            )
        )

    provider = provider_factory(settings.openai, record_usage)
    pipeline = RegulationPipeline(
        repository=repository,
        pdf_processor=PdfProcessor(),
        locator=RegulationSectionLocator(provider),
        extractor=RegulationVariableExtractor(provider),
        validator=RegulationVariableValidator(provider),
        models=AgentModels(
            locator=settings.openai.locator_model,
            extractor=settings.openai.extractor_model,
            validator=settings.openai.validator_model,
        ),
        usage_ledger=usage_ledger,
    )

    run = pipeline.create_run(settings.source_pdf)
    location = pipeline.locate_section(run.run_id)
    if location is None:
        raise RuntimeError("live smoke could not locate the target section")
    pipeline.confirm_location(
        run.run_id,
        page_start=location.page_start,
        page_end=location.page_end,
    )
    variables = pipeline.extract(run.run_id)
    validation = pipeline.validate(run.run_id)
    persisted = repository.load_run(run.run_id)
    report = _build_report(
        run=persisted,
        events=repository.load_events(run.run_id),
        duration_ms=max(0, round((perf_counter() - started) * 1000)),
        models=AgentModels(
            locator=settings.openai.locator_model,
            extractor=settings.openai.extractor_model,
            validator=settings.openai.validator_model,
        ),
        variable_count=len(variables),
        validation_count=len(validation.validations),
        finding_count=len(validation.coverage_findings),
    )
    _write_report(report, settings.report_path)
    return report


def _build_report(
    *,
    run: object,
    events: list[RunEvent],
    duration_ms: int,
    models: AgentModels,
    variable_count: int,
    validation_count: int,
    finding_count: int,
) -> LiveSmokeReport:
    from asset_servicing.domain import Run

    if not isinstance(run, Run) or run.location is None:
        raise ValueError("completed live smoke run must contain a location")
    prompt_versions: dict[str, str] = {}
    usage: dict[str, SmokeUsageReport] = {}
    agent_by_stage = {
        "location": "locator",
        "extraction": "extractor",
        "validation": "validator",
    }
    for event in events:
        agent = agent_by_stage[event.stage]
        prompt_versions[agent] = event.prompt_version
        usage[agent] = SmokeUsageReport(
            input_tokens=_usage_integer(event.usage.get("input_tokens")),
            output_tokens=_usage_integer(event.usage.get("output_tokens")),
            total_tokens=_usage_integer(event.usage.get("total_tokens")),
            attempts=_usage_integer(event.usage.get("attempts")),
        )
    return LiveSmokeReport(
        run_id=run.run_id,
        document=SmokeDocumentReport(
            name=run.document_name,
            sha256=run.document_sha256,
            page_count=run.page_count,
            selected_pages=list(range(run.location.page_start, run.location.page_end + 1)),
        ),
        duration_ms=duration_ms,
        models={
            "locator": models.locator,
            "extractor": models.extractor,
            "validator": models.validator,
        },
        prompt_versions=prompt_versions,
        counts={
            "variables": variable_count,
            "validations": validation_count,
            "coverage_findings": finding_count,
            "pending_review": len(run.pending_items()),
        },
        usage=usage,
    )


def _usage_integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _write_report(report: LiveSmokeReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    os.replace(temporary, path)


__all__ = [
    "LiveSmokeReport",
    "ProviderFactory",
    "SmokeConfigurationError",
    "SmokeSettings",
    "run_live_smoke",
]
