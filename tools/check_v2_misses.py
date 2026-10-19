"""Run the code check on every attack text that AI-check prompt v2 missed (tests/results/exp-stability-v2-low.json),
for each of the 3 AI steps. Offline (node), no n8n or API calls.

python tools/check_v2_misses.py .
"""
import json, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(sys.argv[1])
sys.path.insert(0, str(ROOT / "workflows"))
import guard_js as J
d = json.loads((ROOT / "tests" / "results" / "exp-stability-v2-low.json").read_text(encoding="utf-8"))
wrong = []
for r in d["raw"]:
    if "attacks" in r["set"]:
        for w in r["wrong"]:
            wrong.append(w if isinstance(w, str) else (w.get("text") or w.get("t") or json.dumps(w)))
print("prompt v2 misses:", len(wrong))
S = {s: json.loads((ROOT / "tests" / "schemas" / f"{s}.json").read_text(encoding="utf-8")) for s in ("claim_intake", "ticket_triage", "lead_score")}
items = [{"input": {"text": t}, "schema": S[s], "s": s} for t in wrong for s in S]
js = J.LIB + "\nconst items = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));\n" \
     "console.log(JSON.stringify(items.map((it) => injectionHits(it.input, it.schema))));\n"
with tempfile.TemporaryDirectory() as tdir:
    (Path(tdir) / "a.js").write_text(js, encoding="utf-8")
    (Path(tdir) / "i.json").write_text(json.dumps(items), encoding="utf-8")
    out = subprocess.run(["node", str(Path(tdir) / "a.js"), str(Path(tdir) / "i.json")], capture_output=True, text=True, encoding="utf-8")
if out.returncode:
    raise SystemExit(out.stderr)
hits = json.loads(out.stdout)
missed = [(it["s"], it["input"]["text"]) for it, h in zip(items, hits) if not h]
for s in S:
    print(s, "missed by code check too:", sum(1 for x in missed if x[0] == s))
for s, t in missed:
    print("  ", s, "|", t.replace("\n", " ")[:110])
