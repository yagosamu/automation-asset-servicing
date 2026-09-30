"""Offline quality gates over recorded extraction results."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from asset_servicing.evals.runner import EvaluationPaths, main, run_evaluation

pytestmark = pytest.mark.eval
ROOT = Path(__file__).resolve().parents[2]


def mutated_recording(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> EvaluationPaths:
    paths = EvaluationPaths.defaults(ROOT)
    recording = yaml.safe_load(paths.recorded_extractions.read_text(encoding="utf-8"))
    mutate(recording)
    mutated_path = tmp_path / "extractions.yaml"
    mutated_path.write_text(yaml.safe_dump(recording, allow_unicode=True), encoding="utf-8")
    return replace(paths, recorded_extractions=mutated_path)


def mutated_granularity_fixture(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> EvaluationPaths:
    paths = EvaluationPaths.defaults(ROOT)
    fixture = yaml.safe_load(paths.granularity_fixture.read_text(encoding="utf-8"))
    mutate(fixture)
    mutated_path = tmp_path / "granularity_fixture.yaml"
    mutated_path.write_text(yaml.safe_dump(fixture, allow_unicode=True), encoding="utf-8")
    return replace(paths, granularity_fixture=mutated_path)


def test_recorded_extractions_cover_all_critical_fields() -> None:
    report = run_evaluation(EvaluationPaths.defaults(ROOT))

    coverage = report.metrics["critical_field_coverage"]
    assert coverage.numerator == 23
    assert coverage.denominator == 23
    assert coverage.score == 1.0
    assert coverage.passed is True


def test_missing_critical_field_fails_coverage_gate(tmp_path: Path) -> None:
    def remove_field(recording: dict[str, Any]) -> None:
        recording["documents"][0]["variables"].pop()

    report = run_evaluation(mutated_recording(tmp_path, remove_field))

    coverage = report.metrics["critical_field_coverage"]
    assert coverage.numerator == 22
    assert coverage.denominator == 23
    assert coverage.score == pytest.approx(22 / 23)
    assert coverage.passed is False
    assert report.passed is False
    assert report.failures[0].gate == "critical_field_coverage"
    assert report.failures[0].variable_id == "reg-23183.same-day-redemption"


def test_wrong_critical_value_fails_value_gate(tmp_path: Path) -> None:
    def change_value(recording: dict[str, Any]) -> None:
        recording["documents"][0]["variables"][0]["value"] = "D+30"

    report = run_evaluation(mutated_recording(tmp_path, change_value))

    accuracy = report.metrics["critical_value_accuracy"]
    assert accuracy.numerator == 22
    assert accuracy.denominator == 23
    assert accuracy.score == pytest.approx(22 / 23)
    assert accuracy.passed is False
    assert report.passed is False
    assert any(failure.gate == "critical_value_accuracy" for failure in report.failures)


def test_recorded_evidence_resolves_on_declared_source_pages() -> None:
    report = run_evaluation(EvaluationPaths.defaults(ROOT))

    integrity = report.metrics["evidence_integrity"]
    assert integrity.numerator == 23
    assert integrity.denominator == 23
    assert integrity.score == 1.0
    assert integrity.passed is True


def test_unresolvable_evidence_fails_evidence_gate(tmp_path: Path) -> None:
    def change_evidence(recording: dict[str, Any]) -> None:
        recording["documents"][0]["variables"][0]["evidence"] = "Trecho inventado"

    report = run_evaluation(mutated_recording(tmp_path, change_evidence))

    integrity = report.metrics["evidence_integrity"]
    assert integrity.numerator == 22
    assert integrity.denominator == 23
    assert integrity.score == pytest.approx(22 / 23)
    assert integrity.passed is False
    assert report.passed is False
    assert any(failure.gate == "evidence_integrity" for failure in report.failures)


def test_adjacent_section_variable_fails_boundary_gate(tmp_path: Path) -> None:
    def add_adjacent_variable(recording: dict[str, Any]) -> None:
        recording["documents"][0]["variables"].append(
            {
                "name": "Prazo de convocação da assembleia",
                "value": "10 dias de antecedência",
                "evidence": ("A convocação ocorrerá, no mínimo, com 10 (dez) dias de antecedência"),
                "pages": [7],
            }
        )

    report = run_evaluation(mutated_recording(tmp_path, add_adjacent_variable))

    assert report.passed is False
    assert any(failure.gate == "adjacent_section_exclusion" for failure in report.failures)


def test_adjacent_section_omission_fails_boundary_gate(tmp_path: Path) -> None:
    def add_adjacent_omission(recording: dict[str, Any]) -> None:
        recording["documents"][0]["omissions"].append(
            {
                "description": "Possível regra de quórum omitida.",
                "evidence": "O quórum para aprovação é de maioria simples dos votos dos presentes",
                "pages": [7],
            }
        )

    report = run_evaluation(mutated_recording(tmp_path, add_adjacent_omission))

    assert report.passed is False
    assert any(failure.gate == "adjacent_section_exclusion" for failure in report.failures)


def test_fragmented_coordinated_attributes_fail_granularity_gate(tmp_path: Path) -> None:
    def fragment_rule(fixture: dict[str, Any]) -> None:
        case = fixture["cases"][0]
        case["recorded_output"]["variables"] = [
            {"name": "tratamento_equanime", "value": "equânime"},
            {"name": "simultaneidade", "value": "simultânea"},
            {"name": "proporcionalidade", "value": "proporcional"},
            {"name": "taxa_saida", "value": "sem taxa de saída"},
        ]

    report = run_evaluation(mutated_granularity_fixture(tmp_path, fragment_rule))

    assert report.passed is False
    assert any(failure.gate == "operational_granularity" for failure in report.failures)


def test_grouped_rule_missing_an_attribute_fails_granularity_gate(tmp_path: Path) -> None:
    def remove_attribute(fixture: dict[str, Any]) -> None:
        variable = fixture["cases"][0]["recorded_output"]["variables"][0]
        variable["value"] = "Execução equânime, simultânea e proporcional entre todos os cotistas"

    report = run_evaluation(mutated_granularity_fixture(tmp_path, remove_attribute))

    assert report.passed is False
    assert any(failure.gate == "operational_granularity" for failure in report.failures)


def test_chapter_6_fixture_matches_the_recorded_location() -> None:
    report = run_evaluation(EvaluationPaths.defaults(ROOT))

    assert report.chapter_6.expected_chapter == 6
    assert report.chapter_6.actual_page_start == 18
    assert report.chapter_6.actual_page_end == 23
    assert report.chapter_6.passed is True


def test_wrong_chapter_6_pages_fail_location_scenario(tmp_path: Path) -> None:
    paths = EvaluationPaths.defaults(ROOT)
    fixture = yaml.safe_load(paths.chapter_6_fixture.read_text(encoding="utf-8"))
    fixture["recorded_output"]["page_start"] = 19
    mutated_path = tmp_path / "chapter_6_fixture.yaml"
    mutated_path.write_text(yaml.safe_dump(fixture, allow_unicode=True), encoding="utf-8")

    report = run_evaluation(replace(paths, chapter_6_fixture=mutated_path))

    assert report.chapter_6.passed is False
    assert report.passed is False
    assert any(failure.gate == "chapter_6_location" for failure in report.failures)


def test_all_adversarial_errors_are_routed_to_review() -> None:
    report = run_evaluation(EvaluationPaths.defaults(ROOT))

    recall = report.metrics["adversarial_review_recall"]
    assert recall.numerator == 3
    assert recall.denominator == 3
    assert recall.score == 1.0
    assert recall.passed is True


def test_surviving_adversarial_error_fails_review_gate(tmp_path: Path) -> None:
    paths = EvaluationPaths.defaults(ROOT)
    fixture = yaml.safe_load(paths.adversarial_cases.read_text(encoding="utf-8"))
    escaped = fixture["cases"][0]["recorded_output"]
    escaped.update(confidence=0.99, verdict="supported", has_conflict=False)
    mutated_path = tmp_path / "adversarial_cases.yaml"
    mutated_path.write_text(yaml.safe_dump(fixture, allow_unicode=True), encoding="utf-8")

    report = run_evaluation(replace(paths, adversarial_cases=mutated_path))

    recall = report.metrics["adversarial_review_recall"]
    assert recall.numerator == 2
    assert recall.denominator == 3
    assert recall.score == pytest.approx(2 / 3)
    assert recall.passed is False
    assert report.passed is False
    assert any(failure.gate == "adversarial_review_recall" for failure in report.failures)


def test_all_four_metrics_are_blocking_at_one_hundred_percent() -> None:
    report = run_evaluation(EvaluationPaths.defaults(ROOT))

    assert set(report.metrics) == {
        "adversarial_review_recall",
        "critical_field_coverage",
        "critical_value_accuracy",
        "evidence_integrity",
    }
    assert all(metric.target == 1.0 for metric in report.metrics.values())
    assert all(metric.passed is True for metric in report.metrics.values())
    assert report.passed is True


def test_report_records_models_prompts_corpus_and_generation_time() -> None:
    generated_at = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)

    report = run_evaluation(EvaluationPaths.defaults(ROOT), generated_at=generated_at)

    assert report.generated_at == generated_at
    assert report.recording_id == "btg-regulations-offline-v1"
    assert report.models == {
        "locator": "recorded-fixture-v1",
        "extractor": "recorded-fixture-v1",
        "validator": "recorded-fixture-v1",
    }
    assert report.prompt_versions == {
        "locator": "locator-v1",
        "extractor": "extractor-v3",
        "validator": "validator-v3",
    }
    assert report.corpus.corpus_id == "btg-regulations-v1"
    assert report.corpus.document_count == 4
    assert len(report.corpus.manifest_sha256) == 64


def test_report_is_written_as_json(tmp_path: Path) -> None:
    report_path = tmp_path / "reports" / "latest.json"

    report = run_evaluation(EvaluationPaths.defaults(ROOT), report_path=report_path)
    written = json.loads(report_path.read_text(encoding="utf-8"))

    assert written == report.model_dump(mode="json")
    assert written["passed"] is True


def test_baseline_comparison_has_zero_metric_deltas() -> None:
    report = run_evaluation(EvaluationPaths.defaults(ROOT))

    assert report.baseline is not None
    assert report.baseline.baseline_id == "btg-regulations-offline-v1"
    assert report.baseline.contract_matches is True
    assert report.baseline.corpus_matches is True
    assert report.baseline.metric_deltas == {
        "adversarial_review_recall": 0.0,
        "critical_field_coverage": 0.0,
        "critical_value_accuracy": 0.0,
        "evidence_integrity": 0.0,
    }
    assert report.baseline.chapter_6_matches is True
    assert report.baseline.compatible is True


def test_contract_change_requires_an_updated_baseline(tmp_path: Path) -> None:
    paths = EvaluationPaths.defaults(ROOT)
    logical_name, source_path = paths.contract_files[0]
    changed_source = tmp_path / source_path.name
    changed_source.write_text(
        source_path.read_text(encoding="utf-8") + "\n# changed prompt\n",
        encoding="utf-8",
    )
    changed_contract = ((logical_name, changed_source), *paths.contract_files[1:])

    report = run_evaluation(replace(paths, contract_files=changed_contract))

    assert report.baseline is not None
    assert report.baseline.contract_matches is False
    assert report.baseline.compatible is False
    assert report.passed is False
    assert any(failure.gate == "baseline_contract" for failure in report.failures)


def test_recording_with_stale_prompt_version_fails_contract(tmp_path: Path) -> None:
    def change_prompt_version(recording: dict[str, Any]) -> None:
        recording["prompt_versions"]["extractor"] = "extractor-v2"

    report = run_evaluation(mutated_recording(tmp_path, change_prompt_version))

    assert report.passed is False
    assert any(failure.gate == "recording_prompt_version" for failure in report.failures)


def test_public_command_writes_report_and_returns_success(tmp_path: Path) -> None:
    report_path = tmp_path / "eval-report.json"

    exit_code = main(["--root", str(ROOT), "--report", str(report_path)])

    assert exit_code == 0
    assert json.loads(report_path.read_text(encoding="utf-8"))["passed"] is True
