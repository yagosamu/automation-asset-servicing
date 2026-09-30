"""Executable offline composition root used by the browser acceptance test."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from itertools import cycle
from pathlib import Path

import pymupdf

from asset_servicing.adapters.export import ExcelExporter
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
from asset_servicing.ui.app import LocalAppServices, main

CREATED_AT = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


class OfflineProvider:
    """Recorded agent outputs for a deterministic, network-free browser run."""

    def locate(self, request: LocateRequest) -> LocateResponse:
        return LocateResponse(
            status=LocationStatus.FOUND,
            title="CAPÍTULO 6 – MOVIMENTAÇÃO DE COTAS",
            page_start=2,
            page_end=3,
            rationale="As páginas reúnem as regras de aplicação e resgate.",
        )

    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        return ExtractionResponse(
            variables=[
                AtomicVariable(
                    name="prazo_pagamento_resgate",
                    value="D+30",
                    evidence_text="O pagamento do resgate ocorrerá em até trinta dias.",
                    source_pages=[request.page_start],
                    source_kind=ExtractionSourceKind.PROSE,
                    clause_reference="Art. 10",
                ),
                AtomicVariable(
                    name="aplicacao_minima",
                    value="R$ 1.000,00",
                    evidence_text="A aplicação mínima é de mil reais.",
                    source_pages=[request.page_end],
                    source_kind=ExtractionSourceKind.TABLE,
                ),
            ]
        )

    def validate(self, request: ValidationRequest) -> ValidationResponse:
        low_confidence, supported = request.variables
        return ValidationResponse(
            validations=[
                VariableValidation(
                    variable_id=low_confidence.variable_id,
                    confidence=0.72,
                    evidence_support=EvidenceSupport.PARTIAL,
                    verdict=ValidationVerdict.PARTIALLY_SUPPORTED,
                    rationale="O prazo exige confirmação humana.",
                    issues=["Redação ambígua"],
                ),
                VariableValidation(
                    variable_id=supported.variable_id,
                    confidence=0.97,
                    evidence_support=EvidenceSupport.LITERAL,
                    verdict=ValidationVerdict.SUPPORTED,
                    rationale="Valor diretamente sustentado pela tabela.",
                    issues=[],
                ),
            ],
            omissions=[],
        )


def _ensure_pdf(path: Path) -> None:
    if path.is_file():
        return
    document = pymupdf.open()
    try:
        for page_number in range(1, 5):
            page = document.new_page()
            page.insert_text((72, 72), f"Página {page_number} do regulamento")
        document.save(path)
    finally:
        document.close()


def build_services(root: Path) -> LocalAppServices:
    """Build real local adapters around deterministic recorded agent outputs."""

    regulations_dir = root / "Regulamentos"
    regulations_dir.mkdir(parents=True, exist_ok=True)
    _ensure_pdf(regulations_dir / "regulamento-browser.pdf")
    repository = JsonRunRepository(root / "runs")
    provider = OfflineProvider()
    variable_ids = cycle(("variable-low", "variable-supported"))
    pipeline = RegulationPipeline(
        repository=repository,
        pdf_processor=PdfProcessor(),
        locator=RegulationSectionLocator(provider),
        extractor=RegulationVariableExtractor(provider, id_factory=lambda: next(variable_ids)),
        validator=RegulationVariableValidator(provider),
        models=AgentModels(
            locator="recorded-locator",
            extractor="recorded-extractor",
            validator="recorded-validator",
        ),
        usage_ledger=UsageLedger(),
        run_id_factory=lambda: "run-browser",
        clock=lambda: CREATED_AT,
    )
    delivery = RunDeliveryService(repository=repository, exporter=ExcelExporter(repository))
    return LocalAppServices(
        pipeline=pipeline,
        regulations_dir=regulations_dir,
        upload_dir=root / "uploads",
        review_service=ReviewService(repository=repository, clock=lambda: CREATED_AT),
        delivery_service=delivery,
    )


if __name__ == "__main__":
    runtime_root = Path(os.environ["ASSET_SERVICING_E2E_ROOT"])
    main(build_services(runtime_root))
