"""Executable documentation contract for setup and presentation."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"
pytestmark = pytest.mark.contract


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_has_the_required_operational_sections() -> None:
    headings = {line for line in _readme().splitlines() if line.startswith("## ")}

    assert {
        "## Arquitetura",
        "## Instalação",
        "## Configuração",
        "## Execução",
        "## Qualidade e testes",
        "## Roteiro de apresentação",
        "## Recuperação de falhas",
        "## Premissas e limitações",
    } <= headings


def test_clean_clone_setup_uses_uv_and_keeps_the_secret_out_of_git() -> None:
    readme = _readme()

    assert "git clone https://github.com/yagosamu/automation-asset-servicing.git" in readme
    assert "uv sync --group dev" in readme
    assert '$env:OPENAI_API_KEY = "<sua-chave>"' in readme
    assert "Nunca versione a chave" in readme


def test_readme_lists_the_canonical_runtime_and_quality_commands() -> None:
    readme = _readme()

    assert "uv run streamlit run src/asset_servicing/ui/runtime.py" in readme
    assert 'uv run pytest -m "not needs_api" -q' in readme
    assert (
        "uv run python -m asset_servicing.evals.runner --root . --report output/evals/latest.json"
    ) in readme
    assert "uv run pytest -m needs_api -q" in readme
    assert "uv run ruff format --check ." in readme
    assert "uv run ruff check ." in readme
    assert "uv run mypy src" in readme


def test_presentation_runbook_covers_primary_surprise_and_manual_paths() -> None:
    readme = _readme()

    assert "Criar execução e localizar seção" in readme
    assert "Confirmar intervalo" in readme
    assert "Extrair informações" in readme
    assert "Excel preliminar" in readme
    assert "Excel final" in readme
    assert "Capítulo 6" in readme
    assert "intervalo manual" in readme
    assert "baixa confiança" in readme


def test_recovery_instructions_match_the_persisted_ui_workflow() -> None:
    readme = _readme()

    assert "Retomar execução" in readme
    assert "O progresso foi preservado" in readme
    assert "Clique novamente em **Extrair informações**" in readme


def test_limitations_are_explicit_and_do_not_overstate_the_solution() -> None:
    readme = _readme()

    assert "quatro regulamentos" in readme
    assert "não é uma probabilidade calibrada" in readme
    assert "API externa" in readme
    assert "não implementa OCR dedicado" in readme
    assert "não implementa RAG" in readme
