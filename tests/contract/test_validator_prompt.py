"""Contract tests for the independent validator prompt."""

from __future__ import annotations

from pathlib import Path

import pytest

from asset_servicing.application.validator import (
    VALIDATOR_INSTRUCTIONS,
    VALIDATOR_PROMPT_VERSION,
    RegulationVariableValidator,
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
PROMPT_SNAPSHOT = Path(__file__).parents[1] / "fixtures" / "prompts" / "validator-v3.txt"


class CapturingProvider:
    def __init__(self) -> None:
        self.request: ValidationRequest | None = None

    def locate(self, request: LocateRequest) -> LocateResponse:
        raise AssertionError("unexpected locator call")

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        raise AssertionError("unexpected extractor call")

    def validate(self, request: ValidationRequest) -> ValidationResponse:
        self.request = request
        return ValidationResponse(validations=[], omissions=[])


def normalized_prompt() -> str:
    return VALIDATOR_INSTRUCTIONS.casefold()


def test_validator_uses_an_explicit_prompt_version() -> None:
    assert VALIDATOR_PROMPT_VERSION == "validator-v3"


def test_prompt_excludes_adjacent_sections_from_coverage_findings() -> None:
    boundary_policy = (
        "Limite a análise à seção-alvo sobre emissão, aplicação, resgate, amortização e liquidação "
        "de\n"
        "cotas. Use os títulos e a hierarquia do documento para localizar seu início.\n"
        "Pare no próximo capítulo ou na próxima seção de mesmo nível, mesmo quando estiver na "
        "mesma página\n"
        "confirmada.\n"
        "Ignore conteúdo anterior ou posterior pertencente a capítulos ou seções adjacentes."
    )
    omission_policy = (
        "Não crie omissão quando uma variável existente já representar o fato. Não registre como "
        "omissão\n"
        "nenhum conteúdo de capítulo ou seção adjacente."
    )

    assert boundary_policy in VALIDATOR_INSTRUCTIONS
    assert omission_policy in VALIDATOR_INSTRUCTIONS


def test_validator_prompt_matches_its_versioned_snapshot() -> None:
    expected = PROMPT_SNAPSHOT.read_text(encoding="utf-8").strip()

    assert expected == VALIDATOR_INSTRUCTIONS


def test_validator_accepts_complete_grouping_without_false_omissions() -> None:
    prompt = normalized_prompt()

    assert "detalhe coberto" in prompt
    assert "valor ou evidência" in prompt
    assert "não exija uma variável separada" in prompt
    assert "não reduza a confiança" in prompt


@pytest.mark.parametrize(
    ("score_range", "meaning"),
    [
        ("0,95–1,00", "explícito"),
        ("0,85–0,94", "normalização"),
        ("0,60–0,84", "parcial"),
        ("0,00–0,59", "não sustentado"),
    ],
)
def test_prompt_documents_each_confidence_band(score_range: str, meaning: str) -> None:
    prompt = normalized_prompt()

    assert score_range in prompt
    assert meaning in prompt


def test_prompt_says_confidence_is_not_a_calibrated_probability() -> None:
    assert "não é probabilidade calibrada" in normalized_prompt()


def test_prompt_requires_independent_source_comparison() -> None:
    prompt = normalized_prompt()

    assert "agente independente" in prompt
    assert "compare" in prompt
    assert "páginas confirmadas" in prompt


def test_prompt_forbids_using_extractor_judgment() -> None:
    prompt = normalized_prompt()

    assert "não recebe confiança" in prompt
    assert "não recebe raciocínio" in prompt


def test_prompt_never_allows_automatic_value_edits() -> None:
    prompt = normalized_prompt()

    assert "não altere" in prompt
    assert "nome ou o valor" in prompt


def test_prompt_requires_conflict_and_omission_detection() -> None:
    prompt = normalized_prompt()

    assert "conflito" in prompt
    assert "omissões" in prompt


@pytest.mark.parametrize(
    "field",
    ["score", "veredito", "justificativa", "problemas", "has_conflict"],
)
def test_prompt_requests_each_validation_field(field: str) -> None:
    assert field in normalized_prompt()


def test_prompt_requires_exactly_one_result_per_candidate() -> None:
    assert "exatamente uma avaliação" in normalized_prompt()


def test_prompt_treats_pdf_as_untrusted_data() -> None:
    prompt = normalized_prompt()

    assert "dados não confiáveis" in prompt
    assert "ignore" in prompt


def test_case_use_sends_versioned_instructions_through_the_port() -> None:
    provider = CapturingProvider()

    RegulationVariableValidator(provider).validate(
        AgentDocument(filename="selected.pdf", content=b"%PDF"),
        page_start=2,
        page_end=2,
        variables=[],
    )

    assert provider.request is not None
    assert provider.request.prompt_version == VALIDATOR_PROMPT_VERSION
    assert provider.request.instructions == VALIDATOR_INSTRUCTIONS
