# STATE — n8n-ai-output-guard

n8n AI output guard and fix kit (sub-workflow around any AI step: schema check, one retry, fallback, Slack review queue, alert, log; one before/after fix); Upwork portfolio item 7 (Q-119) to support winning a first client.
**Classification:** PROJECT · T0
**Plan:** Owner-approved 2026-10-18 (plan: side-session note item7-output-guard-plan.md; summary here). Build is done when all five quality-bar items hold: (1) reusable: one guard wraps 3 different AI steps (claim intake, ticket triage, lead score from Q-116) with no change to the guard; contract documented; (2) safety: all hard rules of the eval gate hold in all 3 final runs; (3) fix kit: before/after runs of the broken claims workflow recorded, FIX_REPORT written; (4) test standard: 70+ cases committed before the build via eval-gate, about 30% hold-out written by a separate session, 3 runs, worst run reported; (5) README in client words + diagram + plug-in guide + limits, cover image, Loom if among the top 3-4. Order: eval gate -> hold-out session -> first-hour check (sub-workflow called by an ID set at run time; fallback design if it fails) -> build -> runs -> packaging. Target: Wed 2026-10-22.
**Stack (owner-approved 2026-10-18):** local n8n 2.43.7 (shared with other builds: names prefixed Q119, tag q119, data tables q119_*, webhooks /webhook/q119-*, mock AI server port 8120; never restart or reconfigure n8n) · Claude via a new Anthropic workspace `n8n-output-guard` (owner creates; 30-day key; value only in n8n and LastPass) · Slack demo workspace, new channel #ai-review · no Google, no HubSpot, no real business accounts (F-112).
**Status:** scaffold only. Waiting: n8n is in use by another build (owner will say when free); Anthropic workspace not created.
**Open decisions:** none
**Decisions:** none yet (first ADR planned: the guard always returns a status, never throws, never returns unchecked data)

## Change Log
*(New entries on top. Phase closes require evidence: exit codes,
commit hashes, eval numbers.)*

- **2026-10-18** — Scaffold (new-project, standard). Backlog line Q-119 in kristian-wiki dbe8b44.
