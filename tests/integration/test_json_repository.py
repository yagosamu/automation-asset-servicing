"""Integration contract for the local JSON/JSONL run repository."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from asset_servicing.adapters.persistence.json_repository import (
    JsonRunRepository,
    RunEvent,
)
from asset_servicing.domain.models import (
    CoverageFinding,
    ExtractedVariable,
    FindingReviewStatus,
    ReviewAction,
    ReviewDecision,
    ReviewStatus,
    Run,
    RunState,
    SourceKind,
    ValidationResult,
    ValidationVerdict,
)

pytestmark = pytest.mark.integration


def make_run() -> Run:
    variable = ExtractedVariable(
        id="variable-001",
        canonical_name="prazo_resgate",
        original_name="Prazo para pagamento do resgate",
        original_value="D+30",
        current_name="prazo_resgate",
        current_value="D+30",
        evidence_text="O pagamento do resgate será realizado em até 30 dias.",
        source_pages=[7],
        source_kind=SourceKind.PROSE,
        clause_reference="Art. 12",
        reviewed=True,
        review_status=ReviewStatus.CONFIRMED,
    )
    return Run(
        run_id="run-001",
        document_name="regulamento.pdf",
        document_sha256="a" * 64,
        page_count=12,
        created_at=datetime(2026, 9, 27, 12, 0, tzinfo=UTC),
        state=RunState.REVIEWING,
        variables=[variable],
        validations=[
            ValidationResult(
                variable_id=variable.id,
                confidence=0.95,
                verdict=ValidationVerdict.SUPPORTED,
                rationale="Valor sustentado pela evidência.",
                issues=[],
            )
        ],
        coverage_findings=[
            CoverageFinding(
                id="finding-001",
                description="Possível omissão já descartada.",
                evidence_text="Trecho analisado durante a validação.",
                source_pages=[7],
                review_status=FindingReviewStatus.DISMISSED,
            )
        ],
        reviews=[
            ReviewDecision(
                variable_id=variable.id,
                action=ReviewAction.CONFIRM,
                previous_name=variable.original_name,
                previous_value=variable.original_value,
                resulting_name=variable.current_name,
                resulting_value=variable.current_value,
                reviewed_at=datetime(2026, 9, 27, 13, 0, tzinfo=UTC),
            )
        ],
    )


def make_event(**updates: object) -> RunEvent:
    data: dict[str, object] = {
        "run_id": "run-001",
        "stage": "validation",
        "event": "completed",
        "status": "success",
        "started_at": datetime(2026, 9, 27, 13, 0, tzinfo=UTC),
        "duration_ms": 1250,
        "model": "gpt-5.6-sol",
        "prompt_version": "validator-v1",
        "input_pages": [7],
        "usage": {"input_tokens": 100, "output_tokens": 30},
        "error": None,
    }
    data.update(updates)
    return RunEvent.model_validate(data)


def test_save_creates_expected_run_layout_and_pdf_copy(tmp_path: Path) -> None:
    source_pdf = tmp_path / "source.pdf"
    source_pdf.write_bytes(b"%PDF-test-document")
    repository = JsonRunRepository(tmp_path / "data" / "runs")

    repository.save_run(make_run(), source_pdf=source_pdf)

    run_dir = tmp_path / "data" / "runs" / "run-001"
    assert (run_dir / "source.pdf").read_bytes() == source_pdf.read_bytes()
    assert (run_dir / "run.json").is_file()
    assert (run_dir / "extraction.json").is_file()
    assert (run_dir / "validation.json").is_file()
    assert (run_dir / "reviews.json").is_file()
    assert (run_dir / "events.jsonl").is_file()


def test_save_load_round_trip_preserves_nested_models_and_reviews(tmp_path: Path) -> None:
    repository = JsonRunRepository(tmp_path / "runs")
    expected = make_run()

    repository.save_run(expected)
    loaded = repository.load_run(expected.run_id)

    assert loaded == expected
    assert loaded.variables[0].evidence_text == expected.variables[0].evidence_text
    assert loaded.validations[0].confidence == 0.95
    assert loaded.coverage_findings[0].review_status is FindingReviewStatus.DISMISSED
    assert loaded.reviews[0].action is ReviewAction.CONFIRM


def test_projection_files_contain_their_respective_records(tmp_path: Path) -> None:
    repository = JsonRunRepository(tmp_path / "runs")
    repository.save_run(make_run())
    run_dir = tmp_path / "runs" / "run-001"

    extraction = json.loads((run_dir / "extraction.json").read_text(encoding="utf-8"))
    validation = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    reviews = json.loads((run_dir / "reviews.json").read_text(encoding="utf-8"))

    assert extraction[0]["current_value"] == "D+30"
    assert validation[0]["confidence"] == 0.95
    assert reviews["decisions"][0]["action"] == "confirm"


def test_append_event_persists_required_observability_fields(tmp_path: Path) -> None:
    repository = JsonRunRepository(tmp_path / "runs")
    repository.save_run(make_run())

    repository.append_event(make_event())
    events = repository.load_events("run-001")

    assert len(events) == 1
    assert events[0].run_id == "run-001"
    assert events[0].stage == "validation"
    assert events[0].duration_ms == 1250
    assert events[0].model == "gpt-5.6-sol"
    assert events[0].usage == {"input_tokens": 100, "output_tokens": 30}
    assert events[0].error is None


def test_append_event_preserves_jsonl_order(tmp_path: Path) -> None:
    repository = JsonRunRepository(tmp_path / "runs")
    repository.save_run(make_run())

    repository.append_event(make_event(event="started", status="running"))
    repository.append_event(make_event(event="completed", status="success"))

    lines = (
        (tmp_path / "runs" / "run-001" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert [json.loads(line)["event"] for line in lines] == ["started", "completed"]


def test_save_replaces_state_atomically_and_leaves_no_temp_files(tmp_path: Path) -> None:
    repository = JsonRunRepository(tmp_path / "runs")
    repository.save_run(make_run())

    run_dir = tmp_path / "runs" / "run-001"
    assert list(run_dir.glob(".*.tmp")) == []


def test_failure_before_replace_keeps_last_valid_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = JsonRunRepository(tmp_path / "runs")
    original = make_run()
    repository.save_run(original)
    original_name = original.document_name
    original.document_name = "novo-regulamento.pdf"

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(
        "asset_servicing.adapters.persistence.json_repository.os.replace", fail_replace
    )
    with pytest.raises(OSError, match="simulated replace failure"):
        repository.save_run(original)

    loaded = repository.load_run("run-001")
    assert loaded.document_name == original_name
    assert list((tmp_path / "runs" / "run-001").glob(".*.tmp")) == []


def test_load_unknown_run_reports_missing_state(tmp_path: Path) -> None:
    repository = JsonRunRepository(tmp_path / "runs")

    with pytest.raises(FileNotFoundError, match="run-404"):
        repository.load_run("run-404")


def test_event_sanitization_redacts_sensitive_fields_and_error_text(tmp_path: Path) -> None:
    repository = JsonRunRepository(tmp_path / "runs")
    repository.save_run(make_run())

    repository.append_event(
        make_event(
            usage={"api_key": "sentinel-secret-123", "input_tokens": 90},
            error="authorization=Bearer sentinel-secret-123",
        )
    )

    raw_events = (tmp_path / "runs" / "run-001" / "events.jsonl").read_text(encoding="utf-8")
    assert "sentinel-secret-123" not in raw_events
    assert "[REDACTED]" in raw_events


def test_secret_sentinel_is_absent_from_all_persisted_files(tmp_path: Path) -> None:
    repository = JsonRunRepository(tmp_path / "runs")
    repository.save_run(make_run())
    repository.append_event(
        make_event(error="token=sentinel-secret-123", usage={"secret": "sentinel-secret-123"})
    )

    persisted = "".join(
        file.read_text(encoding="utf-8", errors="ignore")
        for file in (tmp_path / "runs" / "run-001").rglob("*")
        if file.is_file() and file.suffix != ".pdf"
    )
    assert "sentinel-secret-123" not in persisted


def test_save_rejects_path_unsafe_run_identifier(tmp_path: Path) -> None:
    repository = JsonRunRepository(tmp_path / "runs")
    unsafe = make_run()
    unsafe.run_id = "..\\outside"

    with pytest.raises(ValueError, match="safe run_id"):
        repository.save_run(unsafe)


def test_save_rejects_source_path_that_is_not_a_file(tmp_path: Path) -> None:
    repository = JsonRunRepository(tmp_path / "runs")

    with pytest.raises(FileNotFoundError):
        repository.save_run(make_run(), source_pdf=tmp_path / "missing.pdf")
