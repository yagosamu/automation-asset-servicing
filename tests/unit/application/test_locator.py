"""Unit tests for the semantic regulation section locator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from asset_servicing.application.locator import RegulationSectionLocator
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

pytestmark = pytest.mark.unit
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "locator"


class StubLLMProvider:
    """Record locator calls while refusing unrelated agent operations."""

    def __init__(self, response: LocateResponse) -> None:
        self.response = response
        self.locate_requests: list[LocateRequest] = []

    def locate(self, request: LocateRequest) -> LocateResponse:
        self.locate_requests.append(request)
        return self.response

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        raise AssertionError("extract must not be called by the locator")

    def validate(self, request: ValidationRequest) -> ValidationResponse:
        raise AssertionError("validate must not be called by the locator")


def make_document() -> AgentDocument:
    return AgentDocument(filename="regulamento.pdf", content=b"%PDF-completo")


def found_response() -> LocateResponse:
    return LocateResponse(
        status=LocationStatus.FOUND,
        title="Seção de movimentação de cotas",
        page_start=7,
        page_end=10,
        rationale="As páginas concentram as regras relevantes de movimentação.",
    )


def test_found_response_maps_to_unconfirmed_domain_location() -> None:
    provider = StubLLMProvider(found_response())

    outcome = RegulationSectionLocator(provider).locate(make_document())

    assert outcome.location is not None
    assert outcome.location.model_dump() == {
        "title": "Seção de movimentação de cotas",
        "page_start": 7,
        "page_end": 10,
        "rationale": "As páginas concentram as regras relevantes de movimentação.",
        "confirmed": False,
    }


def test_found_response_does_not_request_manual_interval() -> None:
    outcome = RegulationSectionLocator(StubLLMProvider(found_response())).locate(make_document())

    assert outcome.manual_selection_required is False


def test_not_found_is_recoverable_through_manual_interval() -> None:
    provider = StubLLMProvider(
        LocateResponse(
            status=LocationStatus.NOT_FOUND,
            rationale="Não há evidência suficiente para delimitar a seção.",
        )
    )

    outcome = RegulationSectionLocator(provider).locate(make_document())

    assert outcome.location is None
    assert outcome.manual_selection_required is True
    assert outcome.rationale == "Não há evidência suficiente para delimitar a seção."


def test_locator_sends_the_complete_document_unchanged() -> None:
    document = make_document()
    provider = StubLLMProvider(found_response())

    RegulationSectionLocator(provider).locate(document)

    assert provider.locate_requests[0].document is document


def test_locator_forwards_optional_chapter_hint() -> None:
    provider = StubLLMProvider(found_response())

    RegulationSectionLocator(provider).locate(make_document(), chapter_hint=6)

    assert provider.locate_requests[0].chapter_hint == 6


def test_locator_allows_no_chapter_hint() -> None:
    provider = StubLLMProvider(found_response())

    RegulationSectionLocator(provider).locate(make_document())

    assert provider.locate_requests[0].chapter_hint is None


def test_chapter_hint_does_not_reject_a_different_chapter_result() -> None:
    fixture_data = json.loads((FIXTURES / "chapter_6_response.json").read_text(encoding="utf-8"))
    provider = StubLLMProvider(LocateResponse.model_validate(fixture_data))

    outcome = RegulationSectionLocator(provider).locate(make_document(), chapter_hint=3)

    assert outcome.location is not None
    assert outcome.location.title == "CAPÍTULO 6 - DAS MOVIMENTAÇÕES DE COTAS"
    assert (outcome.location.page_start, outcome.location.page_end) == (18, 23)


def test_locator_invokes_only_one_agent_call() -> None:
    provider = StubLLMProvider(found_response())

    RegulationSectionLocator(provider).locate(make_document(), chapter_hint=4)

    assert len(provider.locate_requests) == 1
