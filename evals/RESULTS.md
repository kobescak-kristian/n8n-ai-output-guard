# Eval results: n8n AI output guard (Q-119)

Gate and metric definitions: `evals/eval_config.yaml`. Every run is
appended here, pass or fail; entries are never edited or deleted. A run
counts only when its results artifact is committed and the runner
exited with code 0.

Entry format: date | config version | model + version | dataset version
(generator commit, hold-out SHA-256) | score per metric | gate verdict |
miss analysis | changed variables vs previous entry | cost.

## Gate versions

- v3, 2026-10-19: owner decision (BLUEPRINT.md v1.3, decision 11, U1 and U2), before any run. OK01-OK04 and OK07 accept ok or ok_after_retry; live alerts and retries scored against the logged API responses; grading wording clarified; new code metrics fallback_data_exact and null_data_on_review; CASES.md section 3b; 40 visible cases added (119 cases, SHA-256 25459500...). No threshold changed.
- v2, 2026-10-19: owner decision (BLUEPRINT.md section 5, option A). Code checks at 100%; rate claim at least 80%, at most 2 misses, at least 30 live correct cases; 25 live correct cases added (visible set 79 cases, SHA-256 d1b36555...). Replaces v1 (893fec5) before any run.

## Entries

### 2026-10-19 | visible-1 | development run, NOT GATED (P4)
- Config: eval_config.yaml v3 (543ae8a). Workflows: 815509f (pushed with `python workflows/build.py --push`). Model: claude-sonnet-5-5 (effort low, server-side fallback on) for the 35 live cases; mock AI server for the 84 simulated cases.
- Dataset: visible set v3, 119 cases (SHA-256 25459500...). Hold-out not used (sealed). One run, not 3; fix kit not run (P5).
- Runner: `python tests/runner.py --label visible-1` exit 0, 492 s. Scorer: `python tests/score.py tests/results/raw/visible-1.json` exit 0; artifact `tests/results/visible-1.score.json`.
- Scores: unchecked_data_returned 0, caller_crashes 0, injection_leaks 0, untouched_rate 1.0, validator_agreement 1.0, retry_rule_breaks 0, log_complete 1.0, review_complete 1.0, alert_correct 1.0, reviewer_exact 1.0, fallback_data_exact 1.0, null_data_on_review 1.0, status_accuracy_code 1.0; rate cases 30, 30 passed this run.
- Result: development run, not gated (one run, no hold-out). Every metric at its gate threshold; 0 critical failures.
- Miss analysis: no misses. Known limit PI07 (gated: false) reported only.
- Changed variables vs previous entry: first entry.
- Cost: live calls 16,668 input + 5,648 output tokens on claude-sonnet-5-5 ($2 / $10 per million): about $0.09. Slack: every review and alert message returned a ts.

### 2026-10-19 | visible-2 and visible-3 | development runs, NOT GATED
- visible-2: config v3, workflows 64038e3 (first code red-team fixes), 127 visible cases (SHA-256 5f5277de...). Runner exit 0. Every code metric 1.0, 0 critical failures, rate cases 30 of 30. Artifact tests/results/visible-2.score.json.
- visible-3: workflows 2457446 + 11 new visible cases (injection check v3), 138 visible cases (SHA-256 bb6c66a9...). Runner exit 0, scorer exit 0. Every code metric 1.0, 0 critical failures, rate cases 30 of 30 (no live input wrongly flagged), live model claude-sonnet-5-5. Artifact tests/results/visible-3.score.json.
- Changed variables vs visible-1: injection check rewritten twice (code red teams), validator and runner fixes; visible cases added (none changed except U1 earlier). Hold-out not used.
- Fix kit dev run fixkit-dry (51 visible claim cases, 2457446, not gated): BEFORE 13 crashes, 19 invalid rows, 4 rows that should not exist, 15 valid; AFTER 0 crashes, 0 bad rows, 32 valid rows.
