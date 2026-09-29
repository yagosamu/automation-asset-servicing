"""Unit tests for extraction of atomic regulation variables."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from asset_servicing.application.extractor import RegulationVariableExtractor
from asset_servicing.domain import SourceKind
from asset_servicing.ports.llm import (
    AgentDocument,
    AtomicVariable,
    ExtractionRequest,
    ExtractionResponse,
    ExtractionSourceKind,
    LocateRequest,
    LocateResponse,
    ValidationRequest,
    ValidationResponse,
)

pytestmark = pytest.mark.unit
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "extractor"


class StubLLMProvider:
    """Capture extraction requests and return one validated fixture."""

    def __init__(self, response: ExtractionResponse) -> None:
        self.response = response
        self.extraction_requests: list[ExtractionRequest] = []

    def locate(self, request: LocateRequest) -> LocateResponse:
        raise AssertionError("locate must not be called by the extractor")

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        self.extraction_requests.append(request)
        return self.response

    def validate(self, request: ValidationRequest) -> ValidationResponse:
        raise AssertionError("validate must not be called by the extractor")


def load_response(name: str) -> ExtractionResponse:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return ExtractionResponse.model_validate(data)


def make_document() -> AgentDocument:
    return AgentDocument(filename="regulamento-paginas-12-13.pdf", content=b"%PDF-selected")


def id_factory(*values: str) -> Callable[[], str]:
    return iter(values).__next__


def test_table_fact_maps_every_required_domain_field() -> None:
    provider = StubLLMProvider(load_response("multi_page_table.json"))
    extractor = RegulationVariableExtractor(provider, id_factory=id_factory("var-001"))

    variables = extractor.extract(
        make_document(),
        page_start=12,
        page_end=13,
        preferred_vocabulary=["prazo_pagamento_resgate"],
    )

    assert [variable.model_dump(mode="json") for variable in variables] == [
        {
            "id": "var-001",
            "canonical_name": "prazo_pagamento_resgate",
            "original_name": "prazo_pagamento_resgate",
            "original_value": "até 5 dias úteis após a conversão",
            "current_name": "prazo_pagamento_resgate",
            "current_value": "até 5 dias úteis após a conversão",
            "evidence_text": (
                "O pagamento do resgate será efetuado em até 5 (cinco) dias úteis após a "
                "data de conversão."
            ),
            "source_pages": [12, 13],
            "source_kind": "table",
            "clause_reference": "Tabela do Art. 18",
            "reviewed": False,
            "review_status": "pending",
        }
    ]


def test_cell_with_two_independent_facts_becomes_two_variables() -> None:
    provider = StubLLMProvider(load_response("split_cell.json"))
    extractor = RegulationVariableExtractor(
        provider,
        id_factory=id_factory("var-conversao", "var-pagamento"),
    )

    variables = extractor.extract(make_document(), page_start=9, page_end=9)

    assert [
        (variable.id, variable.current_name, variable.current_value) for variable in variables
    ] == [
        ("var-conversao", "prazo_conversao_resgate", "D+30 dias corridos"),
        ("var-pagamento", "prazo_pagamento_resgate", "D+2 dias úteis da conversão"),
    ]


def test_duplicate_semantic_names_remain_distinct_until_review() -> None:
    provider = StubLLMProvider(
        ExtractionResponse(
            variables=[
                AtomicVariable(
                    name="prazo_resgate",
                    value="D+30",
                    evidence_text="A conversão ocorrerá em trinta dias.",
                    source_pages=[7],
                    source_kind=ExtractionSourceKind.PROSE,
                ),
                AtomicVariable(
                    name="prazo_resgate",
                    value="D+60",
                    evidence_text="Em outra classe, a conversão ocorrerá em sessenta dias.",
                    source_pages=[8],
                    source_kind=ExtractionSourceKind.TABLE,
                ),
            ]
        )
    )
    extractor = RegulationVariableExtractor(
        provider,
        id_factory=id_factory("var-class-a", "var-class-b"),
    )

    variables = extractor.extract(make_document(), page_start=7, page_end=8)

    assert [
        (
            variable.id,
            variable.current_name,
            variable.current_value,
            variable.evidence_text,
            variable.source_pages,
        )
        for variable in variables
    ] == [
        (
            "var-class-a",
            "prazo_resgate",
            "D+30",
            "A conversão ocorrerá em trinta dias.",
            [7],
        ),
        (
            "var-class-b",
            "prazo_resgate",
            "D+60",
            "Em outra classe, a conversão ocorrerá em sessenta dias.",
            [8],
        ),
    ]


def test_section_without_table_keeps_prose_fact() -> None:
    provider = StubLLMProvider(load_response("prose_only.json"))
    extractor = RegulationVariableExtractor(provider, id_factory=id_factory("var-prose"))

    variables = extractor.extract(make_document(), page_start=21, page_end=21)

    assert len(variables) == 1
    assert variables[0].source_kind is SourceKind.PROSE
    assert variables[0].evidence_text.startswith("As cotas estarão sujeitas")
    assert variables[0].clause_reference == "Art. 24, § 1º"


def test_rule_outside_vocabulary_keeps_dynamic_semantic_name() -> None:
    provider = StubLLMProvider(load_response("dynamic_name.json"))
    extractor = RegulationVariableExtractor(provider, id_factory=id_factory("var-dynamic"))

    variables = extractor.extract(
        make_document(),
        page_start=16,
        page_end=16,
        preferred_vocabulary=["prazo_pagamento_resgate"],
    )

    assert variables[0].canonical_name == "resgate_compulsorio_por_desenquadramento"
    assert variables[0].current_value == "permitido para reenquadramento da carteira"


def test_preferred_vocabulary_is_forwarded_without_mutation() -> None:
    provider = StubLLMProvider(ExtractionResponse(variables=[]))
    vocabulary = ["prazo_conversao_resgate", "taxa_saida"]

    RegulationVariableExtractor(provider).extract(
        make_document(),
        page_start=4,
        page_end=6,
        preferred_vocabulary=vocabulary,
    )

    assert provider.extraction_requests[0].preferred_vocabulary == vocabulary


def test_confirmed_page_interval_is_forwarded() -> None:
    provider = StubLLMProvider(ExtractionResponse(variables=[]))

    RegulationVariableExtractor(provider).extract(
        make_document(),
        page_start=12,
        page_end=13,
    )

    request = provider.extraction_requests[0]
    assert (request.page_start, request.page_end) == (12, 13)


def test_selected_document_is_forwarded_unchanged() -> None:
    document = make_document()
    provider = StubLLMProvider(ExtractionResponse(variables=[]))

    RegulationVariableExtractor(provider).extract(document, page_start=12, page_end=13)

    assert provider.extraction_requests[0].document is document


def test_empty_structured_response_returns_empty_variable_list() -> None:
    provider = StubLLMProvider(ExtractionResponse(variables=[]))

    variables = RegulationVariableExtractor(provider).extract(
        make_document(), page_start=1, page_end=1
    )

    assert variables == []
