"""Contract tests for the three independent LLM agent boundaries."""

from __future__ import annotations

from typing import cast

import pytest
from pydantic import BaseModel, ValidationError

from asset_servicing.ports.llm import (
    AgentDocument,
    AtomicVariable,
    ExtractionRequest,
    ExtractionResponse,
    ExtractionSourceKind,
    LLMProvider,
    LocateRequest,
    LocateResponse,
    LocationStatus,
    OmissionFinding,
    ValidationCandidate,
    ValidationRequest,
    ValidationResponse,
    ValidationVerdict,
    VariableValidation,
)

pytestmark = pytest.mark.contract


def make_document() -> AgentDocument:
    return AgentDocument(filename="regulamento.pdf", content=b"%PDF-contract-fixture")


def make_atomic_variable(**updates: object) -> AtomicVariable:
    data: dict[str, object] = {
        "name": "prazo_pagamento_resgate",
        "value": "30 dias corridos",
        "evidence_text": "O pagamento será realizado em até 30 dias corridos.",
        "source_pages": [7],
        "source_kind": ExtractionSourceKind.PROSE,
        "clause_reference": "Art. 12",
    }
    data.update(updates)
    return AtomicVariable.model_validate(data)


def make_candidate(**updates: object) -> ValidationCandidate:
    data: dict[str, object] = {
        "variable_id": "variable-001",
        "name": "prazo_pagamento_resgate",
        "value": "30 dias corridos",
        "evidence_text": "O pagamento será realizado em até 30 dias corridos.",
        "source_pages": [7],
        "source_kind": ExtractionSourceKind.PROSE,
        "clause_reference": "Art. 12",
    }
    data.update(updates)
    return ValidationCandidate.model_validate(data)


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (
            LocateRequest,
            {
                "instructions": "Localize a seção relevante.",
                "prompt_version": "locator-v1",
            },
        ),
        (
            ExtractionRequest,
            {
                "page_start": 4,
                "page_end": 6,
                "instructions": "Extraia fatos atômicos.",
                "prompt_version": "extractor-v1",
                "preferred_vocabulary": [],
            },
        ),
        (
            ValidationRequest,
            {
                "page_start": 4,
                "page_end": 6,
                "instructions": "Valide contra a fonte.",
                "prompt_version": "validator-v1",
                "variables": [make_candidate()],
            },
        ),
    ],
)
def test_each_agent_request_requires_its_document(
    model: type[BaseModel], payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_agent_requests_and_responses_are_distinct_public_contracts() -> None:
    assert LocateRequest is not ExtractionRequest
    assert ExtractionRequest is not ValidationRequest
    assert LocateResponse is not ExtractionResponse
    assert ExtractionResponse is not ValidationResponse


def test_locator_response_exposes_document_based_location() -> None:
    response = LocateResponse(
        status=LocationStatus.FOUND,
        title="Capítulo 3 - Da emissão, aplicação e resgate de cotas",
        page_start=4,
        page_end=6,
        rationale="A seção reúne as regras de movimentação das cotas.",
    )

    assert response.title == "Capítulo 3 - Da emissão, aplicação e resgate de cotas"
    assert (response.page_start, response.page_end) == (4, 6)
    assert response.rationale == "A seção reúne as regras de movimentação das cotas."


def test_locator_response_rejects_missing_fields_when_section_is_found() -> None:
    with pytest.raises(ValidationError, match="found location requires"):
        LocateResponse(
            status=LocationStatus.FOUND,
            rationale="A seção parece compatível.",
        )


def test_locator_response_represents_a_recoverable_not_found_result() -> None:
    response = LocateResponse(
        status=LocationStatus.NOT_FOUND,
        rationale="Nenhuma seção semanticamente compatível foi encontrada.",
    )

    assert response.status is LocationStatus.NOT_FOUND
    assert response.title is None
    assert response.page_start is None
    assert response.page_end is None


def test_locator_response_rejects_an_unknown_status() -> None:
    with pytest.raises(ValidationError):
        LocateResponse.model_validate(
            {
                "status": "uncertain",
                "rationale": "Resultado fora do contrato.",
            }
        )


def test_locator_response_rejects_an_inverted_page_range() -> None:
    with pytest.raises(ValidationError, match="page_end"):
        LocateResponse(
            status=LocationStatus.FOUND,
            title="Capítulo 3",
            page_start=8,
            page_end=7,
            rationale="Intervalo retornado pelo localizador.",
        )


def test_extraction_request_carries_confirmed_pages_and_hybrid_vocabulary() -> None:
    request = ExtractionRequest(
        document=make_document(),
        page_start=4,
        page_end=6,
        instructions="Extraia um fato independente por variável.",
        prompt_version="extractor-v1",
        preferred_vocabulary=["prazo_pagamento_resgate", "taxa_saida"],
    )

    assert (request.page_start, request.page_end) == (4, 6)
    assert request.preferred_vocabulary == ["prazo_pagamento_resgate", "taxa_saida"]


def test_extraction_request_rejects_pages_outside_an_ordered_positive_range() -> None:
    with pytest.raises(ValidationError):
        ExtractionRequest(
            document=make_document(),
            page_start=5,
            page_end=4,
            instructions="Extraia fatos.",
            prompt_version="extractor-v1",
            preferred_vocabulary=[],
        )


def test_atomic_variable_contains_value_and_source_evidence() -> None:
    variable = make_atomic_variable()

    assert variable.name == "prazo_pagamento_resgate"
    assert variable.value == "30 dias corridos"
    assert variable.evidence_text == "O pagamento será realizado em até 30 dias corridos."
    assert variable.source_pages == [7]
    assert variable.source_kind is ExtractionSourceKind.PROSE
    assert variable.clause_reference == "Art. 12"


def test_atomic_variable_rejects_a_missing_value() -> None:
    with pytest.raises(ValidationError):
        AtomicVariable.model_validate(
            {
                "name": "prazo_pagamento_resgate",
                "evidence_text": "Trecho de suporte.",
                "source_pages": [7],
                "source_kind": "prose",
            }
        )


def test_atomic_variable_rejects_an_invalid_source_enum() -> None:
    with pytest.raises(ValidationError):
        make_atomic_variable(source_kind="spreadsheet")


def test_extraction_response_rejects_uncontracted_fields() -> None:
    with pytest.raises(ValidationError):
        ExtractionResponse.model_validate(
            {
                "variables": [make_atomic_variable().model_dump()],
                "confidence": 0.99,
            }
        )


def test_validation_request_contains_only_extracted_facts_and_source() -> None:
    request = ValidationRequest(
        document=make_document(),
        page_start=4,
        page_end=6,
        instructions="Compare cada variável com o documento.",
        prompt_version="validator-v1",
        variables=[make_candidate()],
    )

    candidate_fields = set(type(request.variables[0]).model_fields)
    assert candidate_fields == {
        "variable_id",
        "name",
        "value",
        "evidence_text",
        "source_pages",
        "source_kind",
        "clause_reference",
    }
    assert "confidence" not in candidate_fields
    assert "rationale" not in candidate_fields


def test_validation_request_rejects_extractor_confidence_or_reasoning() -> None:
    payload = make_candidate().model_dump()
    payload.update({"confidence": 0.98, "rationale": "Confiança sugerida pelo extrator."})

    with pytest.raises(ValidationError):
        ValidationCandidate.model_validate(payload)


def test_variable_validation_records_score_verdict_rationale_and_issues() -> None:
    result = VariableValidation(
        variable_id="variable-001",
        confidence=0.72,
        verdict=ValidationVerdict.PARTIALLY_SUPPORTED,
        rationale="O prazo está explícito, mas a contagem não está definida.",
        issues=["Unidade de contagem ambígua"],
        has_conflict=True,
    )

    assert result.confidence == 0.72
    assert result.verdict is ValidationVerdict.PARTIALLY_SUPPORTED
    assert result.rationale == "O prazo está explícito, mas a contagem não está definida."
    assert result.issues == ["Unidade de contagem ambígua"]
    assert result.has_conflict is True


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_variable_validation_rejects_score_outside_closed_unit_interval(
    confidence: float,
) -> None:
    with pytest.raises(ValidationError):
        VariableValidation(
            variable_id="variable-001",
            confidence=confidence,
            verdict=ValidationVerdict.SUPPORTED,
            rationale="Valor diretamente sustentado.",
            issues=[],
        )


def test_variable_validation_rejects_an_invalid_verdict_enum() -> None:
    with pytest.raises(ValidationError):
        VariableValidation.model_validate(
            {
                "variable_id": "variable-001",
                "confidence": 0.9,
                "verdict": "probably_supported",
                "rationale": "Veredito fora do contrato.",
                "issues": [],
            }
        )


def test_validation_response_represents_possible_omissions() -> None:
    omission = OmissionFinding(
        description="A seção menciona carência sem variável correspondente.",
        suggested_name="carencia_resgate",
        evidence_text="O prazo de carência será de 30 dias.",
        source_pages=[5],
    )
    response = ValidationResponse(validations=[], omissions=[omission])

    assert response.omissions[0].suggested_name == "carencia_resgate"
    assert response.omissions[0].evidence_text == "O prazo de carência será de 30 dias."
    assert response.omissions[0].source_pages == [5]


def test_omission_rejects_missing_evidence() -> None:
    with pytest.raises(ValidationError):
        OmissionFinding.model_validate(
            {
                "description": "Possível regra ausente.",
                "source_pages": [5],
            }
        )


@pytest.mark.parametrize(
    "response_model",
    [LocateResponse, ExtractionResponse, ValidationResponse],
)
def test_agent_response_json_schemas_forbid_additional_properties(
    response_model: type[BaseModel],
) -> None:
    schema = response_model.model_json_schema()

    assert schema["additionalProperties"] is False


def test_llm_provider_is_a_runtime_checkable_three_agent_port() -> None:
    class Provider:
        def locate(self, request: LocateRequest) -> LocateResponse:
            return cast(LocateResponse, request)

        def extract(self, request: ExtractionRequest) -> ExtractionResponse:
            return cast(ExtractionResponse, request)

        def validate(self, request: ValidationRequest) -> ValidationResponse:
            return cast(ValidationResponse, request)

    assert isinstance(Provider(), LLMProvider)
