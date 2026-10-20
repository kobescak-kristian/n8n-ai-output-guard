"""Evidence file for FIX_REPORT.md: the fix-kit results of the gated runs by case kind, plus the n8n error log
of the BEFORE workflow (node and error message counts). IDs, kinds and counts only, no case texts.

python tools/fixkit_evidence.py      (after tests/gated.py --run; reads the n8n API, read-only)
-> tests/results/fixkit-gated-evidence.json
"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from n8n_api import Api  # noqa: E402

score = json.loads((ROOT / "tests/results/gated-1.score.json").read_text(encoding="utf-8"))["summary"]["fix_kit"]
paths = json.loads((ROOT / "tests/results/raw/gated-holdout-paths.json").read_text(encoding="utf-8"))
kinds = {}
for p in paths + [str(ROOT / "tests/cases/visible.json")]:
    for c in json.loads(Path(p).read_text(encoding="utf-8"))["cases"]:
        kinds[c["id"]] = c["kind"]
raw = json.loads((ROOT / "tests/results/raw/fixkit-gated-1.json").read_text(encoding="utf-8"))
claim_ids = raw["cases"]

out = {"source": "tests/results/gated-1.score.json (fix_kit) and tests/results/raw/fixkit-gated-*.json; hold-out kinds "
                  "from the sealed batches opened by tests/gated.py --open",
       "claim_cases": len(claim_ids), "hold_out_claim_cases": sum(1 for c in claim_ids if c.startswith("H")),
       "claim_cases_by_kind": dict(collections.Counter(kinds[c] for c in claim_ids)),
       "runs_identical": all(json.dumps(k, sort_keys=True) == json.dumps(score[0], sort_keys=True) for k in score),
       "per_run": []}
for k in score:
    run = {}
    for phase in ("before", "after"):
        x = k[phase]
        run[phase] = {"cases": x["cases"], "valid_rows": x["rows_valid"]}
        for key in ("crashes", "rows_invalid", "rows_that_should_not_exist"):
            run[phase][key] = {"count": len(x[key]), "by_kind": dict(collections.Counter(kinds[c] for c in x[key])),
                               "ids": x[key]}
    out["per_run"].append(run)
after = collections.Counter()
for v in raw["after"].values():
    after[v["response"]["result"]["status"]] += 1
out["after_status_run_1"] = dict(after)

api = Api()
w = api.workflow_by_name("Q119 Fix kit: claims intake BEFORE (broken)")
ex = api.request("GET", "/executions", params={"workflowId": w["id"], "status": "error", "limit": 250, "includeData": "true"})
rows = ex.get("data", [])
errs = collections.Counter()
for e in rows:
    rd = ((e.get("data") or {}).get("resultData") or {})
    err = rd.get("error") or {}
    node = (err.get("node") or {}).get("name") or rd.get("lastNodeExecuted")
    errs[node + " | " + (err.get("message") or "")[:80]] += 1
out["n8n_error_log_before"] = {
    "read_at": "n8n API GET /executions?status=error, workflow 'Q119 Fix kit: claims intake BEFORE (broken)'",
    "executions": len(rows), "first_started_utc": rows[-1]["startedAt"] if rows else None,
    "last_started_utc": rows[0]["startedAt"] if rows else None,
    "by_node_and_message": dict(errs.most_common())}
dest = ROOT / "tests/results/fixkit-gated-evidence.json"
dest.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
print("wrote", dest.relative_to(ROOT), "| error executions", len(rows))
