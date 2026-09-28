"""Recovery, export, and operational-summary use cases."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from asset_servicing.domain import Run, ValidationVerdict


class OperationalEvent(Protocol):
    """Structured event fields used by the operational summary."""

    stage: str
    duration_ms: int
    model: str
    prompt_version: str
    usage: dict[str, object]


class RunRepository(Protocol):
    """Persisted-run operations required by the delivery workflow."""

    def list_runs(self) -> list[Run]: ...

    def load_run(self, run_id: str) -> Run: ...

    def load_events(self, run_id: str) -> Sequence[OperationalEvent]: ...


class WorkbookExporter(Protocol):
    """Workbook operations required by the delivery workflow."""

    def export_preliminary(self, run: Run) -> Path: ...

    def export_final(self, run: Run) -> Path: ...


@dataclass(frozen=True, slots=True)
class ExportArtifact:
    """One generated workbook ready for a local download."""

    path: Path
    data: bytes


@dataclass(frozen=True, slots=True)
class RunSummary:
    """Aggregated operational evidence for one persisted run."""

    total_duration_ms: int
    stage_durations_ms: dict[str, int]
    variable_count: int
    approved_count: int
    reviewed_count: int
    confidence_distribution: dict[str, int]
    call_count: int
    retry_count: int
    usage: dict[str, int | float]
    models: tuple[str, ...]
    prompt_versions: tuple[str, ...]


class RunDeliveryService:
    """Expose persisted runs to the local delivery interface."""

    def __init__(
        self,
        *,
        repository: RunRepository,
        exporter: WorkbookExporter,
    ) -> None:
        self._repository = repository
        self._exporter = exporter

    def list_runs(self) -> list[Run]:
        """Return persisted runs ordered from newest to oldest."""

        return self._repository.list_runs()

    def get_run(self, run_id: str) -> Run:
        """Rehydrate one persisted execution."""

        return self._repository.load_run(run_id)

    def export_preliminary(self, run_id: str) -> ExportArtifact:
        """Generate the preliminary workbook for the selected run."""

        path = self._exporter.export_preliminary(self._repository.load_run(run_id))
        return self._artifact(path)

    def export_final(self, run_id: str) -> ExportArtifact:
        """Generate the final workbook for a run without pending review."""

        path = self._exporter.export_final(self._repository.load_run(run_id))
        return self._artifact(path)

    def get_export(self, run_id: str, *, final: bool) -> ExportArtifact | None:
        """Return an existing workbook recorded by the selected run."""

        run = self._repository.load_run(run_id)
        persisted_path = run.final_export_path if final else run.preliminary_export_path
        if persisted_path is None:
            return None
        path = Path(persisted_path)
        if not path.is_file():
            return None
        return self._artifact(path)

    def summary(self, run_id: str) -> RunSummary:
        """Aggregate persisted run state and structured events."""

        run = self._repository.load_run(run_id)
        events = self._repository.load_events(run_id)
        stage_durations: dict[str, int] = {}
        usage: dict[str, int | float] = {}
        retry_count = 0
        for event in events:
            stage_durations[event.stage] = stage_durations.get(event.stage, 0) + event.duration_ms
            attempts = event.usage.get("attempts", 1)
            if isinstance(attempts, (int, float)) and not isinstance(attempts, bool):
                retry_count += max(0, int(attempts) - 1)
            for key, value in event.usage.items():
                if key in {"attempts", "response_id"}:
                    continue
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    usage[key] = usage.get(key, 0) + value

        distribution = {"high": 0, "medium": 0, "low": 0}
        for validation in run.validations:
            if validation.confidence >= 0.85:
                distribution["high"] += 1
            elif validation.confidence >= 0.50:
                distribution["medium"] += 1
            else:
                distribution["low"] += 1

        return RunSummary(
            total_duration_ms=sum(event.duration_ms for event in events),
            stage_durations_ms=stage_durations,
            variable_count=len(run.variables),
            approved_count=sum(
                validation.verdict is ValidationVerdict.SUPPORTED for validation in run.validations
            ),
            reviewed_count=sum(variable.reviewed for variable in run.variables),
            confidence_distribution=distribution,
            call_count=len(events),
            retry_count=retry_count,
            usage=usage,
            models=tuple(dict.fromkeys(event.model for event in events)),
            prompt_versions=tuple(dict.fromkeys(event.prompt_version for event in events)),
        )

    @staticmethod
    def _artifact(path: Path) -> ExportArtifact:
        return ExportArtifact(path=path, data=path.read_bytes())


__all__ = [
    "ExportArtifact",
    "OperationalEvent",
    "RunDeliveryService",
    "RunRepository",
    "RunSummary",
    "WorkbookExporter",
]
