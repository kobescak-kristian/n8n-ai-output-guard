"""Gated runs (BLUEPRINT.md phase P6): 3 full runs over visible + both sealed hold-out batches, each with
its fix-kit run, on one frozen workflow commit. Run only after R4 (preflight, checkpoint review, dry run).

python tests/gated.py --open                 check both seals, extract each zip into a new empty folder
                                             outside the repo, print the case files found (no content)
python tests/gated.py --run --label gated    runs gated-1..3 and fixkit-gated-1..3, then scores them

Hold-out procedure (owner decision 2026-10-19, item 3 / evals/holdout_commitment.json): the SHA-256 of each
zip must equal its committed archive_sha256, or that batch's result is void; only the zip is extracted, into
a new empty folder; the run stops if any case ID is in more than one file.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOLDOUT_DIR = Path.home() / "q119-holdout"
BATCHES = [("evals/holdout_commitment.json", "holdout.zip"), ("evals/holdout2_commitment.json", "holdout2.zip")]
STATE = ROOT / "tests" / "results" / "raw" / "gated-holdout-paths.json"


def sha256(p):
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def open_holdout():
    files = []
    for commit_file, zip_name in BATCHES:
        commit = json.loads((ROOT / commit_file).read_text(encoding="utf-8"))
        z = HOLDOUT_DIR / zip_name
        got = sha256(z)
        if got != commit["archive_sha256"]:
            raise SystemExit("SEAL BROKEN for %s: %s != %s (batch void)" % (zip_name, got, commit["archive_sha256"]))
        out = Path(tempfile.mkdtemp(prefix="q119-%s-" % zip_name.replace(".zip", "")))
        with zipfile.ZipFile(z) as zf:
            zf.extractall(out)
        cases = [p for p in out.rglob("*.json")]
        if len(cases) != 1:
            raise SystemExit("expected one case file in %s, found %d" % (zip_name, len(cases)))
        n = len(json.loads(cases[0].read_text(encoding="utf-8"))["cases"])
        if n != commit["case_count"]:
            raise SystemExit("%s holds %d cases, commitment says %d" % (zip_name, n, commit["case_count"]))
        print("seal OK %s (%s...), %d cases, extracted to %s" % (zip_name, got[:12], n, out))
        files.append(str(cases[0]))
    STATE.write_text(json.dumps(files), encoding="utf-8")
    return files


def run(label):
    files = json.loads(STATE.read_text(encoding="utf-8"))
    data = []
    for f in files + [str(ROOT / "tests" / "cases" / "visible.json")]:
        data += ["--data", f]
    py = sys.executable
    for k in (1, 2, 3):
        for script, lab in (("runner.py", "%s-%d" % (label, k)), ("fixkit_runner.py", "fixkit-%s-%d" % (label, k))):
            r = subprocess.run([py, str(ROOT / "tests" / script), "--label", lab] + data, cwd=ROOT)
            print("%s exit %d" % (lab, r.returncode), flush=True)
            if r.returncode != 0:
                raise SystemExit("%s exited %d: the run does not count (eval-gate rule 4)" % (lab, r.returncode))
    raw = ROOT / "tests" / "results" / "raw"
    r = subprocess.run([py, str(ROOT / "tests" / "score.py")] +
                       [str(raw / ("%s-%d.json" % (label, k))) for k in (1, 2, 3)] + ["--fixkit"] +
                       [str(raw / ("fixkit-%s-%d.json" % (label, k))) for k in (1, 2, 3)], cwd=ROOT)
    print("score exit %d" % r.returncode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--label", default="gated")
    a = ap.parse_args()
    if a.open:
        open_holdout()
    if a.run:
        run(a.label)


if __name__ == "__main__":
    main()
