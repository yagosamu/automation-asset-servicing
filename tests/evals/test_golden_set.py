"""Integrity contract for the versioned regulation golden set."""

from __future__ import annotations

import hashlib
import unicodedata
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml
from pypdf import PdfReader

pytestmark = pytest.mark.eval
ROOT = Path(__file__).resolve().parents[2]
GOLDEN_ROOT = ROOT / "evals" / "golden" / "v1"
MANIFEST_PATH = GOLDEN_ROOT / "manifest.yaml"
REGULATIONS = ROOT / "Regulamentos"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    assert isinstance(document, dict)
    return document


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return load_yaml(MANIFEST_PATH)


@pytest.fixture(scope="module")
def expected_documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [load_yaml(GOLDEN_ROOT / item["expected"]) for item in manifest["documents"]]


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


@cache
def extracted_pages(filename: str) -> tuple[str, ...]:
    reader = PdfReader(REGULATIONS / filename)
    return tuple(normalized(page.extract_text() or "") for page in reader.pages)


def test_manifest_declares_version_and_annotation_provenance(
    manifest: dict[str, Any],
) -> None:
    assert manifest["schema_version"] == 1
    assert manifest["corpus_id"] == "btg-regulations-v1"
    assert manifest["annotator"] == "candidate-assisted-by-codex"
    assert manifest["annotation_date"] == "2026-09-28"


def test_manifest_covers_exactly_the_four_versioned_regulations(
    manifest: dict[str, Any],
) -> None:
    source_filenames = {path.name for path in REGULATIONS.glob("*.pdf")}
    manifest_filenames = {item["filename"] for item in manifest["documents"]}

    assert len(manifest["documents"]) == 4
    assert manifest_filenames == source_filenames


def test_manifest_document_ids_and_expected_paths_are_unique(
    manifest: dict[str, Any],
) -> None:
    document_ids = [item["id"] for item in manifest["documents"]]
    expected_paths = [item["expected"] for item in manifest["documents"]]

    assert len(document_ids) == len(set(document_ids))
    assert len(expected_paths) == len(set(expected_paths))
    assert all((GOLDEN_ROOT / path).is_file() for path in expected_paths)


@pytest.mark.parametrize(
    "filename, expected_sha256",
    [
        (
            "DOC_REGUL_23183_193223_2026_05.pdf",
            "e308f8ec3f3924c7fd6aa11a4058323aeaa06a7183765eb0e08f7f2a93fb5e4e",
        ),
        (
            "DOC_REGUL_23968_193595_2026_05.pdf",
            "f2538e654b5478dc2079d22aa21d2b05a9c67d95d8a06cf64e8a69df0174ae11",
        ),
        (
            "DOC_REGUL_24029_193593_2026_05.pdf",
            "297cc9931d116bbe01a8d11a48563234c746ae01f99103c5553a869b2f4b8ead",
        ),
        (
            "DOC_REGUL_30148_163257_2025_10.pdf",
            "11a282ca4d7520687425783e5b1a19b8ab9c34d2ee0cb9451f06c5a6668228b5",
        ),
    ],
)
def test_manifest_hash_matches_source_file(
    manifest: dict[str, Any], filename: str, expected_sha256: str
) -> None:
    entry = next(item for item in manifest["documents"] if item["filename"] == filename)
    digest = hashlib.sha256((REGULATIONS / filename).read_bytes()).hexdigest()

    assert entry["sha256"] == expected_sha256
    assert digest == expected_sha256


def test_expected_files_are_bound_to_their_manifest_entries(
    manifest: dict[str, Any], expected_documents: list[dict[str, Any]]
) -> None:
    by_id = {item["id"]: item for item in manifest["documents"]}

    for expected in expected_documents:
        manifest_entry = by_id[expected["document_id"]]
        assert expected["schema_version"] == manifest["schema_version"]
        assert expected["source_filename"] == manifest_entry["filename"]


def test_chapter_annotations_use_valid_source_pages(
    expected_documents: list[dict[str, Any]],
) -> None:
    for expected in expected_documents:
        chapter = expected["chapter"]
        page_count = len(extracted_pages(expected["source_filename"]))

        assert chapter["number"] == 3
        assert "EMISS" in chapter["title"].upper()
        assert chapter["pages"] == sorted(set(chapter["pages"]))
        assert all(1 <= page <= page_count for page in chapter["pages"])


def test_variable_ids_are_globally_unique(
    expected_documents: list[dict[str, Any]],
) -> None:
    variable_ids = [
        variable["id"] for expected in expected_documents for variable in expected["variables"]
    ]

    assert variable_ids
    assert len(variable_ids) == len(set(variable_ids))


def test_every_variable_has_names_values_pages_and_evidence(
    expected_documents: list[dict[str, Any]],
) -> None:
    for expected in expected_documents:
        chapter_pages = set(expected["chapter"]["pages"])
        assert expected["variables"]
        for variable in expected["variables"]:
            assert variable["kind"] in {"table", "prose"}
            assert isinstance(variable["critical"], bool)
            assert all(isinstance(value, str) and value for value in variable["accepted_names"])
            assert all(isinstance(value, str) and value for value in variable["accepted_values"])
            assert set(variable["pages"]) <= chapter_pages
            assert isinstance(variable["evidence"], str) and variable["evidence"]


def test_every_document_has_critical_fields_with_accepted_names_and_values(
    expected_documents: list[dict[str, Any]],
) -> None:
    for expected in expected_documents:
        critical = [variable for variable in expected["variables"] if variable["critical"]]

        assert critical
        assert all(variable["accepted_names"] for variable in critical)
        assert all(variable["accepted_values"] for variable in critical)


def test_every_evidence_snippet_resolves_on_its_declared_pages(
    expected_documents: list[dict[str, Any]],
) -> None:
    for expected in expected_documents:
        pages = extracted_pages(expected["source_filename"])
        for variable in expected["variables"]:
            declared_text = " ".join(pages[page - 1] for page in variable["pages"])
            assert normalized(variable["evidence"]) in declared_text, variable["id"]


def test_golden_set_contains_table_and_prose_variables(
    expected_documents: list[dict[str, Any]],
) -> None:
    kinds = {
        variable["kind"] for expected in expected_documents for variable in expected["variables"]
    }

    assert kinds == {"table", "prose"}
