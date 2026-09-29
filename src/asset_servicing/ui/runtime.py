"""Executable local composition root for the Streamlit application."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import streamlit as st

from asset_servicing.adapters.export import ExcelExporter
from asset_servicing.adapters.llm.openai_responses import (
    LLMUsage,
    OpenAIConfig,
    OpenAIResponsesProvider,
)
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
from asset_servicing.ports.llm import LLMProvider
from asset_servicing.ui.app import DocumentLocationPipeline, LocalAppServices
from asset_servicing.ui.app import main as render_app


class RuntimeConfigurationError(ValueError):
    """Raised when the local application is not explicitly configured."""


class ProviderFactory(Protocol):
    def __call__(
        self,
        config: OpenAIConfig,
        usage_sink: Callable[[LLMUsage], None],
    ) -> LLMProvider: ...


@dataclass(slots=True)
class _LedgerUsage:
    agent: str
    model: str
    prompt_version: str
    response_id: str | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    attempts: int


def _openai_provider(
    config: OpenAIConfig,
    usage_sink: Callable[[LLMUsage], None],
) -> LLMProvider:
    return OpenAIResponsesProvider.from_config(config, usage_sink=usage_sink)


def build_local_services(
    *,
    project_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    provider_factory: ProviderFactory = _openai_provider,
) -> LocalAppServices:
    """Compose real local adapters without making an external LLM call."""

    values = os.environ if environ is None else environ
    required_names = (
        "OPENAI_API_KEY",
        "LOCATOR_MODEL",
        "EXTRACTOR_MODEL",
        "VALIDATOR_MODEL",
    )
    missing = [name for name in required_names if not values.get(name)]
    if missing:
        raise RuntimeConfigurationError(
            f"missing local runtime configuration: {', '.join(missing)}"
        )

    root = (
        Path(__file__).resolve().parents[3]
        if project_root is None
        else Path(project_root).resolve()
    )
    config = OpenAIConfig.from_env(values)
    repository = JsonRunRepository(root / "data" / "runs")
    usage_ledger = UsageLedger()

    def record_usage(usage: LLMUsage) -> None:
        usage_ledger.record(
            _LedgerUsage(
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

    provider = provider_factory(config, record_usage)
    pipeline = RegulationPipeline(
        repository=repository,
        pdf_processor=PdfProcessor(),
        locator=RegulationSectionLocator(provider),
        extractor=RegulationVariableExtractor(provider),
        validator=RegulationVariableValidator(provider),
        models=AgentModels(
            locator=config.locator_model,
            extractor=config.extractor_model,
            validator=config.validator_model,
        ),
        usage_ledger=usage_ledger,
    )
    return LocalAppServices(
        pipeline=cast(DocumentLocationPipeline, pipeline),
        regulations_dir=root / "Regulamentos",
        upload_dir=root / "data" / "uploads",
        review_service=ReviewService(repository=repository),
        delivery_service=RunDeliveryService(
            repository=repository,
            exporter=ExcelExporter(repository),
        ),
    )


def main() -> None:
    """Start the configured local Streamlit application."""

    try:
        services = build_local_services()
    except RuntimeConfigurationError as error:
        st.error(str(error))
        return
    render_app(services)


if __name__ == "__main__":
    main()


__all__ = ["RuntimeConfigurationError", "build_local_services", "main"]
