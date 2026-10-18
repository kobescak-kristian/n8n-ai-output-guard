# AGENTS.md — n8n-ai-output-guard

Agent-first context router. It points to where repository truth lives.
It is not itself evidence of project state: cite the source it routes
to, never this file.

## Repository purpose

A reusable n8n sub-workflow that wraps any AI step: it checks every AI answer against a fixed format, retries once, uses a fallback, sends what still fails to a person in Slack, alerts on errors and logs every call; it ships with one before/after fix of a broken workflow. Human overview: `README.md`.

## Authority and conflict handling

| Question | Canonical source |
|---|---|
| What the system is and claims | `README.md` |
| Why a design decision was made | `adr/` |
| Build status, open decisions, change history | `STATE.md` |
| What the implementation actually does | source, tests and configuration inspected together |

When sources disagree: an adopted ADR outranks the text it amends;
documents state intent, implementation and tests state behaviour, and a
gap between them is a finding to surface, not something to silently
reconcile; `STATE.md` is the status surface; if canonical sources
conflict, stop and ask the owner.

## Task routing

Starting points, not exhaustive reading lists.

| Task class | Start here |
|---|---|
| Understand or explain the system | `README.md` |
| Current status or open decisions | `STATE.md` |
| Test cases, expected results, behaviour rules | `tests/CASES.md`, `tests/make_cases.py`, `tests/cases/` |
| Eval gate and recorded runs | `evals/eval_config.yaml`, `evals/RESULTS.md` |
| Documentation / README / ADR work | the artifact itself; `.githooks/validate_artifacts.py` for enforced structure |

## Always-on constraints

- Tier 0 artifacts are README, ADRs, LICENSE, and AGENTS.md.
  STATE.md is separately required by the build-repo STATE rule.
  Do not create SYSTEM_WALKTHROUGH.md, CHANGELOG.md, RUNBOOK.md or
  other trigger-gated artifacts without an instruction citing the
  trigger. ADRs are for genuine material decisions only, with at least
  one required. Version log lives in README.
- Done means the acceptance condition is demonstrated, not that a file
  exists.
- No secrets or machine-local absolute paths in tracked files.
- Never rewrite git history.
- The eval gate is fixed before the build; never change a case, expected
  result or threshold to make a run pass (new dated version only).
- The hold-out cases are written by a separate session. A building
  session never opens the q119-holdout folder before the final run.
- This file is an instruction surface, not a security boundary.

## Verification

- Tier 0 structure: `python .githooks/validate_artifacts.py .`
- Test cases consistent with the reference validator: `python tests/make_cases.py`
