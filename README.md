# Automation Asset Servicing

Local LLM-assisted extraction of information from investment fund regulations.

## Development

```powershell
uv sync --group dev
uv run pytest -m "unit or contract" -q
uv run pytest -m "not needs_api" -q
uv run ruff format --check .
uv run ruff check .
uv run mypy src
```

The `needs_api` marker is reserved for opt-in tests that require a live LLM
credential. The canonical gates and their intended use are maintained in
`.specs/features/regulation-extraction/tasks.md`.
