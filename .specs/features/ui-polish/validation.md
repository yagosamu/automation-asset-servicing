# UI Polish Validation

**Result**: PASS
**Date**: 2026-09-30
**Spec**: `.specs/features/ui-polish/spec.md`
**Diff range**: `0b08134..28424ba`
**Verifier**: independent sub-agent (author ≠ verifier)

## Spec-anchored check

| Requirement | Evidence | Result |
| --- | --- | --- |
| UIP-01 | `tests/ui/test_document_location_ui.py:117`-`126` asserts the executive title and four labeled stages; `tests/ui/test_complete_journey.py:224` asserts stage 4 is active. | ✅ |
| UIP-02 | `tests/ui/test_document_location_ui.py:129` asserts the initial selection/location guidance. | ✅ |
| UIP-03 | `tests/ui/test_complete_journey.py:214`-`228` asserts immediate active results and the collapsed document/location section. | ✅ |
| UIP-04 | `tests/ui/test_document_location_ui.py:142`-`144` asserts visible location progress; `tests/ui/test_complete_journey.py:372`-`382` asserts persistent error state, retry guidance, and successful retry without recreating the run. | ✅ |
| UIP-05 | `tests/ui/test_delivery_ui.py:181`-`195` asserts numeric confidence, `Média`, and `Não avaliada`; `tests/ui/test_complete_journey.py:218` asserts `Média`/`Alta`; `tests/ui/test_delivery_ui.py:312`-`315` asserts the shared 0.85/0.50 bands including `Baixa`. | ✅ |
| UIP-06 | `tests/ui/test_complete_journey.py:219`-`223` asserts variables, pending items, approvals, and total duration; render order is fixed at `src/asset_servicing/ui/app.py:778`-`790`. | ✅ |
| UIP-07 | `tests/ui/test_delivery_ui.py:303`-`335` asserts a collapsed operational section retaining durations, calls, retries, usage, models, and prompt versions. | ✅ |

## Edge cases

| Edge case | Evidence | Result |
| --- | --- | --- |
| Selecting another regulation resets the visible flow without deleting persistence | `tests/ui/test_complete_journey.py:345`-`360` | ✅ |
| No operational events renders `0,00 s` | Empty-event aggregation yields zero at `src/asset_servicing/application/delivery_service.py:141`; UI formatting/rendering is at `src/asset_servicing/ui/app.py:686` and `src/asset_servicing/ui/app.py:724`-`725`. | ✅ |
| Missing validation is visibly unrated | `tests/ui/test_delivery_ui.py:187`-`195` | ✅ |

## Focused gate

- `uv run pytest tests/ui/test_document_location_ui.py tests/ui/test_complete_journey.py tests/ui/test_delivery_ui.py -q`: **28 passed**.
- `uv run ruff check src/asset_servicing/ui tests/ui/test_document_location_ui.py tests/ui/test_complete_journey.py tests/ui/test_delivery_ui.py`: passed.
- `uv run mypy src/asset_servicing/ui`: passed (3 source files).
- `git diff --check 0b08134..28424ba`: passed.

**Explicit limitation**: per user instruction, this is a focused UI gate only. The global Build/test suite was not run, so the verdict does not claim repository-wide regression coverage. The zero-event duration edge is backed by direct code-path evidence but has no dedicated assertion in the three focused test files.

## Discrimination sensor

| Mutation | Evidence | Result |
| --- | --- | --- |
| Active completed run incorrectly selected stage 1 instead of stage 4 at `src/asset_servicing/ui/app.py:348` | Killed by `tests/ui/test_complete_journey.py:224`. | ✅ Killed |
| Medium confidence incorrectly rendered as `Baixa` at `src/asset_servicing/ui/app.py:371` | Killed by `tests/ui/test_delivery_ui.py:184`. | ✅ Killed |

The two mutations ran in a detached temporary worktree, which was removed. The real worktree porcelain matched the clean pre-sensor baseline before this report was added.

## Summary

All seven acceptance criteria and three listed edge cases match the implementation. The focused gate passed, and both required behavior mutations were detected. Subject to the explicit focused-gate limitation above, the feature is ready.
