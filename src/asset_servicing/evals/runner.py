"""Compare recorded extraction outputs with the versioned golden set."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

from asset_servicing.application.extractor import EXTRACTOR_PROMPT_VERSION
from asset_servicing.application.locator import LOCATOR_PROMPT_VERSION
from asset_servicing.application.validator import VALIDATOR_PROMPT_VERSION

CONTRACT_RELATIVE_PATHS = (
    "src/asset_servicing/application/locator.py",
    "src/asset_servicing/application/extractor.py",
    "src/asset_servicing/application/validator.py",
    "src/asset_servicing/ports/llm.py",
    "src/asset_servicing/domain/models.py",
    "src/asset_servicing/application/pipeline.py",
)


class MetricResult(BaseModel):
    """One blocking quality metric and its supporting counts."""

    model_config = ConfigDict(frozen=True)

    numerator: int = Field(ge=0)
    denominator: int = Field(gt=0)
    score: float = Field(ge=0, le=1)
    target: float = Field(default=1.0, ge=0, le=1)
    passed: bool


class EvaluationFailure(BaseModel):
    """Actionable reason why one evaluation gate failed."""

    model_config = ConfigDict(frozen=True)

    gate: str
    document_id: str | None = None
    variable_id: str | None = None
    detail: str


class ChapterScenarioResult(BaseModel):
    """Exact outcome required from the held-out Chapter 6 locator scenario."""

    model_config = ConfigDict(frozen=True)

    expected_chapter: int = Field(gt=0)
    expected_title: str
    expected_page_start: int = Field(gt=0)
    expected_page_end: int = Field(gt=0)
    actual_title: str | None
    actual_page_start: int | None
    actual_page_end: int | None
    passed: bool


class CorpusSummary(BaseModel):
    """Identity of the immutable source corpus used by this evaluation."""

    model_config = ConfigDict(frozen=True)

    corpus_id: str
    schema_version: int
    document_count: int = Field(gt=0)
    manifest_sha256: str = Field(min_length=64, max_length=64)


class ContractSummary(BaseModel):
    """Fingerprint of prompts, schemas, and pipeline code under evaluation."""

    model_config = ConfigDict(frozen=True)

    files: tuple[str, ...]
    fingerprint: str = Field(min_length=64, max_length=64)


class BaselineComparison(BaseModel):
    """Compatibility and metric deltas against the committed baseline."""

    model_config = ConfigDict(frozen=True)

    baseline_id: str
    contract_matches: bool
    corpus_matches: bool
    metric_deltas: dict[str, float]
    chapter_6_matches: bool
    compatible: bool


class EvaluationReport(BaseModel):
    """Serializable outcome of one deterministic offline evaluation."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = 1
    generated_at: datetime
    recording_id: str
    models: dict[str, str]
    prompt_versions: dict[str, str]
    corpus: CorpusSummary
    contract: ContractSummary
    metrics: dict[str, MetricResult]
    chapter_6: ChapterScenarioResult
    baseline: BaselineComparison | None
    failures: list[EvaluationFailure]
    passed: bool


@dataclass(frozen=True, slots=True)
class EvaluationPaths:
    """Versioned inputs consumed by the offline runner."""

    project_root: Path
    golden_root: Path
    recorded_extractions: Path
    chapter_6_fixture: Path
    adversarial_cases: Path
    baseline: Path
    contract_files: tuple[tuple[str, Path], ...]

    @classmethod
    def defaults(cls, project_root: Path) -> EvaluationPaths:
        root = Path(project_root)
        return cls(
            project_root=root,
            golden_root=root / "evals" / "golden" / "v1",
            recorded_extractions=root / "evals" / "recorded" / "v1" / "extractions.yaml",
            chapter_6_fixture=root / "evals" / "golden" / "v1" / "chapter_6_fixture.yaml",
            adversarial_cases=root / "evals" / "golden" / "v1" / "adversarial_cases.yaml",
            baseline=root / "evals" / "baselines" / "v1.json",
            contract_files=tuple(
                (relative_path, root / relative_path) for relative_path in CONTRACT_RELATIVE_PATHS
            ),
        )


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"expected a mapping in {path}")
    return value


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _metric(numerator: int, denominator: int) -> MetricResult:
    score = numerator / denominator
    return MetricResult(
        numerator=numerator,
        denominator=denominator,
        score=score,
        passed=score == 1.0,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contract_summary(contract_files: tuple[tuple[str, Path], ...]) -> ContractSummary:
    digest = hashlib.sha256()
    for logical_name, path in contract_files:
        digest.update(logical_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return ContractSummary(
        files=tuple(logical_name for logical_name, _ in contract_files),
        fingerprint=digest.hexdigest(),
    )


@cache
def _pdf_pages(path: Path) -> tuple[str, ...]:
    return tuple(_normalized(page.extract_text() or "") for page in PdfReader(path).pages)


def _is_routed_to_review(recorded_output: dict[str, Any]) -> bool:
    if recorded_output["kind"] == "omission":
        return True
    return bool(
        recorded_output["confidence"] < 0.85
        or recorded_output["verdict"] != "supported"
        or recorded_output["has_conflict"]
    )


def run_evaluation(
    paths: EvaluationPaths,
    *,
    generated_at: datetime | None = None,
    report_path: Path | None = None,
) -> EvaluationReport:
    """Run all offline gates, compare the baseline, and optionally persist a report."""

    manifest_path = paths.golden_root / "manifest.yaml"
    manifest = _load_yaml(manifest_path)
    recorded = _load_yaml(paths.recorded_extractions)
    recorded_by_document = {
        document["document_id"]: document["variables"] for document in recorded["documents"]
    }
    critical_fields: list[tuple[str, str, dict[str, Any]]] = []
    for manifest_document in manifest["documents"]:
        expected = _load_yaml(paths.golden_root / manifest_document["expected"])
        critical_fields.extend(
            (expected["document_id"], manifest_document["filename"], variable)
            for variable in expected["variables"]
            if variable["critical"]
        )

    failures: list[EvaluationFailure] = []
    covered = 0
    correct_values = 0
    valid_evidence = 0
    for document_id, source_filename, expected in critical_fields:
        accepted_names = {_normalized(name) for name in expected["accepted_names"]}
        candidates = recorded_by_document.get(document_id, [])
        candidate = next(
            (item for item in candidates if _normalized(item["name"]) in accepted_names),
            None,
        )
        if candidate is None:
            failures.append(
                EvaluationFailure(
                    gate="critical_field_coverage",
                    document_id=document_id,
                    variable_id=expected["id"],
                    detail="No recorded variable matches an accepted field name.",
                )
            )
            failures.append(
                EvaluationFailure(
                    gate="critical_value_accuracy",
                    document_id=document_id,
                    variable_id=expected["id"],
                    detail="A missing critical field has no value to validate.",
                )
            )
            failures.append(
                EvaluationFailure(
                    gate="evidence_integrity",
                    document_id=document_id,
                    variable_id=expected["id"],
                    detail="A missing critical field has no evidence to validate.",
                )
            )
            continue

        covered += 1
        accepted_values = {_normalized(value) for value in expected["accepted_values"]}
        if _normalized(candidate["value"]) in accepted_values:
            correct_values += 1
        else:
            failures.append(
                EvaluationFailure(
                    gate="critical_value_accuracy",
                    document_id=document_id,
                    variable_id=expected["id"],
                    detail="The recorded value does not match any accepted golden value.",
                )
            )

        source_pages = _pdf_pages(paths.project_root / "Regulamentos" / source_filename)
        candidate_pages = candidate["pages"]
        pages_are_expected = bool(candidate_pages) and set(candidate_pages) <= set(
            expected["pages"]
        )
        pages_are_valid = pages_are_expected and all(
            1 <= page_number <= len(source_pages) for page_number in candidate_pages
        )
        declared_text = (
            " ".join(source_pages[page_number - 1] for page_number in candidate_pages)
            if pages_are_valid
            else ""
        )
        if pages_are_valid and _normalized(candidate["evidence"]) in declared_text:
            valid_evidence += 1
        else:
            failures.append(
                EvaluationFailure(
                    gate="evidence_integrity",
                    document_id=document_id,
                    variable_id=expected["id"],
                    detail="Recorded evidence does not resolve on the expected source pages.",
                )
            )

    coverage = _metric(covered, len(critical_fields))
    value_accuracy = _metric(correct_values, len(critical_fields))
    evidence_integrity = _metric(valid_evidence, len(critical_fields))
    chapter_fixture = _load_yaml(paths.chapter_6_fixture)
    expected_location = chapter_fixture["expected"]
    actual_location = chapter_fixture["recorded_output"]
    chapter_passed = (
        actual_location["status"] == expected_location["status"]
        and _normalized(actual_location["title"]) == _normalized(expected_location["title"])
        and actual_location["page_start"] == expected_location["page_start"]
        and actual_location["page_end"] == expected_location["page_end"]
    )
    chapter_6 = ChapterScenarioResult(
        expected_chapter=expected_location["chapter"],
        expected_title=expected_location["title"],
        expected_page_start=expected_location["page_start"],
        expected_page_end=expected_location["page_end"],
        actual_title=actual_location.get("title"),
        actual_page_start=actual_location.get("page_start"),
        actual_page_end=actual_location.get("page_end"),
        passed=chapter_passed,
    )
    if not chapter_passed:
        failures.append(
            EvaluationFailure(
                gate="chapter_6_location",
                detail="Recorded Chapter 6 location differs from the held-out expectation.",
            )
        )

    adversarial_fixture = _load_yaml(paths.adversarial_cases)
    adversarial_cases = [case for case in adversarial_fixture["cases"] if case["expected_review"]]
    routed_cases = 0
    for case in adversarial_cases:
        if _is_routed_to_review(case["recorded_output"]):
            routed_cases += 1
        else:
            failures.append(
                EvaluationFailure(
                    gate="adversarial_review_recall",
                    variable_id=case["id"],
                    detail="An adversarial error escaped the manual-review queue.",
                )
            )
    adversarial_recall = _metric(routed_cases, len(adversarial_cases))
    metrics = {
        "critical_field_coverage": coverage,
        "critical_value_accuracy": value_accuracy,
        "evidence_integrity": evidence_integrity,
        "adversarial_review_recall": adversarial_recall,
    }

    current_prompt_versions = {
        "locator": LOCATOR_PROMPT_VERSION,
        "extractor": EXTRACTOR_PROMPT_VERSION,
        "validator": VALIDATOR_PROMPT_VERSION,
    }
    for agent, current_version in current_prompt_versions.items():
        if recorded["prompt_versions"].get(agent) != current_version:
            failures.append(
                EvaluationFailure(
                    gate="recording_prompt_version",
                    detail=f"Recorded {agent} prompt version does not match the current code.",
                )
            )

    corpus = CorpusSummary(
        corpus_id=manifest["corpus_id"],
        schema_version=manifest["schema_version"],
        document_count=len(manifest["documents"]),
        manifest_sha256=_sha256(manifest_path),
    )
    contract = _contract_summary(paths.contract_files)
    baseline_data = json.loads(paths.baseline.read_text(encoding="utf-8"))
    contract_matches = baseline_data["contract_fingerprint"] == contract.fingerprint
    corpus_matches = baseline_data["corpus_manifest_sha256"] == corpus.manifest_sha256
    metric_deltas = {
        name: metric.score - baseline_data["metrics"][name] for name, metric in metrics.items()
    }
    baseline = BaselineComparison(
        baseline_id=baseline_data["baseline_id"],
        contract_matches=contract_matches,
        corpus_matches=corpus_matches,
        metric_deltas=metric_deltas,
        chapter_6_matches=baseline_data["chapter_6_passed"] == chapter_passed,
        compatible=contract_matches and corpus_matches,
    )
    if not contract_matches:
        failures.append(
            EvaluationFailure(
                gate="baseline_contract",
                detail="Prompt, schema, or pipeline code changed without an updated baseline.",
            )
        )
    if not corpus_matches:
        failures.append(
            EvaluationFailure(
                gate="baseline_corpus",
                detail="Golden corpus changed without an updated baseline.",
            )
        )

    passed = (
        all(metric.passed for metric in metrics.values())
        and chapter_passed
        and baseline.compatible
        and not any(failure.gate == "recording_prompt_version" for failure in failures)
    )
    report = EvaluationReport(
        generated_at=generated_at or datetime.now(UTC),
        recording_id=recorded["recording_id"],
        models=recorded["models"],
        prompt_versions=recorded["prompt_versions"],
        corpus=corpus,
        contract=contract,
        metrics=metrics,
        chapter_6=chapter_6,
        baseline=baseline,
        failures=failures,
        passed=passed,
    )
    if report_path is not None:
        output_path = Path(report_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Run the committed offline baseline from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--report", type=Path, default=Path("output/evals/latest.json"))
    arguments = parser.parse_args(argv)
    report = run_evaluation(
        EvaluationPaths.defaults(arguments.root.resolve()),
        report_path=arguments.report,
    )
    return 0 if report.passed else 1


__all__ = [
    "BaselineComparison",
    "ChapterScenarioResult",
    "ContractSummary",
    "CorpusSummary",
    "EvaluationFailure",
    "EvaluationPaths",
    "EvaluationReport",
    "MetricResult",
    "main",
    "run_evaluation",
]


if __name__ == "__main__":
    raise SystemExit(main())
