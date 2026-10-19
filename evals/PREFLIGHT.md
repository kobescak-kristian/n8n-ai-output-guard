# Preflight before each gated series

Done by hand before the first of the 3 gated runs (and again if a series is
restarted). Not a code guard. Write "preflight done <date> <time>" and any
item that needed action into the RESULTS.md entry of the first run.
Why: item 3 (n8n-ai-invoice-extractor) lost gated runs to a Gmail sending
limit (F-122) and a Sheets rate limit that a check before the run would
have caught. Source: BLUEPRINT.md v1.3, U4.3.

| # | Check | How | OK when |
|---|---|---|---|
| 1 | n8n is ours for the whole series | owner says so; shared notes `n8n-usage.md` | no other build's test run is planned in the window; our line is added there |
| 2 | Mock AI server up | `GET http://localhost:8120/health` | HTTP 200 |
| 3 | Anthropic credential valid | one live call through the AI step | answer received; key expiry date (30-day key from 2026-10-19) is after the series ends |
| 4 | Slack bot can post | one test message to #ai-review through `Slack n8n-output-guard` | message ts returned; bot is a member of #ai-review |
| 5 | Slack posting limit | count review messages + alerts this series will post (from the case list) | runner spacing keeps it at or under about 1 message per second per channel; guard retries Slack 429 with Retry-After |
| 6 | Anthropic rate limit | live calls this series will make (live cases x up to 2 calls x 3 runs) | below the workspace's per-minute limit with the runner's spacing |
| 7 | No KOS rule deploy or n8n change planned during the series | owner | none planned |
| 8 | Frozen workflow commit published | compare the published workflows with the commit (tools) | same commit as the RESULTS.md entry will name |
| 9 | Tables clean | runner reset of q119_* log, queue and claims tables | all empty before run 1 |
| 10 | One dry case through the full path | runner on 1 simulated + 1 live case | runner exit 0; not a result |
