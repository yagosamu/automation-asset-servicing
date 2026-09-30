"""Auditable human review operations over persisted extraction runs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from asset_servicing.domain import (
    CoverageFinding,
    ExtractedVariable,
    FindingReviewStatus,
    ReviewAction,
    ReviewDecision,
    ReviewStatus,
    Run,
    RunState,
    SourceKind,
)


class RunRepository(Protocol):
    """Persistence operations required by the review use case."""

    def load_run(self, run_id: str) -> Run: ...

    def save_run(self, run: Run) -> None: ...


def _new_variable_id() -> str:
    return str(uuid4())


class ReviewService:
    """Apply explicit human decisions without losing original source data."""

    def __init__(
        self,
        *,
        repository: RunRepository,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        variable_id_factory: Callable[[], str] = _new_variable_id,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._variable_id_factory = variable_id_factory

    def get_run(self, run_id: str) -> Run:
        """Rehydrate the persisted review state."""

        return self._repository.load_run(run_id)

    def confirm(
        self,
        run_id: str,
        variable_id: str,
        *,
        note: str | None = None,
    ) -> ExtractedVariable:
        """Confirm a pending variable without changing its current value."""

        return self._review_variable(
            run_id,
            variable_id,
            action=ReviewAction.CONFIRM,
            note=note,
        )

    def edit(
        self,
        run_id: str,
        variable_id: str,
        *,
        name: str,
        value: str,
        note: str | None = None,
    ) -> ExtractedVariable:
        """Replace the current name and value while preserving original fields."""

        name = self._required_text(name, field="name")
        value = self._required_text(value, field="value")
        return self._review_variable(
            run_id,
            variable_id,
            action=ReviewAction.EDIT,
            resulting_name=name,
            resulting_value=value,
            note=note,
        )

    def mark_not_applicable(
        self,
        run_id: str,
        variable_id: str,
        *,
        note: str,
    ) -> ExtractedVariable:
        """Resolve a pending variable as not applicable with an audit note."""

        note = self._required_text(note, field="note")
        return self._review_variable(
            run_id,
            variable_id,
            action=ReviewAction.NOT_APPLICABLE,
            note=note,
        )

    def add_missing(
        self,
        run_id: str,
        finding_id: str,
        *,
        name: str,
        value: str,
        evidence: str,
        note: str | None = None,
    ) -> ExtractedVariable:
        """Accept an omission and create its explicitly reviewed variable."""

        name = self._required_text(name, field="name")
        value = self._required_text(value, field="value")
        evidence = self._required_text(evidence, field="evidence")
        run = self._repository.load_run(run_id)
        self._ensure_reviewing(run)
        finding = next(
            (item for item in run.coverage_findings if item.id == finding_id),
            None,
        )
        if finding is None:
            raise ValueError(f"coverage finding not found: {finding_id}")
        if finding.review_status is not FindingReviewStatus.PENDING:
            raise ValueError(f"coverage finding already reviewed: {finding_id}")

        variable_id = self._variable_id_factory()
        if any(item.id == variable_id for item in run.variables):
            raise ValueError(f"variable id already exists: {variable_id}")
        variable = ExtractedVariable(
            id=variable_id,
            canonical_name=name,
            original_name=name,
            original_value=value,
            current_name=name,
            current_value=value,
            evidence_text=evidence,
            source_pages=finding.source_pages,
            source_kind=SourceKind.HUMAN_ADDED,
            reviewed=True,
            review_status=ReviewStatus.CONFIRMED,
        )
        decision = ReviewDecision(
            variable_id=variable.id,
            action=ReviewAction.ADD_MISSING,
            resulting_name=name,
            resulting_value=value,
            note=note,
            reviewed_at=self._clock(),
        )
        finding.review_status = FindingReviewStatus.ACCEPTED
        run.variables.append(variable)
        run.reviews.append(decision)
        self._invalidate_exports(run)
        self._repository.save_run(run)
        return variable

    def dismiss_omission(
        self,
        run_id: str,
        finding_id: str,
        *,
        note: str,
    ) -> CoverageFinding:
        """Resolve a false or out-of-scope omission without creating a variable."""

        note = self._required_text(note, field="note")
        run = self._repository.load_run(run_id)
        self._ensure_reviewing(run)
        finding = next(
            (item for item in run.coverage_findings if item.id == finding_id),
            None,
        )
        if finding is None:
            raise ValueError(f"coverage finding not found: {finding_id}")
        if finding.review_status is not FindingReviewStatus.PENDING:
            raise ValueError(f"coverage finding already reviewed: {finding_id}")

        finding.review_status = FindingReviewStatus.DISMISSED
        run.reviews.append(
            ReviewDecision(
                finding_id=finding.id,
                action=ReviewAction.DISMISS_OMISSION,
                note=note,
                reviewed_at=self._clock(),
            )
        )
        self._invalidate_exports(run)
        self._repository.save_run(run)
        return finding

    def _review_variable(
        self,
        run_id: str,
        variable_id: str,
        *,
        action: ReviewAction,
        resulting_name: str | None = None,
        resulting_value: str | None = None,
        note: str | None = None,
    ) -> ExtractedVariable:
        run = self._repository.load_run(run_id)
        self._ensure_reviewing(run)
        variable = self._pending_variable(run, variable_id)
        decision = ReviewDecision(
            variable_id=variable.id,
            action=action,
            previous_name=variable.current_name,
            previous_value=variable.current_value,
            resulting_name=resulting_name or variable.current_name,
            resulting_value=resulting_value or variable.current_value,
            note=note,
            reviewed_at=self._clock(),
        )
        variable.apply_review(decision)
        run.reviews.append(decision)
        self._invalidate_exports(run)
        self._repository.save_run(run)
        return variable

    @staticmethod
    def _invalidate_exports(run: Run) -> None:
        run.preliminary_export_path = None
        run.final_export_path = None

    @staticmethod
    def _required_text(value: str, *, field: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field} must not be blank")
        return normalized

    @staticmethod
    def _ensure_reviewing(run: Run) -> None:
        if run.state is not RunState.REVIEWING:
            raise ValueError("review decisions require a run in reviewing state")

    @staticmethod
    def _pending_variable(run: Run, variable_id: str) -> ExtractedVariable:
        variable = next((item for item in run.variables if item.id == variable_id), None)
        if variable is None:
            raise ValueError(f"variable not found: {variable_id}")
        if variable.review_status is not ReviewStatus.PENDING:
            raise ValueError(f"variable already reviewed: {variable_id}")
        return variable


__all__ = ["ReviewService", "RunRepository"]
