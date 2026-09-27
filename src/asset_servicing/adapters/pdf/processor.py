"""Validate and manipulate PDF pages without interpreting their content."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, cast

import pymupdf

DEFAULT_MAX_SIZE_BYTES: Final = 50 * 1024 * 1024
DEFAULT_MAX_PAGES: Final = 200


class _Pixmap(Protocol):
    """Typed view of the PyMuPDF pixmap operations used by this adapter."""

    width: int
    height: int

    def save(self, filename: Path) -> None: ...


class _Page(Protocol):
    """Typed view of a renderable PyMuPDF page."""

    def get_pixmap(self, *, matrix: object, alpha: bool) -> _Pixmap: ...


class _Document(Protocol):
    """Typed boundary for the subset of PyMuPDF used by this adapter."""

    needs_pass: bool
    page_count: int

    def __getitem__(self, page_number: int) -> _Page: ...

    def close(self) -> None: ...

    def insert_pdf(
        self,
        document: _Document,
        *,
        from_page: int,
        to_page: int,
    ) -> None: ...

    def tobytes(self, *, garbage: int, deflate: bool) -> bytes: ...


_open_pdf = cast(Callable[[Path], _Document], pymupdf.open)
_new_pdf = cast(Callable[[], _Document], pymupdf.open)
_make_matrix = cast(Callable[[float, float], object], pymupdf.Matrix)


class PdfValidationError(ValueError):
    """Input error with a stable code suitable for the user interface."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    """Locally derived metadata required to create a processing run."""

    filename: str
    sha256: str
    size_bytes: int
    page_count: int


@dataclass(frozen=True, slots=True)
class PagePreview:
    """Rendered preview tied to its original one-based page number."""

    page_number: int
    path: Path
    width: int
    height: int


class PdfProcessor:
    """Validate, inspect, render, and select pages from one PDF."""

    def __init__(
        self,
        *,
        max_size_bytes: int = DEFAULT_MAX_SIZE_BYTES,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> None:
        if max_size_bytes <= 0 or max_pages <= 0:
            raise ValueError("PDF limits must be positive")
        self.max_size_bytes = max_size_bytes
        self.max_pages = max_pages

    def inspect(self, path: Path) -> DocumentMetadata:
        """Validate a PDF and return reproducible local metadata."""

        document_path = self._validate_file(path)
        document = self._open(document_path)
        try:
            page_count = self._validate_document(document)
        finally:
            document.close()
        return DocumentMetadata(
            filename=document_path.name,
            sha256=self._sha256(document_path),
            size_bytes=document_path.stat().st_size,
            page_count=page_count,
        )

    def render_pages(
        self,
        path: Path,
        *,
        pages: list[int],
        output_dir: Path,
        dpi: int = 144,
    ) -> list[PagePreview]:
        """Render requested one-based source pages as ordered PNG previews."""

        if dpi <= 0:
            raise ValueError("dpi must be positive")
        document_path = self._validate_file(path)
        document = self._open(document_path)
        try:
            page_count = self._validate_document(document)
            self._validate_pages(pages, page_count)
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            matrix = _make_matrix(dpi / 72, dpi / 72)
            previews: list[PagePreview] = []
            for page_number in pages:
                pixmap = document[page_number - 1].get_pixmap(matrix=matrix, alpha=False)
                preview_path = output_dir / f"page-{page_number:04d}.png"
                pixmap.save(preview_path)
                previews.append(
                    PagePreview(
                        page_number=page_number,
                        path=preview_path,
                        width=pixmap.width,
                        height=pixmap.height,
                    )
                )
            return previews
        finally:
            document.close()

    def select_pages(self, path: Path, *, start: int, end: int) -> bytes:
        """Return a PDF containing the inclusive one-based source interval."""

        document_path = self._validate_file(path)
        source = self._open(document_path)
        selected = _new_pdf()
        try:
            page_count = self._validate_document(source)
            self._validate_range(start, end, page_count)
            selected.insert_pdf(source, from_page=start - 1, to_page=end - 1)
            return selected.tobytes(garbage=4, deflate=True)
        finally:
            selected.close()
            source.close()

    def _validate_file(self, path: Path) -> Path:
        document_path = Path(path)
        if not document_path.is_file():
            raise PdfValidationError("not_found", f"PDF file not found: {document_path.name}")
        if document_path.suffix.casefold() != ".pdf":
            raise PdfValidationError("not_pdf", "Input must use the .pdf extension")
        size_bytes = document_path.stat().st_size
        if size_bytes > self.max_size_bytes:
            raise PdfValidationError(
                "too_large",
                f"PDF exceeds the {self.max_size_bytes}-byte size limit",
            )
        with document_path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise PdfValidationError("not_pdf", "Input does not have a PDF signature")
        return document_path

    @staticmethod
    def _open(path: Path) -> _Document:
        try:
            return _open_pdf(path)
        except (pymupdf.FileDataError, RuntimeError, ValueError) as error:
            raise PdfValidationError("unreadable", "PDF cannot be opened") from error

    def _validate_document(self, document: _Document) -> int:
        if document.needs_pass:
            raise PdfValidationError("encrypted", "Encrypted PDF requires a password")
        page_count = document.page_count
        if page_count <= 0:
            raise PdfValidationError("unreadable", "PDF has no readable pages")
        if page_count > self.max_pages:
            raise PdfValidationError(
                "too_many_pages",
                f"PDF exceeds the {self.max_pages}-page limit",
            )
        return page_count

    @staticmethod
    def _validate_range(start: int, end: int, page_count: int) -> None:
        if start < 1 or end < start or end > page_count:
            raise PdfValidationError(
                "invalid_page_range",
                f"Page range must be between 1 and {page_count}",
            )

    @classmethod
    def _validate_pages(cls, pages: list[int], page_count: int) -> None:
        if not pages:
            raise PdfValidationError("invalid_page_range", "At least one page is required")
        for page_number in pages:
            cls._validate_range(page_number, page_number, page_count)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
