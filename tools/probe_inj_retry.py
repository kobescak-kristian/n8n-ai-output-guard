"""Probe: the AI injection check retries once on an API error that a retry can fix (owner decision 15).

python tools/probe_inj_retry.py

Pushes a copy of the injection-check sub-workflow ("Q119 Probe: injection check retry") that asks a local
fake Anthropic API on port 8121 instead of api.anthropic.com, and has no Anthropic credential (the real key
is never sent to the fake server). Each scenario scripts the fake API's replies, sends one simulated
correct case (OK05) through the real guard with that copy as its injection check, and checks the guard's
status, the alert, and how many calls the fake API got. The probe copy is unpublished at the end.
Not a result: a wiring check of the retry path, which the live runs cannot reach on purpose.
"""
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "workflows"))
sys.path.insert(0, str(ROOT / "tests"))
import build  # noqa: E402
import runner  # noqa: E402
from n8n_api import Api, load_env  # noqa: E402

PORT = 8121
CASE_ID = "OK05"
SCRIPT = {"replies": [], "calls": 0}


def answer(text):
    return (200, {}, {"id": "msg_probe", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
                      "content": [{"type": "text", "text": text}], "stop_reason": "end_turn",
                      "usage": {"input_tokens": 10, "output_tokens": 1}})


def error(code, headers=None):
    return (code, headers or {}, {"type": "error", "error": {"type": "probe", "message": "scripted %d" % code}})


CLOSE = "close"  # close the connection without a reply

# name, fake API replies in order, expected guard status, alert expected, fake API calls expected
SCENARIOS = [
    ("NO on try 1", [answer("NO")], "ok", False, 1),
    ("529 then NO", [error(529), answer("NO")], "ok", False, 2),
    ("429 retry-after 3 then YES", [error(429, {"retry-after": "3"}), answer("YES")], "needs_review", False, 2),
    ("closed connection then NO", [CLOSE, answer("NO")], "ok", False, 2),
    ("529 twice", [error(529), error(529)], "needs_review", True, 2),
    ("503 then mixed answer", [error(503), answer("NO, not YES")], "needs_review", True, 2),
    ("mixed answer (not retried)", [answer("NO ... YES")], "needs_review", True, 1),
    ("400 (not retried)", [error(400)], "needs_review", True, 1),
]


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):  # request headers (with any key) are never logged
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        SCRIPT["calls"] += 1
        reply = SCRIPT["replies"].pop(0) if SCRIPT["replies"] else error(500)
        if reply == CLOSE:
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            return
        code, headers, body = reply
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    api = Api()
    fake = ThreadingHTTPServer(("127.0.0.1", PORT), Fake)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    w = build.build_injection_check(url="http://127.0.0.1:%d/v1/messages" % PORT, key="probe-inj",
                                    name="Q119 Probe: injection check retry")
    for n in w.nodes:
        if n["type"] == "n8n-nodes-base.httpRequest":  # no credential: the real key never reaches the fake API
            n.pop("credentials", None)
            for k in ("authentication", "nodeCredentialType"):
                n["parameters"].pop(k, None)
    probe_id = api.push(w.doc())
    ids = {k: api.workflow_by_name(n)["id"] for k, n in runner.NAMES.items()}
    ids["injection_check"] = probe_id
    cases = json.loads((ROOT / "tests" / "cases" / "visible.json").read_text(encoding="utf-8"))["cases"]
    case = next(c for c in cases if c["id"] == CASE_ID)
    schemas = {s: json.loads((ROOT / "tests" / "schemas" / f"{s}.json").read_text(encoding="utf-8"))
               for s in ("claim_intake", "ticket_triage", "lead_score")}
    base = load_env()["N8N_URL"].rstrip("/") + "/webhook/"
    files = [ROOT / "tests" / "cases" / "visible.json"]
    proc = runner.ensure_mock(files)
    failed = 0
    try:
        s, r = runner.http("POST", base + "q119-reset", {"confirm": "reset-q119-tables"})
        if s != 200 or not (isinstance(r, dict) and r.get("reset")):
            raise SystemExit("table reset failed: %s %s" % (s, r))
        for name, replies, want_status, want_alert, want_calls in SCENARIOS:
            runner.http("POST", runner.MOCK + "/reset", {})
            SCRIPT["replies"], SCRIPT["calls"] = list(replies), 0
            t0 = time.time()
            s, r = runner.http("POST", base + "q119-test",
                               {"guard_input": runner.guard_input(case, schemas, ids, "probe-inj")}, timeout=200)
            res = r.get("result", {}) if isinstance(r, dict) else {}
            alert = bool(res.get("alert")) if "alert" in res else None
            ok = s == 200 and res.get("status") == want_status and SCRIPT["calls"] == want_calls and \
                (alert is None or alert == want_alert)
            failed += 0 if ok else 1
            print("%-4s %-30s status %-13s alert %-5s calls %d (want %s, %s, %d)  %.1fs" % (
                "PASS" if ok else "FAIL", name, res.get("status"), alert, SCRIPT["calls"], want_status, want_alert,
                want_calls, time.time() - t0), flush=True)
            time.sleep(1.2)
        s, report = runner.http("GET", base + "q119-report", timeout=120)
        rows = [x for x in (report.get("log") or []) if x.get("run_label") == "probe-inj"]
        print("log rows %d; alert_wanted per row: %s" % (len(rows), [x.get("alert_wanted") for x in rows]))
        want = [sc[3] for sc in SCENARIOS]
        if [bool(x.get("alert_wanted")) for x in rows] != want:
            failed += 1
            print("FAIL alert_wanted in the log does not match", want)
    finally:
        if proc:
            proc.terminate()
        api.request("POST", f"/workflows/{probe_id}/unpublish", {})
        fake.shutdown()
    print("probe workflow unpublished; %d of %d checks failed" % (failed, len(SCENARIOS) + 1))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
