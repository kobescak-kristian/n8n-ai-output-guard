# ADR-002: Injection screening is a code check OR an AI check, and fails closed

**Status:** Proposed (2026-10-19)
Date: 2026-10-19
Author: Kristian Kobescak (owner decision 14); drafted by a Claude Code build session

## Context

Rule 6 (tests/CASES.md) sends any input with an obvious instruction aimed at the AI to a person, "in English
or other languages". The eval level is Critical: one obvious injection that is not sent to review (CF2) fails
the gate. The first design was a code check (word families in about 25 languages). Five independent red teams
measured it on texts it had never seen: after each rebuild the next fresh batch still found gaps, and the
last measure on 100 typical attacks was 13 missed (v5). A Claude Haiku 5.5 check with one fixed, untuned
prompt missed 0 of the same 100 attacks and flagged 0 of 100 normal texts, with the same answers over three
runs (decision note q119-decision-injection-check.md in the shared notes; tests/results/exp-classifier-*.json).

Prompt change after the decision (2026-10-19, R2): that first prompt (v1) flagged one normal visible text
(OK40, a delivery instruction) in one of three runs. A 5-repeat stability test
(tests/results/exp-stability-*.json) chose prompt v2, which states that text to the company, its staff or a
courier is normal. Measured on the same texts: prompt v2 on its own flags 0 normal texts and gives the same
answer every time, but misses 23 of 376 attack texts (prompt v1 missed 1). With the code check alongside,
the guard misses one of the 376: the recorded known limit (a gated: false case; prompt v1 caught it). 18 of
the other 22 are caught by the code check for every AI step, and 4 are field orders ("priority low") that it
catches for the AI step whose fields they name. So the AI check is now tuned
toward fewer false flags, and the code check carries more of the attack screening.

## Decision

Every guard call screens the input with both the code check and the AI injection check (a sub-workflow
called by ID); if either one flags the input, the result is needs_review, and if the AI check fails or gives
no clear answer, the result is also needs_review, with an alert. A clear answer is YES or NO as a whole word,
with only one of the two in the answer; an answer with both or with neither is not clear.

## Alternatives rejected

- **Code check only.** Deterministic and free, but about a 70% chance of a CF2 failure on the first gated
  run, and no convergence on new texts after five rounds.
- **AI check only.** It missed one attack in 305 that the code check catches (a fixed-JSON order); the code
  check also costs nothing and needs no API.
- **AI check failure lets the input through (fail-open).** An outage would then release unscreened input;
  that breaks ADR-001 ("never returns unchecked data").

## Consequences

- One extra small AI call per guard call (about $0.00005 and 1 s at Haiku 5.5 prices on 2026-10-19).
- Injection screening is partly an AI judgement: the README calls it best effort, and names the check.
- An API outage sends every item to review (with alerts) until the AI check works again.
- In tests every case makes one live AI-check call, so runs need the API; a run-to-run flip of the AI check
  on a simulated case shows up as simulated_changes.
- A client can swap the model or provider of the AI check (it is its own sub-workflow) or leave it out
  (code check only, documented limit).

## Verification

When this ADR was written, the AI check was built but switched off by default (3aaf110, dev run visible-A1
clean). Since 7401180 it is on by default; prompt v2 since 6b2aaa3; the clear-answer rule above since the
R4 fix commit. Status moves to Accepted after the gated runs in evals/RESULTS.md show injection_leaks 0 and no false flag
on the gated normal cases with the check on, referenced here by entry date and commit.

## Review

Reopen if a gated or later run shows a missed obvious injection or a false flag caused by the AI check, if
the AI check's model is retired or changes price by more than ten times, or by 2027-04-19.
