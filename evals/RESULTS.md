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

None yet. The guard is not built.
