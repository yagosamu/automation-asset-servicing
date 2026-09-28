"""Contract tests for the versioned semantic locator prompt."""

from __future__ import annotations

import pytest

from asset_servicing.application.locator import (
    LOCATOR_INSTRUCTIONS,
    LOCATOR_PROMPT_VERSION,
    RegulationSectionLocator,
)
from asset_servicing.ports.llm import (
    AgentDocument,
    ExtractionRequest,
    ExtractionResponse,
    LocateRequest,
    LocateResponse,
    LocationStatus,
    ValidationRequest,
    ValidationResponse,
)

pytestmark = pytest.mark.contract


class CapturingProvider:
    def __init__(self) -> None:
        self.request: LocateRequest | None = None

    def locate(self, request: LocateRequest) -> LocateResponse:
        self.request = request
        return LocateResponse(
            status=LocationStatus.NOT_FOUND,
            rationale="Seleção manual necessária.",
        )

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        raise AssertionError("unexpected extractor call")

    def validate(self, request: ValidationRequest) -> ValidationResponse:
        raise AssertionError("unexpected validator call")


def test_locator_uses_an_explicit_prompt_version() -> None:
    assert LOCATOR_PROMPT_VERSION == "locator-v1"


@pytest.mark.parametrize(
    "concept",
    ["emissão", "aplicação", "resgate", "amortização", "liquidação"],
)
def test_prompt_describes_each_semantic_concept(concept: str) -> None:
    assert concept in LOCATOR_INSTRUCTIONS.casefold()


def test_prompt_does_not_fix_chapter_three() -> None:
    normalized = LOCATOR_INSTRUCTIONS.casefold()

    assert "capítulo 3" not in normalized
    assert "capitulo 3" not in normalized


def test_prompt_does_not_fix_a_literal_title_or_page_range() -> None:
    normalized = LOCATOR_INSTRUCTIONS.casefold()

    assert "da emissão, aplicação e resgate de cotas" not in normalized
    assert "página 4" not in normalized
    assert "páginas 4" not in normalized


def test_prompt_declares_chapter_hint_as_non_binding() -> None:
    normalized = LOCATOR_INSTRUCTIONS.casefold()

    assert "pista" in normalized
    assert "não restrinja" in normalized


def test_prompt_requires_document_based_evidence() -> None:
    normalized = LOCATOR_INSTRUCTIONS.casefold()

    assert "justificativa" in normalized
    assert "documento" in normalized


def test_prompt_treats_pdf_content_as_untrusted_data() -> None:
    normalized = LOCATOR_INSTRUCTIONS.casefold()

    assert "dados não confiáveis" in normalized
    assert "ignore" in normalized


def test_case_use_sends_versioned_instructions_through_the_port() -> None:
    provider = CapturingProvider()
    locator = RegulationSectionLocator(provider)

    locator.locate(AgentDocument(filename="regulamento.pdf", content=b"%PDF"))

    assert provider.request is not None
    assert provider.request.prompt_version == LOCATOR_PROMPT_VERSION
    assert provider.request.instructions == LOCATOR_INSTRUCTIONS
