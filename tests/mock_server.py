"""Mock AI server for the simulated test cases (port 8120). No credentials.

Answers like the Anthropic Messages API, one scripted `mock` entry per call, in
order, per case and role (main AI step or second AI step). Entry shapes:
tests/CASES.md section 4. A call beyond the end of the list gets HTTP 500 and
an "over-call" line in the log.

Run: python tests/mock_server.py tests/cases/visible.json [more case files ...]
Endpoints: POST /mock {"case_id", "role"}; POST /reset; GET /health; GET /log
"""
import json
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8120
LOCK = threading.Lock()
SCRIPTS = {}   # (case_id, role) -> list of entries
COUNTS = {}    # (case_id, role) -> calls so far
LOG = []


def load(paths):
    for p in paths:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        for c in doc["cases"] if isinstance(doc, dict) else doc:
            if c.get("source") != "simulated":
                continue
            SCRIPTS[(c["id"], "main")] = c.get("mock") or []
            fb = c.get("fallback") or {}
            if fb.get("mode") == "second_step":
                SCRIPTS[(c["id"], "second")] = fb.get("mock") or []


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _send(self, code, obj, headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _drop(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.connection.close()
        self.close_connection = True

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True, "cases": len(SCRIPTS)})
        if self.path == "/log":
            with LOCK:
                return self._send(200, {"log": list(LOG)})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/reset":
            with LOCK:
                COUNTS.clear()
                LOG.clear()
            return self._send(200, {"reset": True})
        if self.path != "/mock":
            return self._send(404, {"error": "not found"})
        key = (str(body.get("case_id")), str(body.get("role") or "main"))
        with LOCK:
            i = COUNTS.get(key, 0)
            COUNTS[key] = i + 1
            script = SCRIPTS.get(key)
            entry = script[i] if script is not None and i < len(script) else None
            LOG.append({"case_id": key[0], "role": key[1], "n": i + 1, "at": time.time(),
                        "entry": entry if entry is not None else "over-call"})
        if entry is None:
            return self._send(500, {"type": "error", "error": {"type": "api_error", "message": "mock over-call"}})
        if "delay_seconds" in entry:
            time.sleep(entry["delay_seconds"])
            return self._drop()
        if entry.get("close_connection"):
            return self._drop()
        code = entry.get("http", 200)
        if code != 200:
            headers = {"retry-after": str(entry["retry_after"])} if "retry_after" in entry else {}
            etype = {429: "rate_limit_error", 529: "overloaded_error", 401: "authentication_error",
                     403: "permission_error", 400: "invalid_request_error"}.get(code, "api_error")
            return self._send(code, {"type": "error", "error": {"type": etype, "message": "simulated HTTP %d" % code}},
                              headers)
        text = entry.get("text")
        content = [] if text is None else [{"type": "text", "text": text}]
        self._send(200, {"id": "msg_mock", "type": "message", "role": "assistant", "model": "mock-model",
                         "content": content, "stop_reason": entry.get("stop_reason", "end_turn"),
                         "usage": {"input_tokens": 100, "output_tokens": len(text or "") // 4}})


def main():
    load(sys.argv[1:])
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    srv.daemon_threads = True
    print("mock AI server on port %d, %d scripts" % (PORT, len(SCRIPTS)), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
