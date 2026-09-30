"""Contract tests for the versioned atomic extraction prompt."""

from __future__ import annotations

import pytest

from asset_servicing.application.extractor import (
    EXTRACTOR_INSTRUCTIONS,
    EXTRACTOR_PROMPT_VERSION,
    RegulationVariableExtractor,
)
from asset_servicing.ports.llm import (
    AgentDocument,
    ExtractionRequest,
    ExtractionResponse,
    LocateRequest,
    LocateResponse,
    ValidationRequest,
    ValidationResponse,
)

pytestmark = pytest.mark.contract


class CapturingProvider:
    def __init__(self) -> None:
        self.request: ExtractionRequest | None = None

    def locate(self, request: LocateRequest) -> LocateResponse:
        raise AssertionError("unexpected locator call")

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        self.request = request
        return ExtractionResponse(variables=[])

    def validate(self, request: ValidationRequest) -> ValidationResponse:
        raise AssertionError("unexpected validator call")


def normalized_prompt() -> str:
    return EXTRACTOR_INSTRUCTIONS.casefold()


def test_extractor_uses_an_explicit_prompt_version() -> None:
    assert EXTRACTOR_PROMPT_VERSION == "extractor-v2"


def test_prompt_limits_extraction_to_the_target_section() -> None:
    prompt = normalized_prompt()

    assert "seção-alvo" in prompt
    assert "próximo capítulo" in prompt
    assert "mesmo nível" in prompt
    assert "mesma página" in prompt
    assert "ignore" in prompt


def test_prompt_treats_pdf_as_untrusted_data() -> None:
    prompt = normalized_prompt()

    assert "dados não confiáveis" in prompt
    assert "ignore" in prompt


def test_prompt_covers_tables_and_prose() -> None:
    prompt = normalized_prompt()

    assert "tabelas" in prompt
    assert "texto corrido" in prompt


def test_prompt_requires_independent_facts_to_be_separate() -> None:
    prompt = normalized_prompt()

    assert "fatos independentes" in prompt
    assert "variáveis separadas" in prompt


def test_prompt_makes_preferred_vocabulary_non_binding() -> None:
    prompt = normalized_prompt()

    assert "vocabulário preferencial" in prompt
    assert "nome semântico novo" in prompt


@pytest.mark.parametrize(
    "required_field",
    ["nome", "valor", "evidência", "páginas", "origem", "cláusula"],
)
def test_prompt_requests_every_variable_field(required_field: str) -> None:
    assert required_field in normalized_prompt()


def test_prompt_does_not_request_extractor_confidence() -> None:
    prompt = normalized_prompt()

    assert "não atribua confiança" in prompt
    assert "não valide" in prompt


def test_prompt_accepts_prose_only_sections() -> None:
    prompt = normalized_prompt()

    assert "ausência de tabela não é erro" in prompt


def test_case_use_sends_versioned_instructions_through_the_port() -> None:
    provider = CapturingProvider()

    RegulationVariableExtractor(provider).extract(
        AgentDocument(filename="selected.pdf", content=b"%PDF"),
        page_start=3,
        page_end=5,
    )

    assert provider.request is not None
    assert provider.request.prompt_version == EXTRACTOR_PROMPT_VERSION
    assert provider.request.instructions == EXTRACTOR_INSTRUCTIONS
