"""Executable contract for the project bootstrap."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from asset_servicing import __version__

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.contract


def load_project() -> dict[str, object]:
    with (ROOT / "pyproject.toml").open("rb") as project_file:
        return tomllib.load(project_file)


def test_project_declares_src_layout_and_supported_python() -> None:
    project = load_project()["project"]

    assert project["requires-python"] == ">=3.13,<3.14"
    assert project["name"] == "asset-servicing"
    assert (ROOT / "src" / "asset_servicing" / "__init__.py").is_file()
    assert __version__ == project["version"]


def test_quality_tools_are_declared_in_dev_group() -> None:
    dev_dependencies = load_project()["dependency-groups"]["dev"]
    dependency_names = {
        dependency.split(">", 1)[0].split("=", 1)[0] for dependency in dev_dependencies
    }

    assert {"pytest", "pytest-cov", "ruff", "mypy"} <= dependency_names


def test_all_project_markers_are_registered() -> None:
    markers = load_project()["tool"]["pytest"]["ini_options"]["markers"]
    marker_names = {marker.split(":", 1)[0] for marker in markers}

    assert {"unit", "integration", "contract", "ui", "eval", "needs_api"} <= marker_names


def test_canonical_gates_are_documented() -> None:
    tasks = (ROOT / ".specs" / "features" / "regulation-extraction" / "tasks.md").read_text(
        encoding="utf-8"
    )

    assert 'uv run pytest -m "unit or contract" -q' in tasks
    assert 'uv run pytest -m "not needs_api" -q' in tasks
    assert "uv run ruff format --check ." in tasks
