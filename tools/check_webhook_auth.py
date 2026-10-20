"""Check that no Q119 webhook is open: every webhook path refuses a call without its key and a call with a
wrong key (n8n answers 401 or 403 before the workflow runs, so these calls change nothing). Calls with the
right key are checked by the runners (tests/runner.py, tests/fixkit_runner.py), which send the keys.

python tools/check_webhook_auth.py
"""
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import runner as R  # noqa: E402
import webhook_keys as WK  # noqa: E402

METHODS = {"q119-report": "GET", "q119-review": "GET"}
base = R.load_env()["N8N_URL"].rstrip("/") + "/webhook/"
bad = 0
for path, cname in WK.PATHS.items():
    method = METHODS.get(path, "POST")
    body = None if method == "GET" else {}
    ctype = WK.CREDS[cname][0]
    wrong = ({"Authorization": "Basic " + base64.b64encode(b"reviewer:wrong").decode()} if ctype == "httpBasicAuth"
             else {WK.HEADER: "wrong"})
    for label, headers in (("no key", {}), ("wrong key", wrong)):
        import json
        import urllib.error
        import urllib.request
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method,
                                     headers=dict(headers, **({"Content-Type": "application/json"} if data else {})))
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                status = r.status
        except urllib.error.HTTPError as e:
            status = e.code
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            status = "no reply (%s)" % e
        ok = status in (401, 403)
        bad += 0 if ok else 1
        print("%-5s %-20s %-6s %-10s -> %s" % ("OK" if ok else "OPEN", path, method, label, status))
print("%d of %d checks failed" % (bad, 2 * len(WK.PATHS)))
sys.exit(1 if bad else 0)
