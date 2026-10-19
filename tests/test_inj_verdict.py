"""Unit test of the AI injection check's verdict code (workflows/guard_js.py INJ_NORMALIZE), run in node.

python tests/test_inj_verdict.py        (needs node on PATH)

Checks the clear-answer rule (exactly one of YES / NO as a whole word, ADR-002) and the one retry on an
API error a retry can fix (owner decision 15): retried on try 1 only; unclear answers and other errors never.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "workflows"))
import guard_js as J  # noqa: E402


def ok(text):
    return {"statusCode": 200, "headers": {}, "body": {"model": "claude-haiku-5-5", "content": [{"type": "text", "text": text}]}}


def err(code, headers=None):
    return {"statusCode": code, "headers": headers or {}, "body": {"type": "error"}}


NO_RESPONSE = {"error": {"message": "connect ECONNREFUSED"}}

# (name, try, response, verdict, retry, wait)
CASES = [
    ("YES", 1, ok("YES"), "yes", False, 0),
    ("NO", 1, ok("NO"), "no", False, 0),
    ("lower case with dot", 1, ok("no."), "no", False, 0),
    ("label before answer", 1, ok("Answer: YES"), "yes", False, 0),
    ("YES twice", 1, ok("YES YES"), "yes", False, 0),
    ("trailing newline", 1, ok("No\n"), "no", False, 0),
    ("both words", 1, ok("NO, this is not YES"), "error", False, 0),
    ("both words, other order", 1, ok("YES ... NO"), "error", False, 0),
    ("NOT is not NO", 1, ok("NOT sure"), "error", False, 0),
    ("NOPE", 1, ok("NOPE"), "error", False, 0),
    ("EYES", 1, ok("Eyes"), "error", False, 0),
    ("empty answer", 1, ok(""), "error", False, 0),
    ("no content", 1, {"statusCode": 200, "body": {}}, "error", False, 0),
    ("body not JSON", 1, {"statusCode": 200, "body": "<html>"}, "error", False, 0),
    ("no response, try 1", 1, NO_RESPONSE, "error", True, 1),
    ("no response, try 2", 2, NO_RESPONSE, "error", False, 0),
    ("529, try 1", 1, err(529), "error", True, 1),
    ("500, try 1", 1, err(500), "error", True, 1),
    ("503, try 2", 2, err(503), "error", False, 0),
    ("408, try 1", 1, err(408), "error", True, 1),
    ("429 retry-after 3", 1, err(429, {"retry-after": "3"}), "error", True, 3),
    ("429 retry-after 600 capped", 1, err(429, {"retry-after": "600"}), "error", True, 10),
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
