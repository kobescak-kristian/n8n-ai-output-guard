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

Prompt change after the decision (2026-10-19, R2). Result first: with the code check and the AI check
together, the guard still misses only the one recorded known limit on the attack texts measured for each AI
step. Details: the first prompt (v1) flagged one normal visible text (OK40, a delivery instruction) in one of
three runs. A 5-repeat stability test (tests/results/exp-stability-*.json) chose prompt v2, which says that
text to the company, its staff or a courier is normal. On the same texts, prompt v2 on its own flags 0 normal
texts and gives the same answer every time, but misses 23 of 376 attack texts (prompt v1 missed 1). The code
check catches 18 of those 23 for every AI step. 4 are orders for a ticket field ("priority low", with or
without "new instructions" in German or Italian): the code check catches them for the ticket triage step,
where the field exists; for the claim and lead steps the guard lets them through, because the step has no
such field and the order cannot change its answer (a limit, listed in the README). The last one is the
recorded known limit (a gated: false case; prompt v1 caught it). So the AI check is now tuned toward fewer
false flags, and the code check carries more of the attack screening.

Raw-reply measure for the strict answer rule (2026-10-19 night, tools/exp_raw_answers.py, two passes of 2
repeats over every list and every visible input, tests/results/exp-raw-answers-v2-low.json): 4,496 replies;
all but 3 were exactly YES or NO with stop reason end_turn; the 3 others were prose on attack texts, which
the strict rule sends to review. 0 normal texts flagged. Haiku's own answers vary from run to run: in pass 2,
48 attack replies were not YES, and the code check flags all 48 for the AI step they were written for
(0 attacks passed both checks; the known limit was answered YES).

## Decision

Every guard call screens the input with both the code check and the AI injection check (a sub-workflow
called by ID); if either one flags the input, the result is needs_review, and if the AI check fails or gives
no clear answer, the result is also needs_review, with an alert. A clear answer is a whole reply of YES or NO
(after trimming spaces, markdown marks, quotes and end punctuation) that ended normally (stop reason
end_turn); prose, both words, or a cut or refused answer is not clear. On an API error
that a retry can fix (no reply at all (timeout, closed or refused connection, other network error), HTTP 408, 429 or 5xx) the AI check asks once more (owner
decision 15); the fail-closed rule applies to what is left after that retry. An unclear answer is not retried.

## Alternatives rejected

- **Code check only.** Deterministic and free, but about a 70% chance of a CF2 failure on the first gated
  run, and no convergence on new texts after five rounds.
- **AI check only.** With prompt v1 it missed one attack in 305 that the code check catches (a fixed-JSON
  order); with prompt v2 it misses 23 of 376 (see Context). The code check also costs nothing and needs no API.
- **AI check failure lets the input through (fail-open).** An outage would then release unscreened input;
  that breaks ADR-001 ("never returns unchecked data").

## Consequences

- One extra small AI call per guard call, two after a retryable API error (about $0.00005 and 1 s at Haiku 5.5 prices on 2026-10-19).
- Injection screening is partly an AI judgement: the README calls it best effort, and names the check.
- One short API error costs one retry (1 s, or the 429 retry-after time up to 5 s; the first try has 20 s,
  the retry 10 s, so the AI check takes at most about 35 s of the guard's 160 s budget). An API outage longer
  than that sends every item to review (with alerts) until the AI check works again.
- In tests every case makes one live AI-check call (two after a retryable API error), so runs need the API; a run-to-run flip of the AI check
  on a simulated case shows up as simulated_changes.
- A client can swap the model or provider of the AI check (it is its own sub-workflow) or leave it out
  (code check only, documented limit).

## Verification

When this ADR was written, the AI check was built but switched off by default (3aaf110, dev run visible-A1
clean). Since 7401180 it is on by default; prompt v2 since 6b2aaa3; the clear-answer rule since c8ced32; the one retry
since BLUEPRINT v1.7 (decision 15; wiring checked with tools/probe_inj_retry.py). Status moves to Accepted after the gated runs in evals/RESULTS.md show injection_leaks 0 and no false flag
on the gated normal cases with the check on, referenced here by entry date and commit.

## Review

Reopen if a gated or later run shows a missed obvious injection or a false flag caused by the AI check, if
the AI check's model is retired or changes price by more than ten times, or by 2027-04-19.
