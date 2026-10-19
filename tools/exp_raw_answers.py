"""Experiment (not a gated run): the raw replies of the AI injection check (prompt v2, effort low), to test a
strict clear-answer rule before it is built (R4 red team, 2026-10-19: a prose reply such as "Injection
detected. No legitimate request." must not be read as NO).

python tools/exp_raw_answers.py --repeat 2

Texts: every attack and normal list (tools/exp_classifier.lists), the round-5 fresh texts and the input text
of every visible case. Counts, per set, replies that are not exactly YES or NO under the strict rule (after
trimming spaces, markdown marks, quotes and end punctuation), replies whose stop reason is not end_turn, and
wrong answers under the strict rule. Output: tests/results/exp-raw-answers-v2-low.json (every distinct reply).
"""
import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "workflows"))
import exp_classifier as E  # noqa: E402
import guard_js as J  # noqa: E402
from n8n_api import load_env  # noqa: E402

TRIM = " \t\r\n*_`\"'“”‘’«».!"


def strict(answer):
    a = answer.strip(TRIM).upper()
    return a.lower() if a in ("YES", "NO") else "error"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=2)
    a = ap.parse_args()
    import runner as R
    base = load_env()["N8N_URL"].rstrip("/") + "/webhook/"
    sets = E.lists()
    r5 = json.loads((ROOT / "tests" / "results" / "round5-texts.json").read_text(encoding="utf-8"))
    sets += [("round 5 fresh attacks", [tuple(x) for x in r5["attacks"]], True),
             ("round 5 fresh normal", [tuple(x) for x in r5["normal"]], False)]
    vis = json.loads((ROOT / "tests" / "cases" / "visible.json").read_text(encoding="utf-8"))["cases"]
    sets += [("visible case inputs", [(c["step"], c["input"]["text"]) for c in vis if c.get("input")], None)]
    replies = collections.Counter()
    summary, misses = [], []
    for label, items, must in sets:
        not_strict = not_end = wrong = 0
        for _ in range(a.repeat):
            for k in range(0, len(items), 25):
                chunk = [t for _, t in items[k:k + 25]]
                s, r = R.http("POST", base + "q119-exp-classify", {"model": "claude-haiku-5-5", "texts": chunk,
                                                                    "system": J.INJ_PROMPT, "effort": "low"},
                              timeout=600)
                res = r.get("results", []) if isinstance(r, dict) else []
                if len(res) != len(chunk):
                    raise SystemExit("classifier call failed: %s %s" % (s, str(r)[:300]))
                for j, x in enumerate(res):
                    replies[(x["answer"], x.get("stop"))] += 1
                    v = strict(x["answer"])
                    if must is True and v != "yes":
                        misses.append({"set": label, "step": items[k + j][0], "text": items[k + j][1], "verdict": v})
                    not_strict += v == "error"
                    not_end += x.get("stop") != "end_turn"
                    if must is not None and v != "error":
                        wrong += (v == "yes") != must
        summary.append({"set": label, "n": len(items), "repeats": a.repeat, "not_strict": not_strict,
                        "stop_not_end_turn": not_end, "wrong_strict": wrong})
        print("%-28s n=%3d x%d  not strict %d  stop not end_turn %d  wrong %d" % (
            label, len(items), a.repeat, not_strict, not_end, wrong), flush=True)
    out = ROOT / "tests" / "results" / "exp-raw-answers-v2-low.json"
    code = E.code_check([(m["step"], m["text"]) for m in misses]) if misses else []
    for m, hit in zip(misses, code):
        m["code_check_flags"] = bool(hit)
    both = [m for m in misses if not m["code_check_flags"]]
    print("attack replies not YES: %d; of these the code check also misses: %d" % (len(misses), len(both)))
    for m in both:
        print("  BOTH MISS", m["set"], m["step"], m["text"][:100].encode("ascii", "backslashreplace").decode())
    out.write_text(json.dumps({"prompt": J.INJ_PROMPT, "effort": "low", "summary": summary, "misses": misses,
                               "distinct_replies": [{"answer": k[0], "stop": k[1], "count": v}
                                                    for k, v in replies.most_common()]},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print("distinct replies:", [(k[0][:40], k[1], v) for k, v in replies.most_common(12)])
    print("written", out.name)


if __name__ == "__main__":
    main()
