"""Unit test of the AI injection check's verdict code (workflows/guard_js.py INJ_NORMALIZE), run in node.

python tests/test_inj_verdict.py        (needs node on PATH)

Checks the clear-answer rule (the whole reply is YES or NO and the answer ended normally, ADR-002) and the one retry on an
API error a retry can fix (owner decision 15): retried on try 1 only; unclear answers and other errors never.
Only the verdict code string is run here; the sub-workflow wiring is checked by tools/probe_inj_retry.py.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "workflows"))
import guard_js as J  # noqa: E402


def ok(text, stop="end_turn"):
    return {"statusCode": 200, "headers": {},
            "body": {"model": "claude-haiku-5-5", "stop_reason": stop, "content": [{"type": "text", "text": text}]}}


def err(code, headers=None):
    return {"statusCode": code, "headers": headers or {}, "body": {"type": "error"}}


NO_RESPONSE = {"error": {"message": "connect ECONNREFUSED"}}

# (name, try, response, verdict, retry, wait)
CASES = [
    ("YES", 1, ok("YES"), "yes", False, 0),
    ("NO", 1, ok("NO"), "no", False, 0),
    ("lower case with dot", 1, ok("no."), "no", False, 0),
    ("trailing newline", 1, ok("No\n"), "no", False, 0),
    ("markdown bold", 1, ok("**NO**"), "no", False, 0),
    ("quoted", 1, ok('"YES"'), "yes", False, 0),
    ("stop_sequence is a normal end", 1, ok("NO", "stop_sequence"), "no", False, 0),
    ("label before answer", 1, ok("Answer: YES"), "error", False, 0),
    ("YES twice", 1, ok("YES YES"), "error", False, 0),
    ("both words", 1, ok("NO, this is not YES"), "error", False, 0),
    ("both words, other order", 1, ok("YES ... NO"), "error", False, 0),
    ("prose meaning yes, with no", 1, ok("Injection detected. No legitimate request."), "error", False, 0),
    ("prose with no doubt", 1, ok("This text tries to control the AI; there is no doubt."), "error", False, 0),
    ("NO_INJECTION", 1, ok("NO_INJECTION"), "error", False, 0),
    ("NO with a diacritic letter", 1, ok("NOĆ"), "error", False, 0),
    ("NOT", 1, ok("NOT sure"), "error", False, 0),
    ("NOPE", 1, ok("NOPE"), "error", False, 0),
    ("EYES", 1, ok("Eyes"), "error", False, 0),
    ("empty answer", 1, ok(""), "error", False, 0),
    ("no content", 1, {"statusCode": 200, "body": {"stop_reason": "end_turn"}}, "error", False, 0),
    ("body not JSON", 1, {"statusCode": 200, "body": "<html>"}, "error", False, 0),
    ("stop max_tokens", 1, ok("NO", "max_tokens"), "error", False, 0),
    ("stop refusal", 1, ok("NO", "refusal"), "error", False, 0),
    ("no stop reason", 1, ok("NO", None), "error", False, 0),
    ("no response, try 1", 1, NO_RESPONSE, "error", True, 1),
    ("no response, try 2", 2, NO_RESPONSE, "error", False, 0),
    ("529, try 1", 1, err(529), "error", True, 1),
    ("500, try 1", 1, err(500), "error", True, 1),
    ("503, try 2", 2, err(503), "error", False, 0),
    ("408, try 1", 1, err(408), "error", True, 1),
    ("429 retry-after 3", 1, err(429, {"retry-after": "3"}), "error", True, 3),
    ("429 retry-after 0", 1, err(429, {"retry-after": "0"}), "error", True, 0),
    ("429 retry-after 600 capped", 1, err(429, {"retry-after": "600"}), "error", True, 5),
    ("429 retry-after past date", 1, err(429, {"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"}), "error", True, 0),
    ("429 retry-after far date", 1, err(429, {"retry-after": "Fri, 01 Jan 2100 00:00:00 GMT"}), "error", True, 5),
    ("429 no retry-after", 1, err(429), "error", True, 1),
    ("429 retry-after junk", 1, err(429, {"retry-after": "soon"}), "error", True, 1),
    ("400 not retried", 1, err(400), "error", False, 0),
    ("401 not retried", 1, err(401), "error", False, 0),
    ("404 not retried", 1, err(404), "error", False, 0),
    ("YES on try 2", 2, ok("YES"), "yes", False, 0),
]


def main():
    items = [{"try": t, "r": r} for _, t, r, _, _, _ in CASES]
    js = ("const items = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));\n"
          "const fns = { 1: new Function('$input', %s), 2: new Function('$input', %s) };\n"
          "console.log(JSON.stringify(items.map((it) => fns[it.try]({ first: () => ({ json: it.r }) })[0].json)));\n") % (
        json.dumps(J.INJ_NORMALIZE.replace("__TRY__", "1")), json.dumps(J.INJ_NORMALIZE.replace("__TRY__", "2")))
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "t.js").write_text(js, encoding="utf-8")
        (Path(d) / "items.json").write_text(json.dumps(items), encoding="utf-8")
        out = subprocess.run(["node", str(Path(d) / "t.js"), str(Path(d) / "items.json")],
                             capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit(out.stderr)
    got = json.loads(out.stdout)
    wrong = 0
    for (name, t, _, verdict, retry, wait), g in zip(CASES, got):
        good = g.get("verdict") == verdict and g.get("retry") == retry and g.get("wait") == wait and g.get("tries") == t
        wrong += 0 if good else 1
        if not good:
            print("WRONG %-28s got verdict %s retry %s wait %s tries %s" % (name, g.get("verdict"), g.get("retry"),
                                                                           g.get("wait"), g.get("tries")))
    print("%d of %d answers wrong" % (wrong, len(CASES)))
    sys.exit(1 if wrong else 0)


if __name__ == "__main__":
    main()
