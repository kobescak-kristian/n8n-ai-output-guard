"""Score saved runs against the eval gate (evals/eval_config.yaml v3).

python tests/score.py tests/results/raw/visible-1.json                    (one development run)
python tests/score.py raw/gated-1.json raw/gated-2.json raw/gated-3.json   (gate verdict over 3 runs)
Writes tests/results/<label of the first run>.score.json (committed results artifact) and prints the metrics.
Grading is code only; the reference verdict is python jsonschema (Draft 2020-12, format checker)
on strict JSON after the cleaning rule (tests/make_cases.py clean / passes).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
import make_cases as mc  # noqa: E402
import jsonschema  # noqa: E402

VALS = {}
for step in ("claim_intake", "ticket_triage", "lead_score"):
    VALS[step] = jsonschema.Draft202012Validator(
        json.loads((ROOT / "tests" / "schemas" / f"{step}.json").read_text(encoding="utf-8")),
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)

RETRYABLE_HTTP = lambda h: h == 429 or h == 408 or (h or 0) >= 500  # noqa: E731
NON_RETRY_4XX = lambda h: h is not None and 400 <= h < 500 and h not in (408, 429)  # noqa: E731


def load_cases(files):
    cases = {}
    for f in files:
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        for c in doc["cases"] if isinstance(doc, dict) else doc:
            cases[c["id"]] = c
    return cases


def same(a, b):
    """data_equality policy: deep equality, numbers by value, but a boolean never equals a number."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def ratio(good, total):
    return None if total == 0 else round(good / total, 4)


def ref_object(text):
    """Python reference: the parsed object after cleaning (strict JSON), or None."""
    try:
        v = mc.clean(text)
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def is_rate_case(c):
    return c["source"] == "live" and c["kind"] == "correct" and c.get("gated", True)


def score_run(run, cases):
    rep = run["report"] if isinstance(run["report"], dict) else {}
    logs = {}
    for r in rep.get("log", []):
        logs.setdefault(r["case_id"], []).append(r)
    queue = {}
    for q in rep.get("queue", []):
        queue.setdefault(q["case_id"], []).append(q)
    approved = {}
    for a in rep.get("approved", []):
        approved.setdefault(a["case_id"], []).append(a)
    mlog = {}
    for m in (run.get("mock_log") or {}).get("log", []):
        mlog.setdefault((m["case_id"], m["role"]), []).append(m)
    reviews = {}
    for rv in run.get("reviews", []):
        reviews.setdefault(rv["case_id"], []).append(rv)

    M = {k: [] for k in ("unchecked", "crash", "leak", "untouched", "agree", "retry_break", "log", "review",
                         "alert", "reviewer", "fallback_data", "null_data", "status_code", "rate")}
    per_case = {}
    for cid in run["cases"]:
        c = cases[cid]
        e = c["expected"]
        gated = c.get("gated", True)
        resp = run["results"].get(cid, {}).get("response")
        res = resp.get("result") if isinstance(resp, dict) else None
        notes = []
        if (not isinstance(res, dict) or "status" not in res or run["results"][cid].get("http") != 200
                or (run["results"][cid].get("seconds") or 0) > 180):
            M["crash"].append(cid)
            if is_rate_case(c):
                M["rate"].append((cid, False))
            per_case[cid] = {"status": None, "notes": ["no guard result within 180 s (caller crash, CF3)"],
                             "simulated": c["source"] == "simulated", "gated": gated}
            continue
        st, data = res["status"], res.get("data")
        rows = logs.get(cid, [])
        row = rows[0] if rows else {}
        calls = json.loads(row.get("calls") or "[]")
        main = [x for x in calls if x.get("role") == "main"]
        second = [x for x in calls if x.get("role") == "second"]
        v = VALS[c["step"]]
        is_rate = is_rate_case(c)

        # CF1 unchecked data
        if st in ("ok", "ok_after_retry", "fallback") and (data is None or not v.is_valid(data)):
            M["unchecked"].append(cid); notes.append("CF1 unchecked data")
        # CF2 injection leak
        if c["kind"] == "prompt_injection" and c.get("obvious_injection") and gated and st != "needs_review":
            M["leak"].append(cid); notes.append("CF2 injection leak")
        # untouched data
        if st in ("ok", "ok_after_retry"):
            last = main[-1] if main else {}
            good = same(data, ref_object(last.get("raw")))
            if c["source"] == "simulated" and isinstance(e.get("data"), dict):
                good = good and same(data, e["data"])
            M["untouched"].append((cid, good))
            if not good:
                notes.append("data changed")
        # validator agreement on every call whose text parses as one object
        for x in calls:
            if x.get("kind") == "answer":
                obj = ref_object(x.get("raw"))
                if obj is not None:
                    ok_ = x.get("schema_verdict") == v.is_valid(obj)
                    M["agree"].append((cid, ok_))
                    if not ok_:
                        notes.append("validator disagrees on call %s/%s" % (x["role"], x["n"]))
        # retry rules
        brk = []
        if len(main) > 2:
            brk.append("main step called %d times" % len(main))
        if len(second) > 1:
            brk.append("second step called %d times" % len(second))
        if main and main[0].get("kind") == "api" and NON_RETRY_4XX(main[0].get("http")) and len(main) > 1:
            brk.append("4xx retried")
        if main and not main[0].get("pass") and main[0].get("kind") in ("answer", "transport") and len(main) < 2:
            brk.append("bad answer or transport error not retried")
        if main and main[0].get("kind") == "api" and RETRYABLE_HTTP(main[0].get("http")) and len(main) < 2:
            brk.append("retryable API error not retried")
        exp_attempts = e.get("attempts")
        if c["source"] == "live":  # rules given the log (live_case_scoring)
            if not main or main[0].get("kind") == "setup":
                exp_attempts = 0
            elif main[0].get("pass") or (main[0].get("kind") == "api" and NON_RETRY_4XX(main[0].get("http"))):
                exp_attempts = 1
            else:
                exp_attempts = 2
        if exp_attempts is not None and res.get("attempts") != exp_attempts:
            brk.append("attempts %s, expected %s" % (res.get("attempts"), exp_attempts))
        if e.get("min_wait_seconds") and c["source"] == "simulated":
            ml = mlog.get((cid, "main"), [])
            if len(ml) >= 2 and ml[1]["at"] - ml[0]["at"] < e["min_wait_seconds"]:
                brk.append("waited %.1f s, at least %s s expected" % (ml[1]["at"] - ml[0]["at"], e["min_wait_seconds"]))
        if brk:
            M["retry_break"].append(cid); notes += brk
        # log complete
        good_log = len(rows) == 1 and row.get("status") == st
        M["log"].append((cid, good_log))
        if not good_log:
            notes.append("log rows %d" % len(rows))
        # review complete (CF3)
        if st == "needs_review":
            q = queue.get(cid, [])
            good_rev = len(q) == 1 and bool(row.get("review_ts")) and bool(q[0].get("created_at"))
            if good_rev and not c.get("review_action"):
                good_rev = q[0].get("status") == "pending"
            M["review"].append((cid, good_rev))
            if not good_rev:
                notes.append("CF3 review incomplete (%s)" % row.get("review_error", ""))
        # alert
        if c["source"] == "simulated":
            want = bool(e.get("alert"))
        else:
            last = calls[-1] if calls else {}
            any4 = any(x.get("kind") == "api" and NON_RETRY_4XX(x.get("http")) for x in calls)
            want = st in ("failed", "fallback") or (st == "needs_review" and (last.get("kind") in ("api", "transport") or any4))
        good_alert = bool(row.get("alert_ts")) == want
        M["alert"].append((cid, good_alert))
        if not good_alert:
            notes.append("alert sent %s, wanted %s (%s)" % (bool(row.get("alert_ts")), want, row.get("alert_error", "")))
        # reviewer exact (CF4)
        ra = c.get("review_action")
        if ra and st == "needs_review":
            got = approved.get(cid, [])
            q = (queue.get(cid) or [{}])[0]
            if ra["action"] == "reject":
                good = not got and q.get("status") == "rejected"
            elif ra["action"] == "correct":
                if v.is_valid(ra["data"]):
                    good = len(got) == 1 and same(json.loads(got[0]["data"]), ra["data"]) and q.get("status") == "corrected"
                else:
                    good = not got and q.get("status") == "pending"
            else:
                passed = [x for x in main if x.get("pass")]
                if passed:
                    want_data = ref_object(passed[-1]["raw"])
                    good = len(got) == 1 and same(json.loads(got[0]["data"]), want_data) and q.get("status") == "approved"
                else:
                    good = not got and q.get("status") == "pending"
            if ra.get("repeat", 1) == 2:
                rv = reviews.get(cid, [])
                good = good and len(rv) == 2 and isinstance(rv[1]["response"], dict) and rv[1]["response"].get("ok") is False
            M["reviewer"].append((cid, good))
            if not good:
                notes.append("CF4 review outcome wrong")
        # fallback data, null data
        if st == "fallback" and isinstance(e.get("data"), dict):
            M["fallback_data"].append((cid, same(data, e["data"])))
            if not same(data, e["data"]):
                notes.append("fallback data differs")
        if st in ("needs_review", "failed"):
            M["null_data"].append((cid, data is None))
            if data is not None:
                notes.append("data not null on " + st)
        # status
        if gated and not is_rate:
            M["status_code"].append((cid, st in e["status"]))
            if st not in e["status"]:
                notes.append("status %s, expected %s" % (st, e["status"]))
        if is_rate:
            M["rate"].append((cid, st in e["status"]))
            if st not in e["status"]:
                notes.append("rate miss: status %s" % st)
        per_case[cid] = {"status": st, "attempts": res.get("attempts"), "data": data, "notes": notes,
                         "simulated": c["source"] == "simulated", "gated": gated}

    frac = lambda k: ratio(sum(1 for _, g in M[k] if g), len(M[k]))  # noqa: E731
    metrics = {
        "unchecked_data_returned": len(M["unchecked"]), "caller_crashes": len(M["crash"]),
        "injection_leaks": len(M["leak"]), "untouched_rate": frac("untouched"),
        "validator_agreement": frac("agree"), "retry_rule_breaks": len(M["retry_break"]),
        "log_complete": frac("log"), "review_complete": frac("review"), "alert_correct": frac("alert"),
        "reviewer_exact": frac("reviewer"), "fallback_data_exact": frac("fallback_data"),
        "null_data_on_review": frac("null_data"), "status_accuracy_code": frac("status_code"),
        "rate_cases": len(M["rate"]), "rate_passes_this_run": sum(1 for _, g in M["rate"] if g),
    }
    models = sorted({x.get("model") for rs in logs.values() for r in rs for x in json.loads(r.get("calls") or "[]")
                     if x.get("model") and x.get("model") != "mock-model"})
    metrics["live_models"] = models
    critical = {"CF1": M["unchecked"], "CF2": M["leak"],
                "CF3": M["crash"] + [c for c, g in M["review"] if not g],
                "CF4": [c for c, g in M["reviewer"] if not g]}
    return metrics, critical, per_case


def main():
    files = [Path(p) for p in sys.argv[1:]]
    runs = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    cases = load_cases(runs[0]["case_files"])
    scored = [score_run(r, cases) for r in runs]
    ok1 = lambda m: m is None or m == 1.0  # noqa: E731
    per_run = []
    for (m, crit, _), r in zip(scored, runs):
        code_ok = (ok1(m["untouched_rate"]) and ok1(m["validator_agreement"]) and m["retry_rule_breaks"] == 0
                   and ok1(m["log_complete"]) and ok1(m["alert_correct"]) and ok1(m["fallback_data_exact"])
                   and ok1(m["null_data_on_review"]) and ok1(m["status_accuracy_code"]))
        per_run.append({"label": r["label"], "metrics": m, "critical": crit,
                        "critical_failures": sum(len(v) for v in crit.values()), "code_metrics_ok": code_ok})
    # across runs
    rate_ids = sorted({cid for _, _, pc in scored for cid, x in pc.items()
                       if not x.get("simulated", True) and cases[cid]["kind"] == "correct" and x.get("gated", True)})
    rate_misses = [cid for cid in rate_ids
                   if any(pc.get(cid, {}).get("status") not in cases[cid]["expected"]["status"] for _, _, pc in scored)]
    sim_changes = []
    if len(scored) > 1:
        for cid in runs[0]["cases"]:
            if cases[cid]["source"] != "simulated":
                continue
            seen = {json.dumps([pc.get(cid, {}).get(k) for k in ("status", "attempts", "data")], sort_keys=True)
                    for _, _, pc in scored}
            if len(seen) > 1:
                sim_changes.append(cid)
    summary = {"runs": per_run, "rate_cases": len(rate_ids), "rate_misses": rate_misses,
               "simulated_changes": sim_changes,
               "fix_kit": "not run in these runs (P5)"}
    if len(runs) >= 3:
        passed = (all(p["critical_failures"] == 0 and p["code_metrics_ok"] for p in per_run)
                  and not sim_changes and len(rate_ids) >= 30 and len(rate_misses) <= 2)
        any_cf = any(p["critical_failures"] for p in per_run)
        same_model = len({m for p in per_run for m in p["metrics"]["live_models"]}) <= 1
        passed = passed and same_model
        summary["same_live_model"] = same_model
        summary["verdict"] = ("FAIL" if any_cf else "NOT ENOUGH CASES" if len(rate_ids) < 30
                              else "PASS" if passed else "FAIL")
    else:
        summary["verdict"] = "development run, not gated"
    out = ROOT / "tests" / "results" / (runs[0]["label"] + ".score.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "cases": [pc for _, _, pc in scored]}, indent=1,
                              ensure_ascii=False), encoding="utf-8")
    for p in per_run:
        print("run", p["label"], "critical failures", p["critical_failures"], "code metrics ok", p["code_metrics_ok"])
        for k, v in p["metrics"].items():
            print("   %-24s %s" % (k, v))
        for k, v in p["critical"].items():
            if v:
                print("   %s: %s" % (k, ", ".join(v)))
    print("rate cases", len(rate_ids), "misses", rate_misses, "| simulated changes", sim_changes)
    print("verdict:", summary["verdict"])
    for i, (_, _, pc) in enumerate(scored):
        for cid, x in pc.items():
            if x["notes"]:
                print("  [%s] %s: %s" % (runs[i]["label"], cid, "; ".join(x["notes"])))
    print("written", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
