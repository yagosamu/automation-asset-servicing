"""Contract for the executable local Streamlit composition root."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pymupdf
import pytest

from asset_servicing.adapters.llm.openai_responses import LLMUsage, OpenAIConfig
from asset_servicing.application import RegulationPipeline, RunDeliveryService
from asset_servicing.application.review_service import ReviewService
from asset_servicing.ports.llm import (
    ExtractionRequest,
    ExtractionResponse,
    LocateRequest,
    LocateResponse,
    LocationStatus,
    ValidationRequest,
    ValidationResponse,
)
from asset_servicing.ui import runtime

pytestmark = pytest.mark.contract
ROOT = Path(__file__).resolve().parents[2]


class LocatorProvider:
    def __init__(
        self,
        config: OpenAIConfig,
        usage_sink: Callable[[LLMUsage], None],
    ) -> None:
        self.config = config
        self.usage_sink = usage_sink

    def locate(self, request: LocateRequest) -> LocateResponse:
        self.usage_sink(
            LLMUsage(
                agent="locator",
                model=self.config.locator_model,
                prompt_version=request.prompt_version,
                response_id="runtime-location-response",
                input_tokens=8,
                output_tokens=4,
                total_tokens=12,
                attempts=1,
            )
        )
        return LocateResponse(
            status=LocationStatus.FOUND,
            title="CAPÍTULO 3 – DA EMISSÃO, APLICAÇÃO E RESGATE DE COTAS",
            page_start=1,
            page_end=1,
            rationale="A seção alvo está na primeira página.",
        )

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        raise AssertionError("extraction is outside this runtime composition contract")

    def validate(self, request: ValidationRequest) -> ValidationResponse:
        raise AssertionError("validation is outside this runtime composition contract")


def _runtime_environment() -> dict[str, str]:
    return {
        "OPENAI_API_KEY": "sentinel-runtime-secret",
        "LOCATOR_MODEL": "locator-runtime-model",
        "EXTRACTOR_MODEL": "extractor-runtime-model",
        "VALIDATOR_MODEL": "validator-runtime-model",
    }


def _write_pdf(path: Path) -> None:
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "CAPÍTULO 3 – DA EMISSÃO, APLICAÇÃO E RESGATE DE COTAS")
        document.save(path)
    finally:
        document.close()


def test_build_local_services_wires_models_usage_and_local_paths(tmp_path: Path) -> None:
    observed_providers: list[LocatorProvider] = []

    def provider_factory(
        config: OpenAIConfig,
        usage_sink: Callable[[LLMUsage], None],
    ) -> LocatorProvider:
        provider = LocatorProvider(config, usage_sink)
        observed_providers.append(provider)
        return provider

    services = runtime.build_local_services(
        project_root=tmp_path,
        environ=_runtime_environment(),
        provider_factory=provider_factory,
    )
    source = tmp_path / "regulation.pdf"
    _write_pdf(source)
    run = services.pipeline.create_run(source)
    services.pipeline.locate_section(run.run_id, chapter_hint=3)
    summary = services.delivery_service.summary(run.run_id)

    assert isinstance(services.pipeline, RegulationPipeline)
    assert isinstance(services.review_service, ReviewService)
    assert isinstance(services.delivery_service, RunDeliveryService)
    assert services.regulations_dir == tmp_path / "Regulamentos"
    assert services.upload_dir == tmp_path / "data" / "uploads"
    assert (tmp_path / "data" / "runs" / run.run_id / "run.json").is_file()
    assert observed_providers[0].config.locator_model == "locator-runtime-model"
    assert observed_providers[0].config.extractor_model == "extractor-runtime-model"
    assert observed_providers[0].config.validator_model == "validator-runtime-model"
    assert summary.models == ("locator-runtime-model",)
    assert summary.usage["total_tokens"] == 12


def test_missing_runtime_configuration_is_actionable_and_sanitized(tmp_path: Path) -> None:
    with pytest.raises(
        runtime.RuntimeConfigurationError,
        match=(
            "missing local runtime configuration: OPENAI_API_KEY, LOCATOR_MODEL, "
            "EXTRACTOR_MODEL, VALIDATOR_MODEL"
        ),
    ) as error:
        runtime.build_local_services(
            project_root=tmp_path,
            environ={"UNRELATED_SECRET": "must-not-appear"},
        )

    assert "must-not-appear" not in str(error.value)


def test_runtime_directories_are_ignored_by_git() -> None:
    ignored_paths = set((ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())

    assert {"data/runs/", "data/uploads/"} <= ignored_paths


def test_streamlit_entrypoint_passes_configured_services_to_ui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_services = object()
    rendered: list[object] = []
    monkeypatch.setattr(runtime, "build_local_services", lambda: configured_services)
    monkeypatch.setattr(runtime, "render_app", rendered.append)

    runtime.main()

    assert rendered == [configured_services]
