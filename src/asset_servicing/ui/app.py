"""Streamlit flow for document intake and section confirmation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import streamlit as st

from asset_servicing.domain import Run, SectionLocation


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
    )
    source_path: Path | None = None
    if source_kind == "Pasta do projeto":
        filenames = sorted(path.name for path in Path(regulations_dir).glob("*.pdf"))
        selected = st.selectbox(
            "Regulamento",
            filenames,
            key="project_pdf",
            placeholder="Nenhum PDF encontrado",
        )
        if selected:
            source_path = Path(regulations_dir) / selected
    else:
        upload = st.file_uploader(
            "Selecione um regulamento PDF",
            type=["pdf"],
            key="uploaded_pdf",
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
    st.button(
        "Extrair informações",
        disabled=not bool(st.session_state.get("location_confirmed", False)),
        key="start_extraction",
    )


def main() -> None:
    """Render the configured local application entry point."""

    pipeline = st.session_state.get("_asset_servicing_pipeline")
    regulations_dir = st.session_state.get("_asset_servicing_regulations_dir")
    upload_dir = st.session_state.get("_asset_servicing_upload_dir")
    if pipeline is None or regulations_dir is None or upload_dir is None:
        st.error("A aplicação ainda não foi configurada com os serviços locais.")
        return
    render_document_location(
        pipeline=pipeline,
        regulations_dir=Path(regulations_dir),
        upload_dir=Path(upload_dir),
    )


if __name__ == "__main__":
    main()


__all__ = ["DocumentLocationPipeline", "Preview", "main", "render_document_location"]
