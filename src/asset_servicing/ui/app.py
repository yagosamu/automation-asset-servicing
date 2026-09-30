"""Streamlit flow for document intake and section confirmation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import streamlit as st

from asset_servicing.application.delivery_service import ExportArtifact, RunSummary
from asset_servicing.domain import (
    CoverageFinding,
    ExtractedVariable,
    ReviewItemKind,
    Run,
    SectionLocation,
)

_VERDICT_LABELS = {
    "supported": "suportado",
    "partially_supported": "parcialmente suportado",
    "unsupported": "não suportado",
}

_ACTIVE_RUN_VIEW_KEYS = (
    "_asset_servicing_review_run_id",
    "_review_flash",
    "location_run_id",
    "location_page_count",
    "location_confirmed",
    "location_previews",
    "location_result",
    "location_page_start",
    "location_page_end",
    "confirmed_page_start",
    "confirmed_page_end",
)


class Preview(Protocol):
    page_number: int
    path: Path


class DocumentLocationPipeline(Protocol):
    """Public pipeline operations consumed by the intake UI."""

    def create_run(self, source_pdf: Path) -> Run: ...

    def locate_section(
        self,
        run_id: str,
        *,
        chapter_hint: int | None = None,
    ) -> SectionLocation | None: ...

    def confirm_location(self, run_id: str, *, page_start: int, page_end: int) -> Run: ...

    def preview_pages(
        self,
        run_id: str,
        *,
        page_start: int,
        page_end: int,
    ) -> list[Preview]: ...

    def extract(
        self,
        run_id: str,
        *,
        preferred_vocabulary: list[str] | None = None,
    ) -> list[ExtractedVariable]: ...

    def validate(self, run_id: str) -> object: ...


class ReviewWorkflow(Protocol):
    """Public review operations consumed by the results UI."""

    def get_run(self, run_id: str) -> Run: ...

    def confirm(
        self,
        run_id: str,
        variable_id: str,
        *,
        note: str | None = None,
    ) -> ExtractedVariable: ...

    def edit(
        self,
        run_id: str,
        variable_id: str,
        *,
        name: str,
        value: str,
        note: str | None = None,
    ) -> ExtractedVariable: ...

    def mark_not_applicable(
        self,
        run_id: str,
        variable_id: str,
        *,
        note: str,
    ) -> ExtractedVariable: ...

    def add_missing(
        self,
        run_id: str,
        finding_id: str,
        *,
        name: str,
        value: str,
        evidence: str,
        note: str | None = None,
    ) -> ExtractedVariable: ...

    def dismiss_omission(
        self,
        run_id: str,
        finding_id: str,
        *,
        note: str,
    ) -> CoverageFinding: ...


class DeliveryWorkflow(Protocol):
    """Public export and summary operations consumed by the delivery UI."""

    def get_run(self, run_id: str) -> Run: ...

    def export_preliminary(self, run_id: str) -> ExportArtifact: ...

    def export_final(self, run_id: str) -> ExportArtifact: ...

    def get_export(self, run_id: str, *, final: bool) -> ExportArtifact | None: ...

    def summary(self, run_id: str) -> RunSummary: ...


@dataclass(frozen=True, slots=True)
class LocalAppServices:
    """Concrete local dependencies supplied by an executable composition root."""

    pipeline: DocumentLocationPipeline
    regulations_dir: Path
    upload_dir: Path
    review_service: ReviewWorkflow
    delivery_service: DeliveryWorkflow


def render_document_location(
    *,
    pipeline: DocumentLocationPipeline,
    regulations_dir: Path,
    upload_dir: Path,
) -> None:
    """Render the intake and semantic-location stage."""

    st.title("Extração de Regulamentos")
    source_kind = st.radio(
        "Origem do documento",
        ["Pasta do projeto", "Upload"],
        horizontal=True,
        key="document_source",
        on_change=_clear_active_run_view,
    )
    source_path: Path | None = None
    if source_kind == "Pasta do projeto":
        filenames = sorted(path.name for path in Path(regulations_dir).glob("*.pdf"))
        selected = st.selectbox(
            "Regulamento",
            filenames,
            key="project_pdf",
            placeholder="Nenhum PDF encontrado",
            on_change=_clear_active_run_view,
        )
        if selected:
            source_path = Path(regulations_dir) / selected
    else:
        upload = st.file_uploader(
            "Selecione um regulamento PDF",
            type=["pdf"],
            key="uploaded_pdf",
            on_change=_clear_active_run_view,
        )
        if upload is not None:
            upload_dir = Path(upload_dir)
            upload_dir.mkdir(parents=True, exist_ok=True)
            source_path = upload_dir / Path(upload.name).name
            source_path.write_bytes(upload.getvalue())

    chapter_hint = st.number_input(
        "Capítulo esperado (opcional)",
        min_value=1,
        step=1,
        value=None,
        key="chapter_hint",
    )
    if st.button(
        "Criar execução e localizar seção",
        disabled=source_path is None,
        key="start_location",
        type="primary",
    ):
        _start_location(pipeline, source_path, chapter_hint)

    _render_active_location(pipeline)


def _start_location(
    pipeline: DocumentLocationPipeline,
    source_path: Path | None,
    chapter_hint: int | None,
) -> None:
    if source_path is None:
        return
    _clear_active_run_view()
    try:
        run = pipeline.create_run(source_path)
        location = pipeline.locate_section(run.run_id, chapter_hint=chapter_hint)
    except (OSError, RuntimeError, ValueError) as error:
        st.error(str(error))
        return
    st.session_state["location_run_id"] = run.run_id
    st.session_state["location_page_count"] = run.page_count
    st.session_state["location_confirmed"] = False
    st.session_state["location_previews"] = []
    if location is None:
        st.session_state["location_result"] = None
        st.session_state["location_page_start"] = 1
        st.session_state["location_page_end"] = run.page_count
        return
    st.session_state["location_result"] = location.model_dump(mode="json")
    st.session_state["location_page_start"] = location.page_start
    st.session_state["location_page_end"] = location.page_end
    try:
        previews = pipeline.preview_pages(
            run.run_id,
            page_start=location.page_start,
            page_end=location.page_end,
        )
    except (OSError, RuntimeError, ValueError) as error:
        st.error(f"Não foi possível gerar a prévia: {error}")
    else:
        st.session_state["location_previews"] = [str(preview.path) for preview in previews]


def _render_active_location(pipeline: DocumentLocationPipeline) -> None:
    run_id = st.session_state.get("location_run_id")
    if run_id is None:
        return
    location_payload = st.session_state.get("location_result")
    if location_payload is None:
        st.warning("A seção não foi localizada. Informe o intervalo manualmente.")
    else:
        location = SectionLocation.model_validate(location_payload)
        st.subheader(location.title)
        st.markdown(f"Páginas {location.page_start} a {location.page_end}")
        st.info(location.rationale)

    page_count = int(st.session_state["location_page_count"])
    page_start = st.number_input(
        "Página inicial",
        min_value=1,
        max_value=page_count,
        value=int(st.session_state["location_page_start"]),
        key="confirmed_page_start",
    )
    page_end = st.number_input(
        "Página final",
        min_value=1,
        max_value=page_count,
        value=int(st.session_state["location_page_end"]),
        key="confirmed_page_end",
    )
    if st.button("Atualizar prévia", key="refresh_preview"):
        try:
            previews = pipeline.preview_pages(
                str(run_id),
                page_start=int(page_start),
                page_end=int(page_end),
            )
        except (OSError, RuntimeError, ValueError) as error:
            st.error(str(error))
        else:
            st.session_state["location_previews"] = [str(preview.path) for preview in previews]
    for preview_path in st.session_state.get("location_previews", []):
        st.image(preview_path)

    if st.button("Confirmar intervalo", key="confirm_location"):
        try:
            pipeline.confirm_location(
                str(run_id),
                page_start=int(page_start),
                page_end=int(page_end),
            )
        except (OSError, RuntimeError, ValueError) as error:
            st.error(str(error))
        else:
            st.session_state["location_confirmed"] = True
            st.success(f"Intervalo confirmado: páginas {int(page_start)} a {int(page_end)}.")
    if st.button(
        "Extrair informações",
        disabled=not bool(st.session_state.get("location_confirmed", False)),
        key="start_extraction",
    ):
        _extract_and_validate(pipeline, str(run_id))


def _extract_and_validate(pipeline: DocumentLocationPipeline, run_id: str) -> None:
    try:
        pipeline.extract(run_id)
        pipeline.validate(run_id)
    except (OSError, RuntimeError, ValueError) as error:
        st.error(f"Não foi possível concluir a extração e validação: {error}")
        st.info("O progresso foi preservado. Clique em Extrair informações para tentar novamente.")
        return
    st.session_state["_asset_servicing_review_run_id"] = run_id
    st.success("Extração e validação concluídas.")


def _clear_active_run_view() -> None:
    """Clear only browser state tied to the previously active document."""

    for key in _ACTIVE_RUN_VIEW_KEYS:
        st.session_state.pop(key, None)


def render_review_results(*, review_service: ReviewWorkflow, run_id: str) -> None:
    """Render the persisted extraction results and review counters."""

    try:
        run = review_service.get_run(run_id)
    except (OSError, RuntimeError, ValueError) as error:
        st.error(str(error))
        return

    validation_by_variable = {validation.variable_id: validation for validation in run.validations}
    rows = []
    for variable in run.variables:
        validation = validation_by_variable.get(variable.id)
        rows.append(
            {
                "Variável": variable.current_name,
                "Valor": variable.current_value,
                "Trecho-fonte": variable.evidence_text,
                "Páginas": ", ".join(str(page) for page in variable.source_pages),
                "Confiança": validation.confidence if validation else None,
                "Veredito": validation.verdict.value if validation else "—",
                "Foi revisado?": variable.reviewed,
            }
        )

    pending = run.pending_items()
    st.header("Resultados e revisão")
    flash_message = st.session_state.pop("_review_flash", None)
    if flash_message:
        st.success(str(flash_message))
    metric_columns = st.columns(3)
    metric_columns[0].metric("Variáveis", len(run.variables))
    metric_columns[1].metric("Pendências", len(pending))
    metric_columns[2].metric(
        "Revisadas",
        sum(variable.reviewed for variable in run.variables),
    )
    st.dataframe(rows, width="stretch", hide_index=True)
    if not pending:
        st.success("Não há pendências de revisão.")
        return

    variables_by_id = {variable.id: variable for variable in run.variables}
    findings_by_id = {finding.id: finding for finding in run.coverage_findings}
    st.subheader("Fila de revisão")
    for item in pending:
        if item.kind is ReviewItemKind.VARIABLE and item.variable_id is not None:
            variable = variables_by_id[item.variable_id]
            validation = validation_by_variable[item.variable_id]
            st.subheader(variable.current_name)
            st.text_input(
                "Nome atual",
                value=variable.current_name,
                disabled=True,
                key=f"pending_name_{variable.id}",
            )
            st.text_input(
                "Valor atual",
                value=variable.current_value,
                disabled=True,
                key=f"pending_value_{variable.id}",
            )
            st.text_area(
                "Trecho-fonte (somente leitura)",
                value=variable.evidence_text,
                disabled=True,
                key=f"evidence_{variable.id}",
            )
            st.caption(f"Página(s): {', '.join(str(page) for page in variable.source_pages)}")
            formatted_confidence = f"{validation.confidence:.2f}".replace(".", ",")
            st.markdown(f"**Confiança atribuída pela LLM (rubrica):** {formatted_confidence}")
            st.markdown(f"**Veredito:** {_VERDICT_LABELS[validation.verdict.value]}")
            st.info(f"Justificativa do validador: {validation.rationale}")
            confirm_note = st.text_input(
                "Nota da confirmação (opcional)",
                key=f"confirm_note_{variable.id}",
            )
            if st.button("Confirmar variável", key=f"confirm_{variable.id}"):
                try:
                    review_service.confirm(
                        run_id,
                        variable.id,
                        note=confirm_note or None,
                    )
                except (OSError, RuntimeError, ValueError) as error:
                    st.error(str(error))
                else:
                    st.session_state["_review_flash"] = "Variável confirmada."
                    st.rerun()
            st.markdown("##### Editar variável")
            edit_name = st.text_input(
                "Nome revisado",
                value=variable.current_name,
                key=f"edit_name_{variable.id}",
            )
            edit_value = st.text_input(
                "Valor revisado",
                value=variable.current_value,
                key=f"edit_value_{variable.id}",
            )
            edit_note = st.text_input(
                "Nota da edição (opcional)",
                key=f"edit_note_{variable.id}",
            )
            if st.button("Salvar edição", key=f"edit_{variable.id}"):
                try:
                    review_service.edit(
                        run_id,
                        variable.id,
                        name=edit_name,
                        value=edit_value,
                        note=edit_note or None,
                    )
                except (OSError, RuntimeError, ValueError) as error:
                    st.error(str(error))
                else:
                    st.session_state["_review_flash"] = "Variável editada."
                    st.rerun()
            st.markdown("##### Marcar como não aplicável")
            not_applicable_note = st.text_input(
                "Justificativa obrigatória",
                key=f"not_applicable_note_{variable.id}",
            )
            if st.button(
                "Marcar como não aplicável",
                key=f"not_applicable_{variable.id}",
            ):
                try:
                    review_service.mark_not_applicable(
                        run_id,
                        variable.id,
                        note=not_applicable_note,
                    )
                except (OSError, RuntimeError, ValueError) as error:
                    st.error(str(error))
                else:
                    st.session_state["_review_flash"] = "Variável marcada como não aplicável."
                    st.rerun()
        elif item.finding_id is not None:
            finding = findings_by_id[item.finding_id]
            st.subheader("Possível omissão")
            st.text_area(
                "Descrição do apontamento",
                value=finding.description,
                disabled=True,
                key=f"finding_description_{finding.id}",
            )
            st.text_area(
                "Trecho indicado pelo validador",
                value=finding.evidence_text,
                disabled=True,
                key=f"finding_evidence_{finding.id}",
            )
            st.caption(f"Página(s): {', '.join(str(page) for page in finding.source_pages)}")
            missing_name = st.text_input(
                "Nome da variável ausente",
                value=finding.suggested_name or "",
                key=f"missing_name_{finding.id}",
            )
            missing_value = st.text_input(
                "Valor revisado da variável ausente",
                key=f"missing_value_{finding.id}",
            )
            missing_evidence = st.text_area(
                "Evidência revisada manualmente",
                value=finding.evidence_text,
                key=f"missing_evidence_{finding.id}",
            )
            missing_note = st.text_input(
                "Nota da inclusão (opcional)",
                key=f"missing_note_{finding.id}",
            )
            if st.button(
                "Adicionar variável ausente",
                key=f"add_missing_{finding.id}",
            ):
                try:
                    review_service.add_missing(
                        run_id,
                        finding.id,
                        name=missing_name,
                        value=missing_value,
                        evidence=missing_evidence,
                        note=missing_note or None,
                    )
                except (OSError, RuntimeError, ValueError) as error:
                    st.error(str(error))
                else:
                    st.session_state["_review_flash"] = "Variável ausente adicionada."
                    st.rerun()
            st.markdown("##### Descartar apontamento")
            dismiss_note = st.text_input(
                "Justificativa obrigatória para o descarte",
                key=f"dismiss_note_{finding.id}",
            )
            if st.button(
                "Descartar possível omissão",
                key=f"dismiss_{finding.id}",
            ):
                try:
                    review_service.dismiss_omission(
                        run_id,
                        finding.id,
                        note=dismiss_note,
                    )
                except (OSError, RuntimeError, ValueError) as error:
                    st.error(str(error))
                else:
                    st.session_state["_review_flash"] = "Possível omissão descartada."
                    st.rerun()


def render_run_delivery(*, delivery_service: DeliveryWorkflow, run_id: str) -> None:
    """Render workbook generation and downloads for one persisted run."""

    try:
        run = delivery_service.get_run(run_id)
    except (OSError, RuntimeError, ValueError) as error:
        st.error(str(error))
        return

    _render_run_summary(delivery_service, run_id)
    st.header("Arquivos da execução")
    preliminary: ExportArtifact | None = None
    if st.button("Gerar Excel preliminar", key="generate_preliminary"):
        try:
            preliminary = delivery_service.export_preliminary(run_id)
        except (OSError, RuntimeError, ValueError) as error:
            st.error(str(error))
        else:
            st.success("Excel preliminar gerado.")
    if preliminary is None:
        try:
            preliminary = delivery_service.get_export(run_id, final=False)
        except (OSError, RuntimeError, ValueError) as error:
            st.error(str(error))
    if preliminary is not None:
        st.download_button(
            "Baixar Excel preliminar",
            data=preliminary.data,
            file_name=preliminary.path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_preliminary",
        )

    pending_count = len(run.pending_items())
    if pending_count:
        suffix = "pendência" if pending_count == 1 else "pendências"
        st.warning(f"Excel final bloqueado: {pending_count} {suffix} de revisão aberta.")
    final: ExportArtifact | None = None
    if st.button(
        "Gerar Excel final",
        disabled=pending_count > 0,
        key="generate_final",
    ):
        try:
            final = delivery_service.export_final(run_id)
        except (OSError, RuntimeError, ValueError) as error:
            st.error(str(error))
        else:
            st.success("Excel final gerado.")
    if final is None:
        try:
            final = delivery_service.get_export(run_id, final=True)
        except (OSError, RuntimeError, ValueError) as error:
            st.error(str(error))
    if final is not None:
        st.download_button(
            "Baixar Excel final",
            data=final.data,
            file_name=final.path.name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_final",
        )


def _render_run_summary(delivery_service: DeliveryWorkflow, run_id: str) -> None:
    try:
        summary = delivery_service.summary(run_id)
    except (OSError, RuntimeError, ValueError) as error:
        st.error(str(error))
        return

    st.header("Resumo operacional")
    count_columns = st.columns(4)
    count_columns[0].metric("Duração total", _format_duration(summary.total_duration_ms))
    count_columns[1].metric("Variáveis extraídas", summary.variable_count)
    count_columns[2].metric("Aprovadas", summary.approved_count)
    count_columns[3].metric("Revisadas", summary.reviewed_count)
    st.table(
        [
            {"Etapa": stage, "Duração": _format_duration(duration_ms)}
            for stage, duration_ms in summary.stage_durations_ms.items()
        ]
    )
    distribution = summary.confidence_distribution
    st.markdown(
        "**Distribuição de confiança:** "
        f"Alta (≥ 0,85): {distribution['high']} · "
        f"Média (0,50–0,84): {distribution['medium']} · "
        f"Baixa (< 0,50): {distribution['low']}"
    )
    operation_columns = st.columns(2)
    operation_columns[0].metric("Chamadas", summary.call_count)
    operation_columns[1].metric("Retries", summary.retry_count)
    usage_text = " · ".join(f"{key}: {value}" for key, value in sorted(summary.usage.items()))
    st.markdown(f"**Uso reportado:** {usage_text or 'não informado'}")
    st.caption(f"Modelos: {', '.join(summary.models) or 'não informado'}")
    st.caption(f"Versões de prompt: {', '.join(summary.prompt_versions) or 'não informado'}")


def _format_duration(duration_ms: int) -> str:
    return f"{duration_ms / 1000:.2f} s".replace(".", ",")


def main(services: LocalAppServices | None = None) -> None:
    """Render the configured local application entry point."""

    if services is not None:
        st.session_state["_asset_servicing_pipeline"] = services.pipeline
        st.session_state["_asset_servicing_regulations_dir"] = services.regulations_dir
        st.session_state["_asset_servicing_upload_dir"] = services.upload_dir
        st.session_state["_asset_servicing_review_service"] = services.review_service
        st.session_state["_asset_servicing_delivery_service"] = services.delivery_service
    pipeline = st.session_state.get("_asset_servicing_pipeline")
    regulations_dir = st.session_state.get("_asset_servicing_regulations_dir")
    upload_dir = st.session_state.get("_asset_servicing_upload_dir")
    review_service = st.session_state.get("_asset_servicing_review_service")
    review_run_id = st.session_state.get("_asset_servicing_review_run_id")
    delivery_service = st.session_state.get("_asset_servicing_delivery_service")
    if (
        (pipeline is None or regulations_dir is None or upload_dir is None)
        and (review_service is None or review_run_id is None)
        and delivery_service is None
    ):
        st.error("A aplicação ainda não foi configurada com os serviços locais.")
        return
    if pipeline is not None and regulations_dir is not None and upload_dir is not None:
        render_document_location(
            pipeline=pipeline,
            regulations_dir=Path(regulations_dir),
            upload_dir=Path(upload_dir),
        )
    review_run_id = st.session_state.get("_asset_servicing_review_run_id")
    active_run_id = None if review_run_id is None else str(review_run_id)
    if review_service is not None and active_run_id is not None:
        render_review_results(
            review_service=review_service,
            run_id=active_run_id,
        )
    if delivery_service is not None and active_run_id is not None:
        render_run_delivery(
            delivery_service=delivery_service,
            run_id=active_run_id,
        )


if __name__ == "__main__":
    main()


__all__ = [
    "DocumentLocationPipeline",
    "DeliveryWorkflow",
    "LocalAppServices",
    "Preview",
    "ReviewWorkflow",
    "main",
    "render_document_location",
    "render_review_results",
    "render_run_delivery",
]
