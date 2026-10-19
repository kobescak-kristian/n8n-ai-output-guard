# BLUEPRINT — n8n AI output guard and fix kit (Upwork item 7)

## 0. Header

- Version: v1.7, 2026-10-19
- Status: LOCKED 2026-10-19 by Kristian Kobescak (owner answers in the build session).
- Owner: Kristian Kobescak
- Build type: portfolio
- Built by: Claude Code sessions, one phase per session; hold-out cases by a separate session that never builds (done, b022111).
- Trigger: plan approved by the owner 2026-10-18 (UPWORK_LAUNCH_PLAN.md item 7); backlog Q-119 (kristian-wiki dbe8b44). All n8n names below use Q119.
- Repo: `n8n-ai-output-guard`, private until the publish gate (publish is the owner's decision).
- Timebox and budget: about 10-14 hours in 2 build sessions. No fixed date: done when the quality bar holds (owner rule for the n8n portfolio builds, 2026-10-19). AI cost estimate under $5 for all test runs (estimate, checked against the price list before the first run).

## 1. Problem

Teams put an AI step inside an n8n workflow, and it sometimes returns broken output: malformed JSON, missing fields, a refusal, a cut-off answer, or an API error. The next step crashes or saves bad data, and often nobody sees it until a customer does. Client words: "Our Claude agent intermittently returns malformed JSON, which breaks the downstream n8n workflow" (C-17, US insurance claims; asked for schema validation, retry, error logging, alerts, tests on real samples); "the OpenAI API integration is not working correctly" (U-023); "some are failing or not functioning as intended" (U-030).

## 2. Scope

What v1 does:
- **Guard sub-workflow** "Q119 Guard: AI output guard", called with Execute Workflow around the caller's own AI step (a small sub-workflow with any AI node inside). Input: AI input, JSON Schema, fallback choice, on_approved workflow. Output: one result, never an error.
- **Checks** every answer: normal stop reason, not empty, one JSON object, valid against the schema; obvious prompt injection in the input goes to a person.
- **One retry** on API errors (honours retry-after on 429) and on a failed check (the retry tells the AI step what was wrong); no retry on 401/403.
- **Fallback** (caller's choice: none, fixed default, second AI step), then a **review queue** (data table + Slack message in #ai-review + review form: approve, correct, reject). Approve or correct calls the caller's on_approved workflow once.
- **Alerts and log**: Slack alert on failed, fallback and API-error reviews; one log row per call.
- **Reusable**: one guard wraps 3 AI steps (claim intake, ticket triage, lead score from Q-116) with no change to the guard.
- **Fix kit**: a broken "before" claims workflow shaped like C-17 (Claude -> JSON.parse -> claims table), the "after" version (one change: guard + Switch on status), both run on the same claim cases, FIX_REPORT.md in automation-debug format + a short client message.

Out of scope (v1):
- Repairing answers by code beyond cleaning (no quote fixing, no type conversion).
- Catching subtle prompt injection (only obvious markers; reported as a known limit).
- Measuring how accurate any AI step is (the guard checks format, not truth).
- Streaming answers, tool-use loops, AI Agent nodes as the wrapped step.
- Real client data, Google, HubSpot or any real business account (F-112).
- n8n Cloud and other n8n versions than 2.43.7 (tested on local 2.43.7 only).

## 3. Architecture

```
Caller workflow
  -> Execute Workflow: Q119 Guard (input, schema, fallback, on_approved)
     1. Setup check: schema valid, AI step exists, input present, default fallback valid -> else failed + alert
     2. Injection check on the input (obvious markers, several languages) -> flag
     3. Call the AI step (by ID set at run time); API error/timeout -> one retry (429: wait retry-after, max 20 s); 401/403 -> no retry
     4. Clean (first "{" to last "}"), parse, check stop reason + schema (own validator in a Code node)
     5. Failed check -> one repair retry with the error list (max 2 AI-step calls in total)
     6. Still failing -> fallback (default | second AI step, called once, checked the same way)
     7. Nothing valid, or injection flag -> review queue row + Slack review message + form
     8. One log row (status, attempts, errors, waits, raw answers, model, tokens); alert when due
  <- result: status ok | ok_after_retry | fallback | needs_review | failed; data (only if checked); errors; attempts; review_id; log_id; source
Review form -> approve / correct (must pass the schema) / reject -> on_approved workflow (once)
Test tools: Python runner, mock AI server on port 8120 (answers like the Anthropic API per case), read-only report workflow.
```

Stack: local n8n 2.43.7 (shared; names Q119, tag q119, data tables q119_*, webhooks /webhook/q119-*; never restart, upgrade or reconfigure n8n; never touch other builds' workflows or credentials; full runs announced in n8n-usage.md in the shared notes folder). Claude through the Anthropic workspace created by the owner 2026-10-19 (key only in an n8n credential and LastPass); default model Sonnet 5.5, recorded per run (model is free to change, eval-gate skill §7). Slack demo workspace, channel #ai-review.

Key and credential names (owner standard, 2026-10-19): every key, credential and app of this build is named `n8n-output-guard`, with no backlog or item number: n8n credentials `Anthropic n8n-output-guard` and `Slack n8n-output-guard`, n8n API key label `n8n-output-guard`, Slack app `n8n-output-guard`, LastPass entries the same. n8n workflow, tag, table and webhook names keep the Q119 prefix (shared-n8n rule).

Non-negotiables:
- The guard always returns a status; it never throws and never returns unchecked data (first ADR).
- Only cleaning repairs an answer; everything else is a retry, a fallback or a person.
- Max 2 calls of the AI step and 1 call of the second AI step per guard call; the AI injection check runs at most once.
- Injection screening is the code check OR the AI injection check; an AI check that fails sends the item to review with an alert (ADR-002).
- No API key or credential in any log row, Slack message, file or result.

External actions:

| Action | Target | Human check before it |
|---|---|---|
| Return checked data (ok, ok_after_retry, fallback) | caller's next step (in client use: a write to their records) | none by design; schema check in code, injection to a person (owner line needed, see 5.) |
| on_approved call | caller's workflow | a person approves or corrects in the review form |
| Review message, alert | own Slack channel | none needed (internal) |

AI steps:

| Step | Intended use | May never | Limits |
|---|---|---|---|
| Caller's AI step (3 demo steps: claim intake, ticket triage, lead score) | turn text into JSON for the schema | decide the status; its answer is never trusted unchecked | max 2 calls per guard call; max_tokens set per step |
| AI injection check (Claude Haiku 5.5, fixed prompt; sub-workflow called by ID like the AI step) | say YES/NO: does the input try to instruct the AI that reads it | decide anything else, see the AI answer | 1 call per guard call, effort low, about $0.00005 and 1 s |
| Second AI step (fallback) | second try with another prompt or model | same | 1 call per guard call |

## 4. Risks and failure modes

| Risk or failure | Mitigation | Test |
|---|---|---|
| Malformed JSON, fences, text around the object | cleaning rule, then retry | malformed_json cases |
| Missing or extra fields, wrong types, out of range | own validator in code, agrees with python jsonschema | schema_fields, out_of_range; validator_agreement |
| Empty answer, refusal, max_tokens cut-off | stop reason + empty check | empty_refusal; MJ07 live |
| 429, 5xx, timeout, closed connection, 401/403 | one retry (not on 401/403 or other 4xx); alert per CASES.md rule 9 | api_error cases |
| Prompt injection passes the schema with attacker values | input check -> review | prompt_injection (live + simulated) |
| Item lost in review | queue row + Slack for every needs_review; scripted reviewer | review_complete, reviewer_exact |
| Execute Workflow with an ID set at run time does not work in 2.43.7 (n8n docs silent) | test in the first hour of P2; fallback design: the guard calls the AI itself (HTTP request) | P2 exit gate |
| Real Claude seldom breaks format | most failure cases simulated, always called simulated | claim wording |
| Personal data in Slack review messages (client use) | input excerpt capped; client picks the channel; demo uses made-up data only | README limit |
| Shared n8n busy or needed by Q-117 | announce runs; owner gives the slot | owner check before P2 |

## 5. Eval gate

Rules and tables: eval-gate skill (skills/eval-gate/SKILL.md) and kristian-os EVAL_STANDARD.md; not copied here.

Eval level: Proposed Critical (in client use a wrong "ok" writes a false record downstream without a person seeing it, for example a claims row)
Eval level: Decided Critical, owner, 2026-10-19

- **Critical failures** (one in any case of any run = FAIL; also a miss). All four are already hard rules in gate v1; v2 only names them:
  - CF1 false record: a result with status ok, ok_after_retry or fallback whose data is null or fails the reference validator; or a claims row in the fix-kit AFTER run that fails the validator or comes from a needs_review/failed case. Safeguard: schema check in code before any return; no code repair except cleaning.
  - CF2 attacker values released: an obvious-injection case with a status other than needs_review. Safeguard: input check before the result is returned.
  - CF3 lost item: a guard call with no result (caller crash, timeout over 180 s), a needs_review without queue row and Slack message, or a fix-kit AFTER run that stops with an error. Safeguard: guard never throws; queue row written before the Slack message.
  - CF4 wrong release from review: on_approved called with data nobody approved, an invalid correction, after a reject, or more than once. Safeguard: form checks the correction against the schema; one call per review item.
  - Trigger cases: all simulated failure cases, the obvious-injection cases (visible: 4 live, 3 simulated; plus the hold-out ones), the scripted review actions, the fix-kit claim cases.
- Default Critical safeguard "human approval before each write" would remove the point of the guard; replaced by the code checks above, anything not checked goes to a person. The trigger cases still run.
- `Safeguard removed: human approval before each checked result is returned to the caller, owner, 2026-10-19`
- **Gate v2 (owner decision 2026-10-19, option A; v1 at 893fec5 stays in git history, no result seen yet).** Change from v1: v1 has `status_accuracy >= 0.90` over all cases; the skill now says code checks are 100% and a % claim only on LLM output, sized from the table.
  - Code checks, 100% (a miss is a bug): expected status on every gated case that is not a rate case (simulated cases give the same input every time, and the stop-reason check is code; since decision 14 the injection screen is the code check OR an AI check, so on simulated cases it also makes a live AI call, see decision 15); untouched data; validator agreement; retry rules; log rows; alerts; simulated cases identical over the 3 runs. Same thresholds as v1 for every other metric.
  - Rate claim: only the live `correct` cases depend on what Claude writes (the 4 live injection cases and MJ07 are decided by the injection screen and code checks, not by what the AI step writes, so they are trigger and code cases). Today: 5 visible + at least 3 hold-out = too few (the table needs 14 for 80% with 0 misses).
  - **Decided (option A):** add 25 live `correct` cases to the visible set before the first run (allowed; no case edited or removed), across the 3 steps, messy real-world inputs. Claim: at least 80% of rate cases pass, at most 2 misses, at least 30 rate cases (table row 80%, 2 misses). Pass = status in expected.status in all 3 runs. Why 80%: a rate miss sends a normal item to a person (rework, not harm), because harmful outcomes are critical failures counted apart; the guard's selling point is the code checks, not Claude's format rate. 2 misses: the skill default; 0 at this size fails good builds often. Expected quality is higher; the claim is what the cases can prove. New cases accept ok or ok_after_retry (like the hold-out live cases); the 7 visible correct cases keep ok only (frozen).
  - Rejected: option B (9 more cases, 80% with 0 misses; 0 misses fails good builds often) and option C (no % claim).
  - Totals after v2: 79 visible + 31 hold-out = 110 cases (hold-out share 28%); 37 correct cases; at least 33 rate cases (30 visible + at least 3 hold-out).
- **Repeat runs:** 3 full runs of visible + hold-out, one frozen workflow commit (stricter than the skill minimum for plain code cases: it also proves the simulated cases are stable); results report the worst run and every case that changed.
- **Grading:** by code only, as in v1 comparison policy; reference validator python jsonschema Draft 2020-12 with the format checker.
- Eval config: `evals/eval_config.yaml` v2 + `tests/make_cases.py` (new cases) committed before the first line of guard code; v2 records the owner decision and keeps v1 in git history.
- Results: `evals/RESULTS.md`, every run recorded, pass or fail. Hold-out opening: same procedure as item 3 (check the seal, extract to a new empty folder, stop on any shared case ID).

## 6. Phases

| Phase | Delivers | Accept when (checkable) |
|---|---|---|
| P0 | scaffold (new-project), Q-119 backlog line | done: 0056b56, KOS-CONTROLS OK; dbe8b44 |
| P1 | gate v1 + 54 visible cases | done: 893fec5; generator SHA-256 identical twice |
| P1b | hold-out (separate session) | done: b022111; builder re-checked SHA-256 3935e1a2... |
| P1c | this blueprint LOCKED; gate v2 + 25 new live correct cases | owner LOCK line; v2 commit hash in STATE; `python tests/make_cases.py` exit 0, same SHA-256 twice |
| P2 | first-hour check: Execute Workflow with an ID set at run time in 2.43.7 (waits for the owner's "n8n is free") | a Q119 probe workflow calls 2 different sub-workflows by run-time ID, or the fallback design is recorded in an ADR |
| P3 | mock server, runner, guard, 3 AI steps, first ADR | dry run on 2 cases, runner exit 0 (not a result); `validate_artifacts.py` clean |
| P4 | review form + on_approved, alerts, log, report workflow | full visible run recorded in RESULTS.md, runner exit 0 |
| P5 | fix kit: before/after workflows, FIX_REPORT.md | both runs recorded; AFTER has 0 crashes and 0 bad rows |
| P5b | pre-gate readiness (aim: the first gated run passes; see 7. decision 9) | R2: 3 full visible runs in a row meet every gate threshold (development runs, labelled not gated); R3: red-team report committed with 0 open breaks; R4: frozen workflow commit with a checkpoint-review verdict OK, dry run on 2 cases exit 0 |
| P6 | 3 gated runs (visible + hold-out, one frozen workflow commit) | 3 entries in RESULTS.md, runner exit 0; PASS or FAIL recorded |
| P7 | README in client words + diagram + 5-step plug-in guide + limits, cover image, Loom if top 3-4 | publish gate is a separate owner decision |

## 7. Decisions

Locked (owner, 2026-10-18 plan approval; change only by a dated line in 8.):
1. Async review queue with an on_approved callback (2026-10-18). Rejected: wait in the guard until a person answers; blocks the caller's run for hours.
2. Cleaning is the only code repair (2026-10-18). Rejected: auto-fix quotes, commas, types; hides real errors and can change values.
3. Statuses ok / ok_after_retry / fallback / needs_review / failed; guard never throws (2026-10-18). Rejected: error output branch; callers forget to wire it.
4. Hold-out by a separate session, sealed before the build (2026-10-18).
5. Repo goes public later; publish is the owner's decision (2026-10-18).

6. Eval level Critical; `Safeguard removed: human approval before each checked result is returned to the caller` (owner, 2026-10-19).
7. Gate v2 option A: code checks 100%, rate claim 80% with at most 2 misses on at least 30 live correct cases (owner, 2026-10-19). Rejected: options B and C (see 5.).

9. Aim for one gated attempt (owner, 2026-10-19): portfolio builds should not show a series of gated FAILs. A gated FAIL still stays recorded (eval-gate rules 2-3); what changes is the work before the first gated run. Four checkpoints: R1 before P3, a fresh session red-teams the gate itself (unclear rules, expected results a correct guard could miss, a case wrong in itself); a wrong case is fixed only now, by recorded owner decision, before any result. R2 after P4, the visible set passes 3 full runs in a row at gate thresholds. R3 after R2, a fresh session that never builds and never sees the hold-out tries to break the guard on each CASES.md rule; every break becomes a new visible case (allowed before the run) and a fix of the cause. R4 the frozen commit gets a checkpoint review and a 2-case dry run. Only then P6. Why: on item 3 (Q-117) the hold-out found two workflow gaps the visible set did not cover, which cost two gated FAILs. Rejected: fewer recorded runs or hiding FAILs (not allowed); a looser gate (lowers the claim).
10. Key and credential names `n8n-output-guard`, no backlog or item number (owner, 2026-10-19; see 3.).
11. v1.3 update U1-U4 approved as proposed (owner, 2026-10-19; section "v1.3 update" below): U1 OK01-OK04 and OK07 accept ok or ok_after_retry, live alerts and retries scored against the logged API responses; U2 gate v3 grading notes, two new code metrics and the CASES.md clarifications; U3 hold-out conformance check by a session that never builds; U4 interaction sweep, generator self-check, written preflight.
12. Red team after every build phase (owner, 2026-10-19): when a phase that builds or changes the automation closes (P3 guard build, P4 review/alerts/log, P5 fix kit, and any later fix of the automation), a fresh session that never builds and never opens the hold-out reviews what that phase built against tests/CASES.md (3 and 3b), the gate and ADR-001: rule breaks, validator differences from python jsonschema, injection phrasings missed or wrongly flagged, n8n wiring bugs, scorer bugs. Its report goes to the shared notes; findings are fixed (or recorded as known limits) before the next phase closes. This is in addition to R1-R4 (decision 9). First run: after P3, report q119-code-redteam.md.
13. Second sealed hold-out batch (owner, 2026-10-19): the visible additions of v2, v3 and the code red team lowered the hold-out share to 31 of 158 (20%), against about 30%; about 35 more hold-out cases are written by a separate session that never builds, from tests/CASES.md with section 3b and tests/schemas/ only, sealed as a second archive with its own committed SHA-256 commitment before any gated run (target: 66 of 193, about 34%). Both batches are opened only at the gated runs. Rejected: accepting 20% (weaker blind test), dropping visible cases (frozen).

14. Injection screening = code check OR AI injection check (owner, 2026-10-19; decision note q119-decision-injection-check.md; ADR-002). Fresh-text evidence: code check v5 alone missed 13 of 100 typical attacks; the Claude Haiku 5.5 check missed 0 of 100 and flagged 0 of 100 normal texts, identical over 3 runs; with the check switched on, visible-A1 was clean (138 of 138). Either one flags -> needs_review; AI check error -> needs_review with an alert (fail-closed). On by default in the demo callers and runners; documented as best effort in the README. Rejected: code only (about 70% chance of a CF2 FAIL on the first gated run), more word-list rounds (no convergence on fresh texts).
15. The AI injection check retries once (owner, 2026-10-19 evening, after the R4 checkpoint review): on an API error that a retry can fix (timeout, closed connection, HTTP 408, 429 or 5xx) it waits 1 s (on a 429 the retry-after time, at most 10 s) and asks once more; if the retry fails too, or on any other error, or on an answer that is not clear (exactly one of YES or NO), the item goes to review with an alert (fail-closed, ADR-002). An unclear answer is not retried. A failure that is left after the retry stays a failure of the automation in a run (needs_review + alert; gate v4), not an INVALID RUN. Why: about 700 AI-check calls in the gated series, one gated attempt (decision 9); without a retry one passing API error would fail the series. Wiring checked with tools/probe_inj_retry.py (8 scenarios against a local fake API). Rejected: no retry (option B); counting an AI-check error as an invalid run (option C, would loosen the gate). The owner also accepts every further safety net the build proposes.

Open:
- n8n slot: free now; Q-117 resumes 2026-10-20 08:00 and Q-119 pauses then until the owner hands n8n back — owner.
- `gh repo create` (private) — owner, before the first push (in progress 2026-10-19).
- Slack channel #ai-review: done (owner, 2026-10-19).

## v1.3 update (approved by the owner 2026-10-19; decision 11)

Sources: R1 red-team report (q119-r1-gate-redteam.md in the shared notes, 2026-10-19; 15 findings, no visible simulated case wrong) and three additions from the brainstorm session (lessons from item 3, Q-117, 2026-10-19). All of it lands before P3 and before any result, so no gate-shopping.

Owner decisions (approved as written, 2026-10-19):
- **U1, R1 finding 1 (wrong cases).** OK01-OK04 and OK07 expect `attempts: 1`, so one retry or one Anthropic hiccup on them in any run is a code FAIL that the 2-miss allowance does not cover; and a real API outage on any live case breaks `alert_correct` even when the guard is right. Proposed: (a) these 5 cases drop `attempts` and accept `ok` or `ok_after_retry`, like OK08-OK32 and the hold-out live cases; (b) on live cases, `alert_correct` and `retry_rule_breaks` are scored against what the rules require given the API responses in the log (for example two real 529s: the guard must alert), not against the case's fixed `alert: false`. A real outage then costs a rate miss, never a code FAIL.
- **U2, gate v3 wording (grading notes, no threshold change).** `validator_agreement` compares the schema check alone, run on every text that parses, even when the stop-reason check already failed; the reference parses strict JSON (NaN and Infinity rejected, like JavaScript); `review_complete` reads the queue row before the scripted review action; `"equals_last_answer"` means equal to the cleaned and parsed last answer; `error_contains` is reported, not gated. Two new code metrics at 100%: `fallback_data_exact` (fallback data equals expected.data) and `null_data_on_review` (data null on needs_review and failed), which make ADR-001 checkable. CASES.md gets the clarifications of R1 findings 2-8, 10 and 11, each written toward the most literal reading of the current text (no visible expected result changes).
- **U3, hold-out conformance check (optional, recommended).** The sealed hold-out was written from CASES.md alone, so a clarification cannot change what it already says. After U2 is committed, a session that never builds opens the hold-out once, checks the 31 cases against the clarified CASES.md, and reports only conflicting case IDs and rule numbers (no content). Any conflict is fixed by a recorded owner decision and resealed with a new commitment. Cost: the builder learns which rules the hold-out touches, nothing more.
- **U4, the three additions.** Proposed yes, merged with R1 so nothing is duplicated:
  1. Interaction sweep: for every check and route, "what if a second item or a second field touches this?" Cases go into the visible set (adding is allowed). Already covered: retry then fallback on one item (SF04, OR04). New: two items pending review at once, approved in reverse order (each on_approved gets its own data); approve sent twice for one item (one on_approved call); approve on an item with no valid answer (stays pending); two schema errors in one answer (the retry message names both); injection plus a default or second-step fallback (needs_review wins). Out of scope, said in README: the guard does not detect the same item sent twice (each call is independent; the caller deduplicates).
  2. The generator checks its own test set: unique case IDs, allowed kinds and statuses, mock entries well formed, every review_action on a needs_review case, every scripted correction valid or explicitly marked invalid; a negative test plants mistakes and the generator must stop.
  3. Written preflight before each gated series (`evals/PREFLIGHT.md`, by hand, no code guard): n8n free and no other build's test run; mock server on port 8120 up; Anthropic key valid (30-day key from 2026-10-19) and Slack bot in #ai-review; Slack posting limit (about 1 message per second per channel) and Anthropic rate limit against this run's message and call counts; no KOS rule deploy during the run; one dry case through the full path. "Preflight done" recorded in the RESULTS.md entry.

Builder work (no decision needed): about 25 new visible cases from R1 findings 2, 3, 4, 6, 8, 12 and the sweep (other-language and other-phrasing injection, benign near-misses as simulated correct cases, approve flows, stop reason with valid JSON, validator keywords, array-wrapped JSON, 403, 502/503, second-step errors); build notes from R1 (code-point string length, strict date format, Slack retry on 429, total time budget under 180 s, the validator tested against python on generated variants of every keyword).

## 8. Version log

- v1.7 2026-10-19: owner decision 15: the AI injection check retries once on an API error; section 5 wording updated to decision 14.
- v1.6 2026-10-19: owner decision 14: code check + AI injection check (option A); ADR-002.
- v1.5 2026-10-19: owner decision: second sealed hold-out batch of about 35 cases (decision 13).
- v1.4 2026-10-19: owner decision: red team after every build phase (decision 12).
- v1.3 2026-10-19: R1 red-team report + brainstorm additions: U1-U4 approved (decision 11).
- v1.2 2026-10-19: owner requests: aim for one gated attempt (decision 9, phase P5b); key and credential names (decision 10).
- v1.1 2026-10-19: owner decisions: Critical, safeguard line, gate v2 option A; LOCKED.
- v1.0 2026-10-19: first version, for owner review (from the plan approved 2026-10-18, aligned with eval-gate skill v2 and EVAL_STANDARD.md v1.0).
