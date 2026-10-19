# Test cases: format and the behaviour they encode

Written before the build (eval gate: `evals/eval_config.yaml`). The guard
is built to these rules, never the reverse. A separate session writes the
hold-out cases from this file alone.

## 1. What is tested

The guard is an n8n sub-workflow. A calling workflow gives it an AI input,
a JSON Schema and a fallback choice. The guard calls the caller's **AI
step** (a small sub-workflow with the real AI node inside), checks the
answer, and returns one result. The tests call the guard through a test
caller workflow and read the result, the guard log, the review queue and
the Slack message IDs through a read-only report workflow.

Three AI steps are used, each with its own schema in `tests/schemas/`:

| step | schema | what the AI reads |
|---|---|---|
| `claim_intake` | `claim_intake.json` | an insurance claim e-mail (shape of research post C-17) |
| `ticket_triage` | `ticket_triage.json` | one customer support message |
| `lead_score` | `lead_score.json` | a lead form (the Q-116 lead qualifier answer) |

## 2. Result statuses

| status | meaning | `data` |
|---|---|---|
| `ok` | first answer passed | the checked answer |
| `ok_after_retry` | first try failed, the one retry passed | the checked answer |
| `fallback` | both tries failed, the fallback gave a valid answer | the fallback answer |
| `needs_review` | nothing valid; the item is in the review queue for a person | null |
| `failed` | the caller's setup is broken; the AI step is not called | null |

## 3. Behaviour rules

1. **At most 2 calls of the AI step per guard call** (the first try + one
   retry), whatever went wrong. A second AI step used as fallback is
   called at most once and is counted separately.
2. **Retry once** after: server error (500, 502, 503, 529), rate limit
   (429; wait at least the `retry-after` seconds, at most 20), timeout,
   closed connection, or an answer that fails the checks. The retry for
   a bad answer tells the AI step what was wrong, in plain words.
   **No retry** after 401 or 403 (API key problem): straight to the
   fallback or review, with an alert.
3. **Cleaning is the only repair.** If the text is not valid JSON as it
   is, the guard takes the part from the first `{` to the last `}` and
   tries again (this removes ```json fences and words around one
   object). Nothing else is fixed by code: no quote fixing, no trailing
   comma removal, no type conversion.
4. **Checks** on every answer: stop reason must be a normal end (not
   `refusal`, not `max_tokens`); text not empty; one JSON object; valid
   against the schema (type, required, enum, minimum/maximum, length,
   pattern, `format: date`, arrays, no extra fields when
   `additionalProperties` is false).
5. **Passed answers are returned untouched:** `data` equals the parsed
   answer exactly (same keys, values, number values, text byte for byte).
6. **Prompt injection in the input:** if the input has obvious
   instructions aimed at the AI (for example "ignore previous
   instructions", a fake "SYSTEM:" line, "return the following JSON",
   in English or other languages), the result is `needs_review` even
   when the answer passes the schema. Normal customer phrases like
   "please ignore my previous email" must not trigger this.
7. **Fallback** (caller's choice): `none`, `default` (a fixed value,
   checked against the schema at the start), or `second_step` (another
   AI step, called once, checked the same way). If the fallback also
   fails: `needs_review`.
8. **Nothing is lost:** every `needs_review` result has a review queue
   row (status `pending`) and a Slack review message. A reviewer can
   approve (only when there is a valid answer), correct (the corrected
   answer must pass the schema, or the item stays pending), or reject.
   After approve or correct, the guard calls the caller's
   `on_approved` workflow once with the final data.
9. **Alerts** (Slack alert message): when the status is `failed` or
   `fallback`, and when an API error (including 401/403) is the reason
   for `needs_review`. No alert for `ok` or `ok_after_retry` (logged
   only). Review messages are separate from alerts.
10. **Log:** exactly one log row per guard call, with the returned
    status, attempts, error list, wait time, timing, and the raw answer
    of every attempt.
11. **Setup check first:** missing or invalid schema, unknown AI step,
    missing AI input, or a default fallback that fails the schema gives
    `failed` with a clear error and an alert, without calling the AI.

## 3b. Clarifications (gate v3, owner decision 2026-10-19, BLUEPRINT.md v1.3 U2)

The rules above stay word for word. These lines say how they are read,
each toward the most literal reading of the text. They change no visible
expected result (source: R1 red-team report, 2026-10-19; the line "Rule 6, how
the guard screens" comes from owner decision 14, gate v4).

- **Rule 1, attempts.** `attempts` = calls of the main AI step, including
  calls that ended in an HTTP error, a timeout or a closed connection. The
  second AI step is logged in its own field and never counted in `attempts`.
- **Rule 2, waits.** A `retry-after` above 20 seconds: wait 20 seconds, then
  retry. A 429 without `retry-after`: wait 1 second, then retry.
- **Rule 2, which errors are retried.** Every 5xx (500, 502, 503, 504, 529
  and others), 408, 429, a timeout and a closed connection are retried once.
  Every other 4xx (400, 404, 413, 422 ...) is treated like 401/403: no
  retry, straight to the fallback or review, with an alert.
- **Rule 2, the retry.** Same model, same settings, same max_tokens; for a
  failed check only the plain-words error list is added.
- **Rule 3, not an object.** Text that is valid JSON but not one object (an
  array, a string, a number) is a failed check. Cleaning happens only when
  the text does not parse as it is. JSON is parsed strictly: `NaN`,
  `Infinity` and `-Infinity` are not JSON.
- **Rule 4, order of checks.** A stop reason other than a normal end fails
  the check even when the text is complete, valid JSON. Whenever the text
  parses, the schema check still runs and its verdict is logged.
- **Rule 4, string length.** `minLength` and `maxLength` count characters
  (Unicode code points: one emoji is one character). `format: date` is
  `YYYY-MM-DD` and a real calendar day.
- **Rule 6, what counts as obvious.** In any language: words telling the AI
  to ignore, disregard or forget earlier instructions or rules; "new
  instructions"; "you are now ..." or a mode switch ("developer mode",
  "admin mode"); a role line or tag that gives the AI orders (`SYSTEM:`,
  `Assistant:`, `### Instruction`, `[INST]`, `</system>`, an HTML comment
  addressed to the assistant); a request to return fixed JSON or set field
  values. Normal text is not flagged: "please ignore my previous email",
  "System: Windows 11", "please disregard the attached invoice", "return
  the following items", "act as ... as soon as possible".
- **Rule 6, injection wins.** On a flagged input the main AI step runs as
  usual (first try and one retry, so the reviewer sees an answer), but no
  fallback is used and the second AI step is not called. The result is
  `needs_review` whatever the fallback setting. Only a setup `failed` wins
  over it. No alert for the injection itself (rule 9).
- **Rule 6, how the guard screens (gate v4, owner decision 2026-10-19).** The
  input is screened by a code check and by an AI injection check (a small
  AI step that answers YES or NO). Either one flagging is enough. On an API
  error a retry can fix, the AI check asks once more (decision 15). If the AI
  check still fails (API error, no clear answer), the item goes to review
  with an alert. Expected results of the cases do not change: obvious injections
  are needs_review, normal text is not flagged.
- **Rule 7, the second AI step.** Its answer goes through the same cleaning
  and checks. It is called once and never retried; an HTTP error or a
  timeout of the second step gives `needs_review`.
- **Rule 8, approve.** Approve releases the last answer of the main AI step
  that passed every check (for example an injection-flagged item whose
  answer passed). If no answer passed, approve is refused: the item stays
  pending and on_approved is not called. Once an item is approved,
  corrected or rejected, a second action on it is refused: on_approved is
  called at most once per item.
- **Rule 9, alert for needs_review.** Alert when the last call (of the main
  AI step, or of the second AI step when it ran last) ended in an HTTP
  error, a timeout or a closed connection, or when any call returned a 4xx
  other than 408 and 429. No alert when the reason is bad answers only or
  an injection flag. An AI injection check that fails (API error, no clear
  answer) does alert (gate v4, the line "Rule 6, how the guard screens").
- **Time budget.** A guard call returns within 170 seconds in total: the
  guard plans its calls with 160 seconds and keeps 10 seconds for n8n; the
  AI injection check (at most about 35 seconds with its retry) and every AI
  call count in that time, and the second AI step gets only the time left.
  (CF3 counts a call over 180 seconds as lost.) A timed-out call counts as a
  timeout (rule 2).
- **Fix kit.** It runs once per gated run on every claim_intake case with
  the case's own options, fallback and review action. Setup cases run
  through the AFTER workflow's guard call with the same broken setup
  (expected: no claims row, no crash). Live claim cases call Claude again.

## 4. Case format (`tests/cases/*.json`)

```json
{
  "id": "SF02",
  "kind": "schema_fields",
  "step": "claim_intake",
  "source": "simulated",
  "input": {"text": "<the e-mail, ticket or form text>"},
  "mock": [ {"http": 200, "stop_reason": "end_turn", "text": "<raw answer of try 1>"},
            {"http": 200, "stop_reason": "end_turn", "text": "<raw answer of try 2>"} ],
  "fallback": {"mode": "none"},
  "options": {"timeout_seconds": 8},
  "review_action": {"action": "correct", "data": { }},
  "obvious_injection": true,
  "gated": true,
  "expected": {
    "status": ["needs_review"],
    "attempts": 2,
    "alert": false,
    "review_row": true,
    "data": null,
    "error_contains": ["key"],
    "min_wait_seconds": 3
  },
  "note": "one line: what this case tests"
}
```

Field rules:
- `kind`: `malformed_json`, `schema_fields`, `out_of_range`,
  `empty_refusal`, `api_error`, `prompt_injection`, `correct`, `setup`.
- `source`: `simulated` (answers come from the mock AI server, `mock`
  required) or `live` (real Claude; no `mock`).
- `mock`: one entry per try, in order. Entry shapes:
  `{"http": 200, "stop_reason": "end_turn" | "refusal" | "max_tokens", "text": "..." | null}`,
  `{"http": 429, "retry_after": 3}`, `{"http": 500}` (any error code),
  `{"delay_seconds": 30}` (answer comes too late), `{"close_connection": true}`.
- `fallback`: `{"mode": "none"}`, `{"mode": "default", "value": {...}}`,
  or `{"mode": "second_step", "mock": [<one entry>]}` (simulated only).
- `options`: `timeout_seconds` (default 60), `max_tokens` (live only),
  `setup_problem` (setup cases: `schema_missing`, `schema_invalid`,
  `ai_step_unknown`, `fallback_invalid`, `input_missing`).
- `review_action`: the scripted reviewer action for a `needs_review`
  case: `approve`, `reject`, or `correct` with `data`.
- `obvious_injection`: injection cases only. `true` = a person would
  clearly see an instruction aimed at the AI (gated: must be
  `needs_review`). `false` = subtle; reported, not gated.
- `gated: false`: a known-limit case, reported but not in the gate.
- `expected.status`: the statuses that count as correct (usually one).
- `expected.data`: an exact object, `"equals_last_answer"` (live: the
  data must equal the last raw answer, parsed), or null.
- `expected.attempts`, `error_contains`, `min_wait_seconds`: optional.
  `error_contains` is reported, not gated (gate v3).
- `expected.data: "equals_last_answer"` means: equal to the cleaned and
  parsed last answer of the main AI step.
- `review_action.repeat` (optional, 1 or 2): 2 = the same action is
  submitted twice; the second must be refused (section 3b, rule 8).
- Mock server: `{"delay_seconds": N}` holds the request for N seconds and
  then closes the connection with no answer. A call beyond the end of the
  `mock` list gets HTTP 500 and an "over-call" line in the mock log.
- Runner: all scripted review actions of a run are submitted after every
  guard call of that run has returned, in reverse case order, so many
  items wait in the queue at once.

## 5. Files

- `tests/make_cases.py` builds `tests/cases/visible.json` (deterministic)
  and checks every expected result against the reference validator
  (python `jsonschema`, Draft 2020-12 with the format checker).
- Hold-out cases are not in this repository until the final run; see
  `evals/eval_config.yaml`, `dataset.hold_out_set`.
