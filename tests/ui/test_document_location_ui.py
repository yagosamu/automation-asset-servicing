"""Streamlit journeys for document intake and section confirmation."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from asset_servicing.domain import Run, SectionLocation
from asset_servicing.ui import app as ui_app

pytestmark = pytest.mark.ui


@dataclass(frozen=True, slots=True)
class FakePreview:
    page_number: int
    path: Path


class FakePipeline:
    def __init__(self) -> None:
        self.created_paths: list[Path] = []
        self.chapter_hints: list[int | None] = []
        self.confirmed_ranges: list[tuple[int, int]] = []
        self.preview_ranges: list[tuple[int, int]] = []
        self.preview_path: Path | None = None
        self.create_error: Exception | None = None
        self.location: SectionLocation | None = SectionLocation(
            title="CAPÍTULO 3 – DA EMISSÃO, APLICAÇÃO E RESGATE DE COTAS",
            page_start=7,
            page_end=9,
            rationale="A seção reúne as regras de movimentação de cotas.",
        )

    def create_run(self, source_pdf: Path) -> Run:
        self.created_paths.append(source_pdf)
        if self.create_error is not None:
            raise self.create_error
        return Run(
            run_id="run-001",
            document_name=source_pdf.name,
            document_sha256="d" * 64,
            page_count=12,
            created_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )

    def locate_section(
        self,
        run_id: str,
        *,
        chapter_hint: int | None = None,
    ) -> SectionLocation | None:
        assert run_id == "run-001"
        self.chapter_hints.append(chapter_hint)
        return self.location

    def confirm_location(self, run_id: str, *, page_start: int, page_end: int) -> Run:
        assert run_id == "run-001"
        self.confirmed_ranges.append((page_start, page_end))
        run = Run(
            run_id="run-001",
            document_name="confirmed.pdf",
            document_sha256="e" * 64,
            page_count=12,
            created_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
        if self.location is not None:
            run.location = self.location.model_copy(
                update={"page_start": page_start, "page_end": page_end, "confirmed": True}
            )
        return run

    def preview_pages(self, run_id: str, *, page_start: int, page_end: int) -> list[FakePreview]:
        assert run_id == "run-001"
        self.preview_ranges.append((page_start, page_end))
        if self.preview_path is None:
            return []
        return [
            FakePreview(page_number=page, path=self.preview_path)
            for page in range(page_start, page_end + 1)
        ]


def make_app(
    tmp_path: Path,
    pipeline: FakePipeline,
    *,
    project_files: list[str] | None = None,
) -> AppTest:
    regulations = tmp_path / "Regulamentos"
    regulations.mkdir()
    for filename in ["regulamento.pdf"] if project_files is None else project_files:
        (regulations / filename).write_bytes(b"%PDF-1.7\nfixture")
    uploads = tmp_path / "uploads"
    preview = tmp_path / "preview.png"
    preview.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
    )
    pipeline.preview_path = preview
    app = AppTest.from_file(str(Path(ui_app.__file__)))
    app.session_state["_asset_servicing_pipeline"] = pipeline
    app.session_state["_asset_servicing_regulations_dir"] = regulations
    app.session_state["_asset_servicing_upload_dir"] = uploads
    return app.run()


def test_initial_view_offers_project_folder_and_upload(tmp_path: Path) -> None:
    app = make_app(tmp_path, FakePipeline())

    assert app.title[0].value == "Extração de Regulamentos"
    assert app.get_by_key("document_source").value == "Pasta do projeto"
    assert app.get_by_key("project_pdf").value == "regulamento.pdf"
    assert len(app.file_uploader) == 0


def test_project_pdf_starts_run_and_shows_location(tmp_path: Path) -> None:
    pipeline = FakePipeline()
    app = make_app(tmp_path, pipeline)

    app.get_by_key("start_location").click().run()

    assert pipeline.created_paths[0].name == "regulamento.pdf"
    assert app.subheader[0].value.startswith("CAPÍTULO 3")
    assert "Páginas 7 a 9" in app.markdown[0].value
    assert "regras de movimentação" in app.info[0].value


def test_upload_uses_the_same_pipeline_entrypoint(tmp_path: Path) -> None:
    pipeline = FakePipeline()
    app = make_app(tmp_path, pipeline)
    app.get_by_key("document_source").set_value("Upload").run()

    app.get_by_key("uploaded_pdf").upload(
        "enviado.pdf",
        b"%PDF-1.7\nupload",
        "application/pdf",
    ).run()
    app.get_by_key("start_location").click().run()

    assert len(pipeline.created_paths) == 1
    assert pipeline.created_paths[0].name == "enviado.pdf"
    assert pipeline.created_paths[0].read_bytes() == b"%PDF-1.7\nupload"
    assert app.subheader[0].value.startswith("CAPÍTULO 3")


def test_invalid_document_shows_recoverable_error(tmp_path: Path) -> None:
    pipeline = FakePipeline()
    pipeline.create_error = ValueError("Input must use the .pdf extension")
    app = make_app(tmp_path, pipeline)

    app.get_by_key("start_location").click().run()

    assert "Input must use the .pdf extension" in app.error[0].value
    assert len(app.subheader) == 0
    assert app.get_by_key("start_location").disabled is False


def test_optional_chapter_hint_is_forwarded_to_semantic_locator(tmp_path: Path) -> None:
    pipeline = FakePipeline()
    app = make_app(tmp_path, pipeline)
    app.get_by_key("chapter_hint").set_value(6).run()

    app.get_by_key("start_location").click().run()

    assert pipeline.chapter_hints == [6]


def test_preview_is_visible_for_the_located_interval(tmp_path: Path) -> None:
    pipeline = FakePipeline()
    app = make_app(tmp_path, pipeline)

    app.get_by_key("start_location").click().run()

    assert pipeline.preview_ranges == [(7, 9)]
    assert len(app.image) == 3


def test_extraction_stays_disabled_before_confirmation(tmp_path: Path) -> None:
    app = make_app(tmp_path, FakePipeline())

    app.get_by_key("start_location").click().run()

    assert app.get_by_key("start_extraction").disabled is True


def test_operator_can_correct_pages_and_refresh_preview(tmp_path: Path) -> None:
    pipeline = FakePipeline()
    app = make_app(tmp_path, pipeline)
    app.get_by_key("start_location").click().run()
    app.get_by_key("confirmed_page_start").set_value(6).run()
    app.get_by_key("confirmed_page_end").set_value(8).run()

    app.get_by_key("refresh_preview").click().run()

    assert pipeline.preview_ranges[-1] == (6, 8)
    assert len(app.image) == 3


def test_confirmation_persists_corrected_pages_and_enables_extraction(tmp_path: Path) -> None:
    pipeline = FakePipeline()
    app = make_app(tmp_path, pipeline)
    app.get_by_key("start_location").click().run()
    app.get_by_key("confirmed_page_start").set_value(6).run()
    app.get_by_key("confirmed_page_end").set_value(8).run()

    app.get_by_key("confirm_location").click().run()

    assert pipeline.confirmed_ranges == [(6, 8)]
    assert "páginas 6 a 8" in app.success[0].value
    assert app.get_by_key("start_extraction").disabled is False


def test_not_found_shows_manual_range_as_recoverable_path(tmp_path: Path) -> None:
    pipeline = FakePipeline()
    pipeline.location = None
    app = make_app(tmp_path, pipeline)

    app.get_by_key("start_location").click().run()

    assert "não foi localizada" in app.warning[0].value
    assert app.get_by_key("confirmed_page_start").value == 1
    assert app.get_by_key("confirmed_page_end").value == 12
    assert app.get_by_key("start_extraction").disabled is True


def test_manual_range_can_be_confirmed_after_not_found(tmp_path: Path) -> None:
    pipeline = FakePipeline()
    pipeline.location = None
    app = make_app(tmp_path, pipeline)
    app.get_by_key("start_location").click().run()
    app.get_by_key("confirmed_page_start").set_value(4).run()
    app.get_by_key("confirmed_page_end").set_value(5).run()

    app.get_by_key("confirm_location").click().run()

    assert pipeline.confirmed_ranges == [(4, 5)]
    assert app.get_by_key("start_extraction").disabled is False


def test_empty_project_folder_keeps_start_disabled(tmp_path: Path) -> None:
    app = make_app(tmp_path, FakePipeline(), project_files=[])

    assert app.get_by_key("project_pdf").value is None
    assert app.get_by_key("start_location").disabled is True
