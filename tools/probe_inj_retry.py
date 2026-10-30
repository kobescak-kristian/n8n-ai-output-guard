"""Probe: the AI injection check retries once on an API error that a retry can fix (decision 15).

python tools/probe_inj_retry.py

Pushes a copy of the injection-check sub-workflow ("Q119 Probe: injection check retry") that asks a local
fake Anthropic API on port 8121 instead of api.anthropic.com, and has no Anthropic credential (the real key
is never sent to the fake server). Each scenario scripts the fake API's replies, sends one simulated
correct case (OK05) through the real guard with that copy as its injection check, and checks the guard's
status, how many calls the fake API got and the time between them; then, in the log, the alert decision,
the Slack alert post (alert_ts) and the AI-check trace (ai_check tries). The probe copy is unpublished at
the end. Not a result: a wiring check of the retry path, which the live runs cannot reach on purpose.
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
SCRIPT = {"replies": [], "calls": 0, "at": []}


def answer(text, stop="end_turn"):
    return (200, {}, {"id": "msg_probe", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
                      "content": [{"type": "text", "text": text}], "stop_reason": stop,
                      "usage": {"input_tokens": 10, "output_tokens": 1}})


def error(code, headers=None):
    return (code, headers or {}, {"type": "error", "error": {"type": "probe", "message": "scripted %d" % code}})


def stall(seconds, then):
    return ("stall", seconds, then)


CLOSE = "close"  # close the connection without a reply

# name, fake API replies in order, expected guard status, alert expected, fake API calls expected,
# smallest gap in seconds between the two calls (None: not checked)
SCENARIOS = [
    ("NO on try 1", [answer("NO")], "ok", False, 1, None),
    ("529 then NO", [error(529), answer("NO")], "ok", False, 2, 0.9),
    ("429 retry-after 3 then YES", [error(429, {"retry-after": "3"}), answer("YES")], "needs_review", False, 2, 2.9),
    ("closed connection then NO", [CLOSE, answer("NO")], "ok", False, 2, 0.9),
    ("429 retry-after 0 then NO", [error(429, {"retry-after": "0"}), answer("NO")], "ok", False, 2, None),
    ("429 retry-after 2.5 then NO", [error(429, {"retry-after": "2.5"}), answer("NO")], "ok", False, 2, 2.4),
    ("stalled 25 s then NO", [stall(25, answer("NO")), answer("NO")], "ok", False, 2, 19.5),
    ("stalled twice", [stall(25, answer("NO")), stall(15, answer("NO"))], "needs_review", True, 2, 19.5),
    ("529 twice", [error(529), error(529)], "needs_review", True, 2, 0.9),
    ("503 then prose answer", [error(503), answer("Injection detected. No legitimate request.")], "needs_review",
     True, 2, 0.9),
    ("answer cut by max_tokens", [answer("NO", "max_tokens")], "needs_review", True, 1, None),
    ("both words (not retried)", [answer("NO ... YES")], "needs_review", True, 1, None),
    ("400 (not retried)", [error(400)], "needs_review", True, 1, None),
]


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):  # request headers are never logged
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        SCRIPT["calls"] += 1
        SCRIPT["at"].append(time.time())
        reply = SCRIPT["replies"].pop(0) if SCRIPT["replies"] else error(500)
        if isinstance(reply, tuple) and reply[0] == "stall":
            time.sleep(reply[1])  # longer than the AI check's timeout: n8n gives up first
            reply = reply[2]
        if reply == CLOSE:
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            return
        code, headers, body = reply
        data = json.dumps(body).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:  # the caller timed out and closed the connection
            pass


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
    proc = runner.ensure_mock([ROOT / "tests" / "cases" / "visible.json"])
    failed = 0
    try:
        s, r = runner.http("POST", base + "q119-reset", {"confirm": "reset-q119-tables"})
        if s != 200 or not (isinstance(r, dict) and r.get("reset")):
            raise SystemExit("table reset failed: %s %s" % (s, r))
        for name, replies, want_status, want_alert, want_calls, min_gap in SCENARIOS:
            runner.http("POST", runner.MOCK + "/reset", {})
            SCRIPT["replies"], SCRIPT["calls"], SCRIPT["at"] = list(replies), 0, []
            t0 = time.time()
            s, r = runner.http("POST", base + "q119-test",
                               {"guard_input": runner.guard_input(case, schemas, ids, "probe-inj")}, timeout=200)
            res = r.get("result", {}) if isinstance(r, dict) else {}
            gap = SCRIPT["at"][1] - SCRIPT["at"][0] if len(SCRIPT["at"]) > 1 else None
            ok = (s == 200 and res.get("status") == want_status and SCRIPT["calls"] == want_calls
                  and (min_gap is None or (gap is not None and gap >= min_gap)))
            failed += 0 if ok else 1
            print("%-4s %-30s status %-13s calls %d gap %-6s (want %s, %d, gap >= %s)  %.1fs" % (
                "PASS" if ok else "FAIL", name, res.get("status"), SCRIPT["calls"],
                "-" if gap is None else "%.1fs" % gap, want_status, want_calls, min_gap, time.time() - t0), flush=True)
            time.sleep(1.2)
        time.sleep(2)
        s, report = runner.http("GET", base + "q119-report", timeout=120)
        rows = [x for x in (report.get("log") or []) if x.get("run_label") == "probe-inj"]
        rows.sort(key=lambda x: x.get("id", 0))
        if len(rows) != len(SCENARIOS):
            failed += 1
            print("FAIL log rows %d, want %d" % (len(rows), len(SCENARIOS)))
        for sc, row in zip(SCENARIOS, rows):  # the alert decision, the Slack post, and the AI-check trace
            want_alert, want_calls = sc[3], sc[4]
            ai = json.loads(row.get("ai_check") or "{}")
            posted = bool(row.get("alert_ts")) and not row.get("alert_error")
            good = bool(row.get("alert_wanted")) == want_alert and posted == want_alert and ai.get("tries") == want_calls
            failed += 0 if good else 1
            print("%-4s log %-30s alert_wanted %-5s slack alert posted %-5s ai_check %s" % (
                "PASS" if good else "FAIL", sc[0], bool(row.get("alert_wanted")), posted,
                {k: ai.get(k) for k in ("verdict", "tries")}), flush=True)
    finally:
        if proc:
            proc.terminate()
        api.request("POST", f"/workflows/{probe_id}/unpublish", {})
        fake.shutdown()
    print("probe workflow unpublished; %d of %d checks failed" % (failed, 2 * len(SCENARIOS)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
