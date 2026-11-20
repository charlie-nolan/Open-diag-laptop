# ADR-0002: Simulation harness and blind grader (tests/sim/)

Status: Accepted (recorded 2026-11-20)

## Context

These decisions were written as code comments next to the code they explain. Comments are banned
(ADR-0001), so they are kept here. Each entry names the file and the function or class it applies to;
search the file for that name. When the code changes, update or remove the entry in the same change.

## Decisions

### `tests/sim/blind_grade.py`

- `_claude_env`: A real token, not a pasted command line.
- E.g. the CLI login expired: stop, don't skip all.

### `tests/sim/run_sim.py`

- Keep the sim out of the deck's own trace logs.
- Intake exactly as typed: the app's own load/store turns these into the case.
