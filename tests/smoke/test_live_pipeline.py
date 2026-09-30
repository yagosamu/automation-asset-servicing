"""Opt-in smoke test for the three real OpenAI-backed agents."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import pymupdf
import pytest

from asset_servicing.adapters.llm.openai_responses import LLMUsage, OpenAIConfig
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
from asset_servicing.smoke import SmokeConfigurationError, SmokeSettings, run_live_smoke

pytestmark = pytest.mark.needs_api


class RecordingProvider:
    def __init__(
        self,
        usage_sink: Callable[[LLMUsage], None],
        config: OpenAIConfig,
    ) -> None:
        self.usage_sink = usage_sink
        self.models = {
            "locator": config.locator_model,
            "extractor": config.extractor_model,
            "validator": config.validator_model,
        }
        self.calls: list[str] = []

    def locate(self, request: LocateRequest) -> LocateResponse:
        self._record("locator", request.prompt_version)
        return LocateResponse(
            status=LocationStatus.FOUND,
            title="CAPÍTULO 3 – MOVIMENTAÇÃO DE COTAS",
            page_start=2,
            page_end=3,
            rationale="A seção reúne aplicação e resgate.",
        )

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        self._record("extractor", request.prompt_version)
        return ExtractionResponse(
            variables=[
                AtomicVariable(
                    name="prazo_resgate",
                    value="D+30",
                    evidence_text="O pagamento ocorrerá em até trinta dias.",
                    source_pages=[2],
                    source_kind=ExtractionSourceKind.PROSE,
                )
            ]
        )

    def validate(self, request: ValidationRequest) -> ValidationResponse:
        self._record("validator", request.prompt_version)
        return ValidationResponse(
            validations=[
                VariableValidation(
                    variable_id=request.variables[0].variable_id,
                    confidence=0.97,
                    evidence_support=EvidenceSupport.LITERAL,
                    verdict=ValidationVerdict.SUPPORTED,
                    rationale="O valor está diretamente sustentado.",
                    issues=[],
                )
            ],
            omissions=[],
        )

    def _record(self, agent: str, prompt_version: str) -> None:
        self.calls.append(agent)
        self.usage_sink(
            LLMUsage(
                agent=agent,
                model=self.models[agent],
                prompt_version=prompt_version,
                response_id=f"response-{agent}",
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
                attempts=1,
            )
        )


def _make_pdf(path: Path) -> None:
    document = pymupdf.open()
    try:
        for page_number in range(1, 5):
            page = document.new_page()
            page.insert_text((72, 72), f"Página {page_number}: conteúdo sentinela do PDF")
        document.save(path)
    finally:
        document.close()


def test_missing_configuration_is_reported_without_reading_a_secret(tmp_path: Path) -> None:
    with pytest.raises(
        SmokeConfigurationError,
        match=(
            "missing live smoke configuration: OPENAI_API_KEY, LOCATOR_MODEL, "
            "EXTRACTOR_MODEL, VALIDATOR_MODEL"
        ),
    ):
        SmokeSettings.from_env({}, project_root=tmp_path)


def test_settings_preserve_independent_models_and_explicit_paths(tmp_path: Path) -> None:
    settings = SmokeSettings.from_env(
        {
            "OPENAI_API_KEY": "sentinel-live-secret",
            "LOCATOR_MODEL": "locator-live-model",
            "EXTRACTOR_MODEL": "extractor-live-model",
            "VALIDATOR_MODEL": "validator-live-model",
            "OPENAI_SMOKE_PDF": str(tmp_path / "source.pdf"),
            "OPENAI_SMOKE_WORK_DIR": str(tmp_path / "work"),
            "OPENAI_SMOKE_REPORT": str(tmp_path / "evidence" / "report.json"),
        },
        project_root=tmp_path,
    )

    assert settings.openai.locator_model == "locator-live-model"
    assert settings.openai.extractor_model == "extractor-live-model"
    assert settings.openai.validator_model == "validator-live-model"
    assert settings.source_pdf == tmp_path / "source.pdf"
    assert settings.work_dir == tmp_path / "work"
    assert settings.report_path == tmp_path / "evidence" / "report.json"
    assert "sentinel-live-secret" not in repr(settings)


def test_smoke_runs_three_agents_and_writes_a_sanitized_report(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    _make_pdf(source_pdf)
    settings = SmokeSettings.from_env(
        {
            "OPENAI_API_KEY": "sentinel-live-secret",
            "LOCATOR_MODEL": "locator-live-model",
            "EXTRACTOR_MODEL": "extractor-live-model",
            "VALIDATOR_MODEL": "validator-live-model",
            "OPENAI_SMOKE_PDF": str(source_pdf),
            "OPENAI_SMOKE_WORK_DIR": str(tmp_path / "work"),
            "OPENAI_SMOKE_REPORT": str(tmp_path / "report.json"),
        },
        project_root=tmp_path,
    )
    observed: list[RecordingProvider] = []

    def provider_factory(
        config: OpenAIConfig,
        usage_sink: Callable[[LLMUsage], None],
    ) -> RecordingProvider:
        provider = RecordingProvider(usage_sink, config)
        observed.append(provider)
        return provider

    report = run_live_smoke(settings, provider_factory=provider_factory)

    assert observed[0].calls == ["locator", "extractor", "validator"]
    assert report.status == "passed"
    assert report.models == {
        "locator": "locator-live-model",
        "extractor": "extractor-live-model",
        "validator": "validator-live-model",
    }
    assert report.counts == {
        "variables": 1,
        "validations": 1,
        "coverage_findings": 0,
        "pending_review": 0,
    }
    assert {agent: usage.total_tokens for agent, usage in report.usage.items()} == {
        "locator": 120,
        "extractor": 120,
        "validator": 120,
    }
    persisted = json.loads(settings.report_path.read_text(encoding="utf-8"))
    serialized = json.dumps(persisted, ensure_ascii=False)
    assert set(persisted) == {
        "schema_version",
        "status",
        "run_id",
        "document",
        "duration_ms",
        "models",
        "prompt_versions",
        "counts",
        "usage",
    }
    assert persisted["document"]["name"] == "source.pdf"
    assert persisted["document"]["selected_pages"] == [2, 3]
    assert "sentinel-live-secret" not in serialized
    assert "conteúdo sentinela do PDF" not in serialized
    assert "evidence_text" not in serialized


def test_live_pipeline_with_configured_openai_credentials() -> None:
    project_root = Path(__file__).resolve().parents[2]
    try:
        settings = SmokeSettings.from_env(os.environ, project_root=project_root)
    except SmokeConfigurationError as error:
        pytest.skip(f"live OpenAI smoke disabled: {error}")

    report = run_live_smoke(settings)

    assert report.status == "passed"
    assert set(report.models) == {"locator", "extractor", "validator"}
    assert set(report.usage) == {"locator", "extractor", "validator"}
    assert all(usage.attempts >= 1 for usage in report.usage.values())
    assert settings.report_path.is_file()
