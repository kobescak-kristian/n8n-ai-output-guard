# STATE — n8n-ai-output-guard

n8n AI output guard and fix kit (sub-workflow around any AI step: schema check, one retry, fallback, Slack review queue, alert, log; one before/after fix); Upwork portfolio item 7 (Q-119) to support winning a first client.
**Classification:** PROJECT · T0
**Plan:** Owner-approved 2026-10-18 (plan: side-session note item7-output-guard-plan.md; summary here). Build is done when all five quality-bar items hold: (1) reusable: one guard wraps 3 different AI steps (claim intake, ticket triage, lead score from Q-116) with no change to the guard; contract documented; (2) safety: all hard rules of the eval gate hold in all 3 final runs; (3) fix kit: before/after runs of the broken claims workflow recorded, FIX_REPORT written; (4) test standard: 70+ cases committed before the build via eval-gate, about 30% hold-out written by a separate session, 3 runs, worst run reported; (5) README in client words + diagram + plug-in guide + limits, cover image, Loom if among the top 3-4. Order: eval gate -> hold-out session -> first-hour check (sub-workflow called by an ID set at run time; fallback design if it fails) -> build -> runs -> packaging. No fixed date: done when the quality bar holds (owner 2026-10-19).
**Stack (owner-approved 2026-10-18):** local n8n 2.43.7 (shared with other builds: names prefixed Q119, tag q119, data tables q119_*, webhooks /webhook/q119-*, mock AI server port 8120; never restart or reconfigure n8n) · Claude via a new Anthropic workspace `n8n-output-guard` (owner creates; 30-day key; value only in n8n and LastPass) · Slack demo workspace, new channel #ai-review · no Google, no HubSpot, no real business accounts (F-112).
**Status:** BLUEPRINT.md v1.1 LOCKED 2026-10-19 (Critical, gate v2 option A); eval gate v2 + 79 visible cases committed; hold-out sealed (31 cases, b022111); ADR-001 Proposed; guard build not started. n8n free until Q-117 resumes 2026-10-20 08:00, then Q-119 pauses. Anthropic workspace created and Slack #ai-review created by the owner 2026-10-19; GitHub repo created (private).
**Open decisions:** none
**Decisions:** BLUEPRINT.md section 7; [ADR-001](adr/001-guard-always-returns-a-status.md) the guard always returns a status (Proposed until a recorded run).

## Change Log
*(New entries on top. Phase closes require evidence: exit codes,
commit hashes, eval numbers.)*

- **2026-10-19** — BLUEPRINT.md v1.2 (owner requests): aim for one gated attempt, with checkpoints R1 (red team of the gate before P3) to R4 (checkpoint review + dry run of the frozen commit), new phase P5b; every key, credential and app named `n8n-output-guard` (no backlog or item number). Waiting on the owner: n8n API key in the local `.env`, Slack app + n8n credential `Slack n8n-output-guard`, n8n credential `Anthropic n8n-output-guard`.

- **2026-10-19** — P1c: BLUEPRINT.md v1.1 LOCKED by the owner (eval level Critical; `Safeguard removed: human approval before each checked result is returned to the caller`; gate v2 option A). `evals/eval_config.yaml` v2: code checks 100%, rate claim at least 80% with at most 2 misses on at least 30 live correct cases. 25 live correct cases added (OK08-OK32), none edited or removed: `python tests/make_cases.py` exit 0, "wrote 79 cases", SHA-256 d1b36555... on two runs. Totals 110 cases (hold-out 28%). ADR-001 written (Proposed).

- **2026-10-18** — Hold-out sealed by a separate session (never builds the guard): 31 cases (8 live, 23 simulated; 30 gated), commit b022111 `evals/holdout_commitment.json`; builder re-computed the archive SHA-256 = committed value (3935e1a2...). Total 85 cases, hold-out share 36%.
- **2026-10-18** — Eval gate before build: `evals/eval_config.yaml` v1 (14 gated metrics, worst of 3 runs), `tests/CASES.md` (behaviour rules + case format), 3 schemas, `tests/make_cases.py` -> `tests/cases/visible.json` 54 cases (7 per failure kind x 7 kinds + 5 setup; 44 simulated, 10 live; generator self-check against python jsonschema exit 0; SHA-256 d44a17e5... identical on two runs). Hold-out (>= 23 cases) by a separate session next.

- **2026-10-18** — Scaffold (new-project, standard). Backlog line Q-119 in kristian-wiki dbe8b44.
