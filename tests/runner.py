"""Test runner for the n8n AI output guard (Q-119).

Runs cases through the test caller workflow, submits the scripted review actions
through the review form (after every guard call, in reverse case order), reads
the report and the mock log, saves the raw run and prints a basic check per case.
The gate metrics are computed by tests/score.py from the saved raw run.

python tests/runner.py --label dry-1 --ids MJ01,OK05
python tests/runner.py --label visible-1                 (all visible cases)
python tests/runner.py --label gated-1 --data <hold-out folder>/holdout.json --data tests/cases/visible.json
"""
import argparse
import copy
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from n8n_api import Api, load_env  # noqa: E402
import jsonschema  # noqa: E402

VALS = {s: jsonschema.Draft202012Validator(json.loads((ROOT / "tests" / "schemas" / f"{s}.json").read_text(encoding="utf-8")),
                                           format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)
        for s in ("claim_intake", "ticket_triage", "lead_score")}

MOCK = "http://127.0.0.1:8120"
NAMES = {"mock": "Q119 AI step: mock (simulated)", "on_approved": "Q119 Test: on_approved recorder",
         "claim_intake": "Q119 AI step: claim intake (Claude)", "ticket_triage": "Q119 AI step: ticket triage (Claude)",
         "lead_score": "Q119 AI step: lead score (Claude)"}


def http(method, url, body=None, form=None, timeout=60):
    data, headers = None, {}
    if body is not None:
        data, headers = json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"}
    if form is not None:
        data, headers = urllib.parse.urlencode(form).encode("utf-8"), {"Content-Type": "application/x-www-form-urlencoded"}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        return 0, str(e)


def mock_up():
    s, r = http("GET", MOCK + "/health", timeout=3)
    return r.get("cases") if s == 200 and isinstance(r, dict) else None


def script_count(files):
    n = 0
    for f in files:
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        for c in doc["cases"] if isinstance(doc, dict) else doc:
            if c.get("source") == "simulated":
                n += 1 + ((c.get("fallback") or {}).get("mode") == "second_step")
    return n


def ensure_mock(files):
    running = mock_up()
    if running is not None:
        if running != script_count(files):
            raise SystemExit("a mock AI server is already running with %s scripts, but these case files need %s: "
                             "stop it first" % (running, script_count(files)))
        return None
    p = subprocess.Popen([sys.executable, "-I", str(ROOT / "tests" / "mock_server.py"), *map(str, files)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        time.sleep(0.2)
        if mock_up() is not None:
            return p
    raise SystemExit("mock AI server did not start")


def guard_input(c, schemas, ids, label):
    schema = copy.deepcopy(schemas[c["step"]])
    fb = dict(c.get("fallback") or {"mode": "none"})
    if fb.get("mode") == "second_step":
        fb = {"mode": "second_step", "second_step_id": ids["mock"]}
    opts = c.get("options") or {}
    gi = {"task": c["step"], "ai_step_id": ids["mock"] if c["source"] == "simulated" else ids[c["step"]],
          "ai_input": {"text": c["input"]["text"]}, "schema": schema, "fallback": fb,
          "on_approved_id": ids["on_approved"],
          "options": {"timeout_seconds": opts.get("timeout_seconds", 60), "max_tokens": opts.get("max_tokens")},
          "meta": {"case_id": c["id"], "run_label": label}}
    problem = opts.get("setup_problem")
    if problem == "schema_missing":
        gi.pop("schema")
    elif problem == "schema_invalid":
        first = next(iter(schema["properties"]))
        schema["properties"][first]["type"] = "strng"
    elif problem == "ai_step_unknown":
        gi["ai_step_id"] = "Q119doesNotExist"
    elif problem == "input_missing":
        gi["ai_input"] = None
    elif problem == "fallback_invalid" and not (
            fb.get("mode") == "default" and isinstance(fb.get("value"), dict)
            and not VALS[c["step"]].is_valid(fb["value"])):
        gi["fallback"] = {"mode": "default", "value": {}}  # an empty object fails "required"
    return gi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--data", action="append")
    ap.add_argument("--ids", default="")
    ap.add_argument("--gap", type=float, default=1.2, help="seconds between cases (Slack posting limit)")
    a = ap.parse_args()
    files = [Path(p) for p in (a.data or [ROOT / "tests" / "cases" / "visible.json"])]
    cases = []
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        cases += doc["cases"] if isinstance(doc, dict) else doc
    if a.ids:
        want = a.ids.split(",")
        cases = [c for c in cases if c["id"] in want]
    schemas = {s: json.loads((ROOT / "tests" / "schemas" / f"{s}.json").read_text(encoding="utf-8"))
               for s in ("claim_intake", "ticket_triage", "lead_score")}
    api = Api()
    ids = {}
    for k, n in NAMES.items():
        w = api.workflow_by_name(n)
        if not w:
            raise SystemExit("workflow missing in n8n: " + n)
        ids[k] = w["id"]
    base = load_env()["N8N_URL"].rstrip("/") + "/webhook/"
    proc = ensure_mock(files)
    try:
        s, r = http("POST", base + "q119-reset", {"confirm": "reset-q119-tables"})
        if s != 200 or not (isinstance(r, dict) and r.get("reset")):
            raise SystemExit("table reset failed: %s %s" % (s, r))
        http("POST", MOCK + "/reset", {})
        results = {}
        t_start = time.time()
        for c in cases:
            t0 = time.time()
            s, r = http("POST", base + "q119-test", {"guard_input": guard_input(c, schemas, ids, a.label)}, timeout=200)
            results[c["id"]] = {"http": s, "response": r, "seconds": round(time.time() - t0, 2)}
            res = r.get("result", {}) if isinstance(r, dict) else {}
            print("%-6s %-14s http %s  %5.1fs" % (c["id"], res.get("status", "?"), s, time.time() - t0), flush=True)
            time.sleep(a.gap)
        reviews = []
        for c in reversed(cases):
            ra = c.get("review_action")
            res = (results[c["id"]].get("response") or {}).get("result", {}) if isinstance(results[c["id"]].get("response"), dict) else {}
            if not ra or not res.get("review_id"):
                continue
            form = {"id": res["review_id"], "action": ra["action"]}
            if ra["action"] == "correct":
                form["data"] = json.dumps(ra["data"], ensure_ascii=False)
            for i in range(ra.get("repeat", 1)):
                s, r = http("POST", base + "q119-review-submit", form=form)
                reviews.append({"case_id": c["id"], "n": i + 1, "action": ra["action"], "http": s, "response": r})
                time.sleep(0.5)
        time.sleep(2)
        s, report = http("GET", base + "q119-report", timeout=120)
        _, mock_log = http("GET", MOCK + "/log")
    finally:
        if proc:
            proc.terminate()
    out = {"label": a.label, "started": t_start, "seconds": round(time.time() - t_start, 1), "case_files": [str(f) for f in files],
           "cases": [c["id"] for c in cases], "results": results, "reviews": reviews, "report": report,
           "mock_log": mock_log}
    raw_dir = ROOT / "tests" / "results" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{a.label}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    basic(cases, out)


def basic(cases, out):
    """Quick per-case view (not the gate): status, attempts and alert against the case."""
    log = {r["case_id"]: r for r in (out["report"] or {}).get("log", [])} if isinstance(out["report"], dict) else {}
    bad = 0
    for c in cases:
        res = ((out["results"][c["id"]].get("response") or {}) if isinstance(out["results"][c["id"]].get("response"), dict) else {}).get("result", {})
        e, row = c["expected"], log.get(c["id"], {})
        notes = []
        if res.get("status") not in e["status"]:
            notes.append("status %s, expected %s" % (res.get("status"), e["status"]))
        if c["source"] == "simulated" and "attempts" in e and res.get("attempts") != e["attempts"]:
            notes.append("attempts %s, expected %s" % (res.get("attempts"), e["attempts"]))
        if c["source"] == "simulated" and bool(row.get("alert_ts")) != bool(e.get("alert")):
            notes.append("alert %s, expected %s (%s)" % (bool(row.get("alert_ts")), e.get("alert"), row.get("alert_error", "")))
        if e.get("review_row") and not row.get("review_ts"):
            notes.append("no Slack review ts (%s)" % row.get("review_error", ""))
        if isinstance(e.get("data"), dict) and res.get("data") != e["data"]:
            notes.append("data differs")
        bad += bool(notes)
        print(("ok    " if not notes else "CHECK ") + c["id"] + ("" if not notes else "  " + "; ".join(notes)))
    print("%d of %d cases need a look; raw run saved as tests/results/raw/%s.json" % (bad, len(cases), out["label"]))


if __name__ == "__main__":
    main()
