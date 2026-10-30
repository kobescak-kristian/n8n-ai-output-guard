# ADR-001: The guard always returns a status; it never throws and never returns unchecked data

**Status:** Accepted (2026-10-20, P6 gated runs on 9107ff3)
Date: 2026-10-19
Author: Kristian Kobescak; drafted by a Claude Code build session

## Context

The guard is an n8n sub-workflow that wraps a caller's AI step (BLUEPRINT.md
sections 2-3). The client problem it answers is a workflow that crashes or
saves bad data when the AI answer is broken (a real insurance claims job post). If the guard
itself can throw an error, the caller's run stops and the item is lost, which
is the same failure in a new place. If the guard can return data that did not
pass the checks, the caller writes a false record. The eval gate is Critical
(Kristian, 2026-10-19) and names both as critical failures: CF3 lost item and CF1
false record (`evals/eval_config.yaml` v2).

## Decision

Every guard call ends with exactly one result object with a `status` of `ok`,
`ok_after_retry`, `fallback`, `needs_review` or `failed`, and `data` is
non-null only when it passed the schema check in that call.

## Alternatives rejected

- **Throw an error on failure and let the caller use n8n's error output or an
  error workflow.** Rejected: callers often forget to wire the error branch,
  and an unwired error stops the run; the item is lost (CF3).
- **Return the best-effort answer with a warning flag.** Rejected: the next
  step will use the data whatever the flag says; that is how false records
  are written (CF1).
- **Repair answers in code (fix quotes, trailing commas, types) so more pass.**
  Rejected: repairs can change values without anyone noticing; only the
  cleaning rule (first `{` to last `}`) is allowed (tests/CASES.md rule 3).

## Consequences

- The caller needs one Switch node on `status`; that is the whole integration.
- Every failure path (API error, bad setup, fallback failure, injection flag)
  must end in a result, a log row and, where due, a review row or an alert.
  This costs more build work in the guard than letting errors bubble up.
- n8n can still fail outside the guard's control (the n8n process stops, the
  execution is killed). The guard cannot return a status then; the README
  states this as a limit.
- `failed` is a real status for broken caller setup, not an error: the caller
  must handle it like `needs_review` without a review row.

## Verification

Unbuilt. Status moves to Accepted only after a recorded full run in
`evals/RESULTS.md` with `caller_crashes == 0` and `unchecked_data_returned == 0`
(gate v2 metrics), referenced here by entry date and commit.

Accepted 2026-10-20: `evals/RESULTS.md`, entries "2026-10-20 | P6 gated series" and
"2026-10-20 | P6 verdict", frozen commit 9107ff3: in all 3 gated runs (231 cases each)
`caller_crashes` 0 and `unchecked_data_returned` 0.

## Review

Reopen if any recorded run shows a guard call with no result or with
unchecked data returned, or when the guard is ported to an n8n version other
than 2.43.7. Review by 2027-04-19 otherwise.
