"""Integration contract for structural PDF processing."""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest
from pypdf import PdfReader, PdfWriter

from asset_servicing.adapters.pdf.processor import PdfProcessor, PdfValidationError

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
REGULATIONS = ROOT / "Regulamentos"

EXPECTED_DOCUMENTS = {
    "DOC_REGUL_23183_193223_2026_05.pdf": (
        14,
        "e308f8ec3f3924c7fd6aa11a4058323aeaa06a7183765eb0e08f7f2a93fb5e4e",
    ),
    "DOC_REGUL_23968_193595_2026_05.pdf": (
        14,
        "f2538e654b5478dc2079d22aa21d2b05a9c67d95d8a06cf64e8a69df0174ae11",
    ),
    "DOC_REGUL_24029_193593_2026_05.pdf": (
        16,
        "297cc9931d116bbe01a8d11a48563234c746ae01f99103c5553a869b2f4b8ead",
    ),
    "DOC_REGUL_30148_163257_2025_10.pdf": (
        17,
        "11a282ca4d7520687425783e5b1a19b8ab9c34d2ee0cb9451f06c5a6668228b5",
    ),
}


def write_blank_pdf(path: Path, *, pages: int, password: str | None = None) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    if password is not None:
        writer.encrypt(password)
    with path.open("wb") as output:
        writer.write(output)


def write_labeled_pdf(path: Path) -> None:
    document = pymupdf.open()
    for page_number in range(1, 4):
        page = document.new_page(width=600 + page_number, height=800)
        page.insert_text((72, 72), f"SOURCE PAGE {page_number}")
    document.save(path)
    document.close()


@pytest.mark.parametrize(("filename", "expected"), EXPECTED_DOCUMENTS.items())
def test_inspect_returns_reproducible_metadata_for_real_regulations(
    filename: str, expected: tuple[int, str]
) -> None:
    expected_pages, expected_hash = expected

    metadata = PdfProcessor().inspect(REGULATIONS / filename)

    assert metadata.filename == filename
    assert metadata.page_count == expected_pages
    assert metadata.sha256 == expected_hash
    assert metadata.size_bytes == (REGULATIONS / filename).stat().st_size


def test_default_limits_are_50_mib_and_200_pages() -> None:
    processor = PdfProcessor()

    assert processor.max_size_bytes == 50 * 1024 * 1024
    assert processor.max_pages == 200


def test_non_pdf_extension_is_rejected_before_opening(tmp_path: Path) -> None:
    document = tmp_path / "regulamento.txt"
    document.write_bytes(b"%PDF-1.7")

    with pytest.raises(PdfValidationError) as captured:
        PdfProcessor().inspect(document)

    assert captured.value.code == "not_pdf"


def test_unreadable_pdf_is_rejected_with_specific_condition(tmp_path: Path) -> None:
    document = tmp_path / "broken.pdf"
    document.write_bytes(b"%PDF-1.7\nthis is not a valid document")

    with pytest.raises(PdfValidationError) as captured:
        PdfProcessor().inspect(document)

    assert captured.value.code == "unreadable"


def test_encrypted_pdf_is_rejected_without_attempting_password(tmp_path: Path) -> None:
    document = tmp_path / "encrypted.pdf"
    write_blank_pdf(document, pages=1, password="password")

    with pytest.raises(PdfValidationError) as captured:
        PdfProcessor().inspect(document)

    assert captured.value.code == "encrypted"


def test_size_limit_is_inclusive_and_rejects_the_next_byte(tmp_path: Path) -> None:
    accepted = tmp_path / "accepted.pdf"
    write_blank_pdf(accepted, pages=1)
    exact_limit = accepted.stat().st_size
    oversized = tmp_path / "oversized.pdf"
    oversized.write_bytes(accepted.read_bytes() + b"x")
    processor = PdfProcessor(max_size_bytes=exact_limit)

    assert processor.inspect(accepted).size_bytes == exact_limit
    with pytest.raises(PdfValidationError) as captured:
        processor.inspect(oversized)
    assert captured.value.code == "too_large"


def test_pdf_with_exactly_200_pages_is_accepted(tmp_path: Path) -> None:
    document = tmp_path / "two-hundred-pages.pdf"
    write_blank_pdf(document, pages=200)

    assert PdfProcessor().inspect(document).page_count == 200


def test_pdf_with_201_pages_is_rejected(tmp_path: Path) -> None:
    document = tmp_path / "two-hundred-one-pages.pdf"
    write_blank_pdf(document, pages=201)

    with pytest.raises(PdfValidationError) as captured:
        PdfProcessor().inspect(document)

    assert captured.value.code == "too_many_pages"


def test_select_pages_preserves_source_order_and_original_content(tmp_path: Path) -> None:
    source = tmp_path / "labeled.pdf"
    write_labeled_pdf(source)

    selected_bytes = PdfProcessor().select_pages(source, start=2, end=3)
    selected_path = tmp_path / "selected.pdf"
    selected_path.write_bytes(selected_bytes)
    reader = PdfReader(selected_path)

    assert len(reader.pages) == 2
    assert [page.extract_text().strip() for page in reader.pages] == [
        "SOURCE PAGE 2",
        "SOURCE PAGE 3",
    ]
    assert [float(page.mediabox.width) for page in reader.pages] == [602.0, 603.0]


@pytest.mark.parametrize(
    ("start", "end"),
    [(0, 1), (2, 1), (1, 4)],
)
def test_select_pages_rejects_ranges_outside_the_document(
    tmp_path: Path, start: int, end: int
) -> None:
    source = tmp_path / "three-pages.pdf"
    write_blank_pdf(source, pages=3)

    with pytest.raises(PdfValidationError) as captured:
        PdfProcessor().select_pages(source, start=start, end=end)

    assert captured.value.code == "invalid_page_range"


def test_render_pages_writes_ordered_png_previews_to_requested_directory(
    tmp_path: Path,
) -> None:
    source = REGULATIONS / "DOC_REGUL_23183_193223_2026_05.pdf"
    output_dir = tmp_path / "previews"

    previews = PdfProcessor().render_pages(source, pages=[2, 4], output_dir=output_dir)

    assert [preview.page_number for preview in previews] == [2, 4]
    assert [preview.path.name for preview in previews] == ["page-0002.png", "page-0004.png"]
    assert all(preview.path.parent == output_dir for preview in previews)
    assert all(preview.path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for preview in previews)
    assert all(preview.width > 0 and preview.height > 0 for preview in previews)


def test_render_pages_rejects_invalid_page_number(tmp_path: Path) -> None:
    source = tmp_path / "one-page.pdf"
    write_blank_pdf(source, pages=1)

    with pytest.raises(PdfValidationError) as captured:
        PdfProcessor().render_pages(source, pages=[2], output_dir=tmp_path / "previews")

    assert captured.value.code == "invalid_page_range"
