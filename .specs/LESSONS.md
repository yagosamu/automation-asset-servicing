# LESSONS - auto-maintained by scripts/lessons.py

> Machine-owned. Do NOT hand-edit. Changes are overwritten on the next `lessons.py` write.
> Canonical state lives in `.specs/lessons.json`. Edit lessons only via the script.
> promote_threshold=2 distinct features · window_days=45 · quarantine_threshold=2

## Confirmed (load these at Specify/Design)

Corroborated across multiple features. Safe to apply as guidance.

_none_

## Candidates (under observation - do NOT load as guidance yet)

Seen once or not yet corroborated. Tracked, not trusted.

### L-001 - Assert every required payload field against its expected value, including injected timestamps
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `pipeline-tests` · harmful: 0
- features: regulation-extraction
- evidence: ASET-01 (pipeline-tests)
- last seen: 2026-09-29T18:26:59Z

### L-002 - Test prompt constraints with complete semantic clauses or behavioral fixtures, not isolated keywords.
- signal: `surviving_mutant` · recurrence: 1 feature(s) · scope: `prompts-evals` · harmful: 0
- features: regulation-extraction
- evidence: validation.md M1/M3 (prompts-evals)
- last seen: 2026-09-30T11:22:41Z

## Quarantined (failed when applied - ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_
