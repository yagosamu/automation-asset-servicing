"""Atomic JSON/JSONL persistence for one local processing run."""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from asset_servicing.domain.models import (
    Run,
)

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]


class RunEvent(BaseModel):
    """Structured operational event persisted in ``events.jsonl``."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    event: str = Field(min_length=1)
    status: str = Field(min_length=1)
    started_at: datetime
    duration_ms: int = Field(ge=0)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    input_pages: list[int] = Field(default_factory=list)
    usage: dict[str, object] = Field(default_factory=dict)
    error: str | None = None


class JsonRunRepository:
    """Persist run state under a validated ``<root>/<run_id>`` directory."""

    _SENSITIVE_KEY = re.compile(
        r"^(?:api[_ -]?key|authorization|access[_ -]?token|token|secret|password|credential)$",
        re.IGNORECASE,
    )
    _SENSITIVE_INLINE = re.compile(
        r"(?P<key>api[_ -]?key|authorization|access[_ -]?token|token|secret|password|credential)"
        r"\s*[:=]\s*(?:Bearer\s+)?[^\s,;]+",
        re.IGNORECASE,
    )
    _BEARER = re.compile(r"Bearer\s+[^\s,;]+", re.IGNORECASE)
    _OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]+\b")

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def save_run(self, run: Run, *, source_pdf: Path | None = None) -> None:
        """Atomically persist canonical state and its audit projections."""

        run_dir = self._run_dir(run.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        if source_pdf is not None:
            self._copy_source(source_pdf, run_dir / "source.pdf")

        canonical = {"schema_version": 1, **run.model_dump(mode="json")}
        projections: list[tuple[Path, JsonValue]] = [
            (run_dir / "extraction.json", self._json_value(run.variables)),
            (run_dir / "validation.json", self._json_value(run.validations)),
            (
                run_dir / "reviews.json",
                {
                    "coverage_findings": self._json_value(run.coverage_findings),
                    "decisions": self._json_value(run.reviews),
                },
            ),
            (run_dir / "events.jsonl", ""),
        ]
        if (run_dir / "events.jsonl").exists():
            projections[-1] = (
                run_dir / "events.jsonl",
                (run_dir / "events.jsonl").read_text(encoding="utf-8"),
            )

        temporary_files: list[tuple[Path, Path]] = []
        try:
            for destination, value in projections:
                temporary_files.append(
                    (
                        self._write_temp(
                            destination, value, json_lines=destination.suffix == ".jsonl"
                        ),
                        destination,
                    )
                )
            canonical_temp = self._write_temp(run_dir / "run.json", canonical)
            temporary_files.append((canonical_temp, run_dir / "run.json"))

            for temporary, destination in temporary_files:
                if destination.name == "run.json":
                    continue
                os.replace(temporary, destination)
            os.replace(canonical_temp, run_dir / "run.json")
        finally:
            for temporary, _ in temporary_files:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)

    def load_run(self, run_id: str) -> Run:
        """Rehydrate the canonical run state and all nested domain models."""

        run_path = self._run_dir(run_id) / "run.json"
        if not run_path.is_file():
            raise FileNotFoundError(f"run state not found: {run_id}")
        payload = json.loads(run_path.read_text(encoding="utf-8"))
        payload.pop("schema_version", None)
        return Run.model_validate(payload)

    def list_runs(self) -> list[Run]:
        """Return every persisted run ordered from newest to oldest."""

        if not self.root.is_dir():
            return []
        runs = [self.load_run(run_path.parent.name) for run_path in self.root.glob("*/run.json")]
        return sorted(runs, key=lambda run: run.created_at, reverse=True)

    def source_path(self, run_id: str) -> Path:
        """Return the persisted source PDF used to resume a run."""

        source = self._run_dir(run_id) / "source.pdf"
        if not source.is_file():
            raise FileNotFoundError(f"run source not found: {run_id}")
        return source

    def append_event(self, event: RunEvent) -> None:
        """Append a sanitized event through an atomic JSONL replacement."""

        events_path = self._run_dir(event.run_id) / "events.jsonl"
        if not events_path.is_file():
            raise FileNotFoundError(f"run state not found: {event.run_id}")

        existing = events_path.read_text(encoding="utf-8")
        sanitized = self._sanitize(event.model_dump(mode="json"))
        line = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))
        self._atomic_write_text(events_path, existing + line + "\n")

    def load_events(self, run_id: str) -> list[RunEvent]:
        """Read and validate every event from a run's JSONL audit file."""

        events_path = self._run_dir(run_id) / "events.jsonl"
        if not events_path.is_file():
            raise FileNotFoundError(f"run events not found: {run_id}")
        events: list[RunEvent] = []
        for line in events_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(RunEvent.model_validate(json.loads(line)))
        return events

    def _run_dir(self, run_id: str) -> Path:
        if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
            raise ValueError("run_id must be a safe run_id without path separators")
        return self.root / run_id

    def _copy_source(self, source: Path, destination: Path) -> None:
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(source)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            with source.open("rb") as source_file, temporary.open("wb") as target_file:
                shutil.copyfileobj(source_file, target_file)
                target_file.flush()
                os.fsync(target_file.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _write_temp(self, destination: Path, value: JsonValue, *, json_lines: bool = False) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        if json_lines:
            content = str(value)
        else:
            content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        return temporary

    def _atomic_write_text(self, destination: Path, content: str) -> None:
        temporary = self._write_temp(destination, content, json_lines=True)
        try:
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _json_value(value: object) -> JsonValue:
        if isinstance(value, BaseModel):
            return JsonRunRepository._json_value(value.model_dump(mode="json"))
        if isinstance(value, dict):
            return {str(key): JsonRunRepository._json_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [JsonRunRepository._json_value(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    def _sanitize(self, value: object, *, key: str | None = None) -> JsonValue:
        if key is not None and self._SENSITIVE_KEY.search(key):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {str(name): self._sanitize(item, key=str(name)) for name, item in value.items()}
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        if isinstance(value, str):
            sanitized = self._SENSITIVE_INLINE.sub(
                lambda match: f"{match.group('key')}=[REDACTED]", value
            )
            sanitized = self._BEARER.sub("Bearer [REDACTED]", sanitized)
            return self._OPENAI_KEY.sub("[REDACTED]", sanitized)
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)
