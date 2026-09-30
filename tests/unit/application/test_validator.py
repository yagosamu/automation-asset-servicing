"""Unit tests for independent validation and uncertainty routing."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from asset_servicing.application.validator import (
    RegulationVariableValidator,
    ValidationBatch,
    ValidationCoverageError,
)
from asset_servicing.domain import (
    ConfidenceBasis,
    ExtractedVariable,
    ReviewReason,
    Run,
    RunState,
    SourceKind,
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

pytestmark = pytest.mark.unit
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "validator"


class StubLLMProvider:
    """Capture validation requests and return one structured response."""

    def __init__(self, response: ValidationResponse) -> None:
        self.response = response
        self.validation_requests: list[ValidationRequest] = []

    def locate(self, request: LocateRequest) -> LocateResponse:
        raise AssertionError("locate must not be called by the validator")

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        raise AssertionError("extract must not be called by the validator")

    def validate(self, request: ValidationRequest) -> ValidationResponse:
        self.validation_requests.append(request)
        return self.response


def load_response() -> ValidationResponse:
    data = json.loads((FIXTURES / "adversarial_response.json").read_text(encoding="utf-8"))
    return ValidationResponse.model_validate(data)


def make_variable(variable_id: str, name: str, value: str) -> ExtractedVariable:
    return ExtractedVariable(
        id=variable_id,
        canonical_name=name,
        original_name=name,
        original_value=value,
        current_name=name,
        current_value=value,
        evidence_text=f"Trecho de evidência para {name}.",
        source_pages=[21],
        source_kind=SourceKind.PROSE,
        clause_reference="Art. 20",
    )


def make_variables() -> list[ExtractedVariable]:
    return [
        make_variable("var-correct", "prazo_pagamento_resgate", "D+5"),
        make_variable("var-ambiguous", "carencia_aplicacao", "180 dias"),
        make_variable("var-conflict", "prazo_conversao_resgate", "D+30"),
        make_variable("var-unsupported", "taxa_saida", "2%"),
    ]


def make_document() -> AgentDocument:
    return AgentDocument(filename="selected-pages.pdf", content=b"%PDF-selected")


def id_factory(*values: str) -> Callable[[], str]:
    return iter(values).__next__


def validate_fixture() -> tuple[list[ExtractedVariable], ValidationBatch]:
    variables = make_variables()
    validator = RegulationVariableValidator(
        StubLLMProvider(load_response()),
        finding_id_factory=id_factory("finding-omission"),
    )
    batch = validator.validate(
        make_document(),
        page_start=21,
        page_end=22,
        variables=variables,
    )
    return variables, batch


def make_reviewing_run(variables: list[ExtractedVariable]) -> Run:
    return Run(
        run_id="run-validation",
        document_name="regulamento.pdf",
        document_sha256="a" * 64,
        page_count=30,
        created_at=datetime(2026, 9, 28, 10, 0, tzinfo=UTC),
        state=RunState.REVIEWING,
        variables=variables,
    )


def test_validator_maps_score_verdict_rationale_issues_and_conflict() -> None:
    _, batch = validate_fixture()

    assert [validation.model_dump(mode="json") for validation in batch.validations] == [
        {
            "variable_id": "var-correct",
            "confidence": 0.97,
            "evidence_support": "literal",
            "verdict": "supported",
            "rationale": "O valor está explícito e completo na fonte.",
            "issues": [],
            "has_conflict": False,
            "confidence_basis": "llm_rubric",
        },
        {
            "variable_id": "var-ambiguous",
            "confidence": 0.72,
            "evidence_support": "partial",
            "verdict": "partially_supported",
            "rationale": "A fonte sustenta apenas parte da condição extraída.",
            "issues": ["A condição temporal depende do parágrafo seguinte."],
            "has_conflict": False,
            "confidence_basis": "llm_rubric",
        },
        {
            "variable_id": "var-conflict",
            "confidence": 0.35,
            "evidence_support": "unsupported",
            "verdict": "unsupported",
            "rationale": "O prazo extraído contradiz o prazo expresso na fonte.",
            "issues": ["A variável informa D+30, mas a fonte informa D+60."],
            "has_conflict": True,
            "confidence_basis": "llm_rubric",
        },
        {
            "variable_id": "var-unsupported",
            "confidence": 0.2,
            "evidence_support": "unsupported",
            "verdict": "unsupported",
            "rationale": "O valor extraído não aparece nas páginas confirmadas.",
            "issues": ["Não há suporte documental para a taxa informada."],
            "has_conflict": False,
            "confidence_basis": "llm_rubric",
        },
    ]


def test_possible_omission_maps_to_pending_coverage_finding() -> None:
    _, batch = validate_fixture()

    assert [finding.model_dump(mode="json") for finding in batch.coverage_findings] == [
        {
            "id": "finding-omission",
            "description": "A carência de resgate aparece na fonte, mas não foi extraída.",
            "suggested_name": "carencia_resgate",
            "evidence_text": "As cotas estarão sujeitas à carência de 180 dias.",
            "source_pages": [22],
            "review_status": "pending",
        }
    ]


def test_all_adversarial_results_and_omission_enter_review_queue() -> None:
    variables, batch = validate_fixture()
    run = make_reviewing_run(variables)
    run.validations = batch.validations
    run.coverage_findings = batch.coverage_findings

    pending = run.pending_items()

    assert {item.item_id for item in pending} == {
        "variable:var-ambiguous",
        "variable:var-conflict",
        "variable:var-unsupported",
        "finding:finding-omission",
    }


def test_correct_supported_result_stays_out_of_review_queue() -> None:
    variables, batch = validate_fixture()
    run = make_reviewing_run(variables)
    run.validations = batch.validations
    run.coverage_findings = batch.coverage_findings

    assert "variable:var-correct" not in {item.item_id for item in run.pending_items()}


def test_ambiguous_result_routes_by_low_confidence_and_verdict() -> None:
    variables, batch = validate_fixture()
    run = make_reviewing_run(variables)
    run.validations = batch.validations

    item = next(item for item in run.pending_items() if item.variable_id == "var-ambiguous")

    assert item.reasons == [ReviewReason.LOW_CONFIDENCE, ReviewReason.VERDICT]


def test_contradictory_result_routes_by_score_verdict_and_conflict() -> None:
    variables, batch = validate_fixture()
    run = make_reviewing_run(variables)
    run.validations = batch.validations

    item = next(item for item in run.pending_items() if item.variable_id == "var-conflict")

    assert item.reasons == [
        ReviewReason.LOW_CONFIDENCE,
        ReviewReason.VERDICT,
        ReviewReason.CONFLICT,
    ]


def test_validation_never_changes_extracted_names_or_values() -> None:
    variables = make_variables()
    before = [(variable.current_name, variable.current_value) for variable in variables]
    validator = RegulationVariableValidator(
        StubLLMProvider(load_response()),
        finding_id_factory=id_factory("finding-omission"),
    )

    validator.validate(make_document(), page_start=21, page_end=22, variables=variables)

    assert [(variable.current_name, variable.current_value) for variable in variables] == before


def test_request_contains_source_fields_without_extractor_judgment() -> None:
    provider = StubLLMProvider(load_response())
    variables = make_variables()
    validator = RegulationVariableValidator(
        provider,
        finding_id_factory=id_factory("finding-omission"),
    )

    validator.validate(make_document(), page_start=21, page_end=22, variables=variables)

    candidate = provider.validation_requests[0].variables[0].model_dump(mode="json")
    assert candidate == {
        "variable_id": "var-correct",
        "name": "prazo_pagamento_resgate",
        "value": "D+5",
        "evidence_text": "Trecho de evidência para prazo_pagamento_resgate.",
        "source_pages": [21],
        "source_kind": "prose",
        "clause_reference": "Art. 20",
    }
    assert "confidence" not in candidate
    assert "verdict" not in candidate
    assert "rationale" not in candidate


def test_request_forwards_confirmed_document_and_interval() -> None:
    provider = StubLLMProvider(load_response())
    document = make_document()
    validator = RegulationVariableValidator(
        provider,
        finding_id_factory=id_factory("finding-omission"),
    )

    validator.validate(document, page_start=21, page_end=22, variables=make_variables())

    request = provider.validation_requests[0]
    assert request.document is document
    assert (request.page_start, request.page_end) == (21, 22)


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            ValidationResponse(validations=[], omissions=[]),
            "missing validation results",
        ),
        (
            ValidationResponse(
                validations=[load_response().validations[0], load_response().validations[0]],
                omissions=[],
            ),
            "duplicate validation results",
        ),
        (
            ValidationResponse.model_validate(
                {
                    "validations": [
                        {
                            **load_response().validations[0].model_dump(mode="json"),
                            "variable_id": "var-unknown",
                        }
                    ],
                    "omissions": [],
                }
            ),
            "unknown validation results",
        ),
    ],
)
def test_validator_rejects_incomplete_or_unmatched_coverage(
    response: ValidationResponse,
    message: str,
) -> None:
    validator = RegulationVariableValidator(StubLLMProvider(response))

    with pytest.raises(ValidationCoverageError, match=message):
        validator.validate(
            make_document(),
            page_start=21,
            page_end=22,
            variables=make_variables(),
        )


def test_confidence_is_explicitly_attributed_to_llm_rubric() -> None:
    _, batch = validate_fixture()

    assert {validation.confidence_basis for validation in batch.validations} == {
        ConfidenceBasis.LLM_RUBRIC
    }
