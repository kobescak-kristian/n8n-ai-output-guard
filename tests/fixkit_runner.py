"""Fix-kit run: the same claim cases through the BEFORE (broken) and the AFTER (guarded) workflow.

python tests/fixkit_runner.py --label fixkit-1                       (visible claim cases)
python tests/fixkit_runner.py --label fixkit-g1 --data <hold-out>/holdout.json --data tests/cases/visible.json

Both phases use the same AI answers: the mock AI server is reset between them, and live cases call
Claude in each phase. Review actions are submitted for the AFTER phase as in the main run; on_approved
goes to the test recorder, never to the claims table. Saves tests/results/raw/<label>.json and prints a
summary; tests/score.py --fixkit scores it (fix_kit_after_crashes, fix_kit_after_bad_rows).
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import runner as R  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--data", action="append")
    ap.add_argument("--gap", type=float, default=1.2)
    ap.add_argument("--no-classifier", action="store_true", help="code check only, without the AI injection check")
    a = ap.parse_args()
    R.CLASSIFIER["on"] = not a.no_classifier
    files = [Path(p) for p in (a.data or [ROOT / "tests" / "cases" / "visible.json"])]
    cases = []
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        cases += [c for c in (doc["cases"] if isinstance(doc, dict) else doc) if c["step"] == "claim_intake"]
    ids_seen = [c["id"] for c in cases]
    if len(ids_seen) != len(set(ids_seen)):
        raise SystemExit("duplicate case IDs across the case files")
    schemas = {s: json.loads((ROOT / "tests" / "schemas" / f"{s}.json").read_text(encoding="utf-8"))
               for s in ("claim_intake", "ticket_triage", "lead_score")}
    api = R.Api()
    ids = {k: api.workflow_by_name(n)["id"] for k, n in R.NAMES.items()}
    base = R.load_env()["N8N_URL"].rstrip("/") + "/webhook/"
    proc = R.ensure_mock(files)
    out = {"label": a.label, "case_files": [str(f) for f in files], "cases": [c["id"] for c in cases],
           "before": {}, "after": {}, "reviews": []}
    try:
        s, r = R.http("POST", base + "q119-reset", {"confirm": "reset-q119-tables"})
        if s != 200:
            raise SystemExit("table reset failed")
        for phase in ("before", "after"):
            R.http("POST", R.MOCK + "/reset", {})
            for c in cases:
                gi = R.guard_input(c, schemas, ids, a.label)
                t0 = time.time()
                if phase == "before":
                    body = {"ai_step_id": gi["ai_step_id"], "ai_input": gi["ai_input"], "meta": gi["meta"],
                            "options": gi["options"]}
                    s, r = R.http("POST", base + "q119-fixkit-before", body, timeout=200)
                else:
                    s, r = R.http("POST", base + "q119-fixkit-after", {"guard_input": gi}, timeout=200)
                out[phase][c["id"]] = {"http": s, "response": r, "seconds": round(time.time() - t0, 2)}
                print("%-6s %-7s http %s" % (c["id"], phase, s), flush=True)
                time.sleep(a.gap)
        for c in reversed(cases):
            ra = c.get("review_action")
            res = (out["after"][c["id"]].get("response") or {})
            res = res.get("result", {}) if isinstance(res, dict) else {}
            if not ra or not res.get("review_id"):
                continue
            form = {"id": res["review_id"], "action": ra["action"]}
            if ra["action"] == "correct":
                form["data"] = json.dumps(ra["data"], ensure_ascii=False)
            for i in range(ra.get("repeat", 1)):
                s, r = R.http("POST", base + "q119-review-submit", form=form)
                out["reviews"].append({"case_id": c["id"], "n": i + 1, "http": s, "response": r})
        time.sleep(2)
        s, out["report"] = R.http("GET", base + "q119-report", timeout=120)
    finally:
        if proc:
            proc.terminate()
    raw = ROOT / "tests" / "results" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / f"{a.label}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    claims = (out["report"] or {}).get("claims", []) if isinstance(out["report"], dict) else []
    for phase in ("before", "after"):
        crashes = sum(1 for v in out[phase].values() if v["http"] != 200)
        rows = [r for r in claims if r["workflow"] == phase]
        print("%s: %d cases, %d crashed, %d rows saved" % (phase, len(cases), crashes, len(rows)))
    print("raw run saved as tests/results/raw/%s.json" % a.label)


if __name__ == "__main__":
    main()
