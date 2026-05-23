# Tradeoffs Log

Records approved or unavoidable deviations from the spec. Each entry has a
stable ID so the matrix and design docs can reference it without duplicating
the rationale.

## Format

```
## T-NNN — short title

Date: YYYY-MM-DD
Scope: spec §X.Y or module path
Status: accepted | superseded | reverted

### Decision

What was actually done.

### Why

Why the spec direction was changed or could not be followed verbatim.

### Impact

What downstream behavior, verification, or future work this affects.
```

## Entries

_No tradeoffs recorded for the initial P0 implementation. Spec was followed
as written for everything in [`matrix_implementation.md`](matrix_implementation.md)._
