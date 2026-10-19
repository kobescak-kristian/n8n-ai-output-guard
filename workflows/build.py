"""Generate and load the n8n workflows of the AI output guard (Q-119).

python workflows/build.py           -> workflows/*.json (placeholders, no credential IDs)
python workflows/build.py --push    -> also creates/updates every Q119 workflow in local n8n through the
                                       n8n API (key in the git-ignored .env), fills credential and workflow
                                       IDs by name, publishes the ones with a trigger

The workflow logic lives here and in guard_js.py; the JSON files are build output.
"""
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "workflows"
sys.path.insert(0, str(OUT))
sys.path.insert(0, str(ROOT / "tools"))
import guard_js as J  # noqa: E402

BASE = "http://localhost:5678"
CHANNEL = "#ai-review"
CRED_NAMES = {"anthropicApi": "Anthropic n8n-output-guard", "slackApi": "Slack n8n-output-guard"}
TABLES = {
    "q119_log": [("call_id", "string"), ("task", "string"), ("case_id", "string"), ("run_label", "string"),
                 ("status", "string"), ("attempts", "number"), ("second_step_calls", "number"), ("errors", "string"),
                 ("calls", "string"), ("injection", "boolean"), ("injection_hits", "string"),
                 ("alert_wanted", "boolean"), ("alert_ts", "string"), ("alert_error", "string"),
                 ("review_id", "string"), ("review_ts", "string"), ("review_error", "string"),
                 ("started_at", "string"), ("seconds", "number"), ("model", "string"), ("tokens_in", "number"),
                 ("tokens_out", "number"), ("data", "string"), ("source", "string"), ("reason", "string")],
    "q119_queue": [("review_id", "string"), ("call_id", "string"), ("case_id", "string"), ("run_label", "string"),
                   ("task", "string"), ("status", "string"), ("reason", "string"), ("input_excerpt", "string"),
                   ("answers", "string"), ("passed_answer", "string"), ("schema", "string"),
                   ("on_approved_id", "string"), ("created_at", "string"), ("decided_at", "string"),
                   ("decision", "string"), ("final_data", "string"), ("decision_note", "string")],
    "q119_approved": [("review_id", "string"), ("case_id", "string"), ("task", "string"), ("data", "string"),
                      ("at", "string")],
    "q119_claims": [("case_id", "string"), ("run_label", "string"), ("workflow", "string"), ("row", "string"),
                    ("at", "string")],
}


class WF:
    def __init__(self, key, name):
        self.key, self.name = key, name
        self.nodes, self.conn = [], {}

    def add(self, name, ntype, version, params, x, y=0, cred=None, **extra):
        n = {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"q119/{self.key}/{name}")), "name": name, "type": ntype,
             "typeVersion": version, "position": [int(x * 260), int(y * 180)], "parameters": params}
        if cred:
            n["credentials"] = {cred: {"id": f"__CRED:{cred}__", "name": CRED_NAMES[cred]}}
        n.update(extra)
        self.nodes.append(n)
        return name

    def link(self, a, b, out=0):
        outs = self.conn.setdefault(a, {"main": []})["main"]
        while len(outs) <= out:
            outs.append([])
        outs[out].append({"node": b, "type": "main", "index": 0})

    def chain(self, *names):
        for a, b in zip(names, names[1:]):
            self.link(a, b)

    def doc(self):
        return {"name": self.name, "nodes": self.nodes, "connections": self.conn,
                "settings": {"executionOrder": "v1"}}


def code(w, name, js, x, y=0, **extra):
    return w.add(name, "n8n-nodes-base.code", 2, {"jsCode": js.strip().replace("__BASE__", BASE) + "\n"}, x, y,
                 **extra)


def if_true(w, name, expr, x, y=0):
    return w.add(name, "n8n-nodes-base.if", 2.2, {"conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
        "conditions": [{"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"q119/{w.key}/{name}")), "leftValue": expr,
                        "rightValue": "", "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
        "combinator": "and"}, "looseTypeValidation": True, "options": {}}, x, y)


def trigger(w, x=0):
    return w.add("Start", "n8n-nodes-base.executeWorkflowTrigger", 1.3, {"inputSource": "passthrough"}, x)


def call(w, name, id_expr, x, y=0):
    return w.add(name, "n8n-nodes-base.executeWorkflow", 1.4, {
        "source": "database", "workflowId": {"__rl": True, "mode": "id", "value": id_expr},
        "options": {"waitForSubWorkflow": True}}, x, y, onError="continueRegularOutput", alwaysOutputData=True)


def table(name):
    return {"__rl": True, "mode": "name", "value": name}


def insert(w, name, tbl, x, y=0, **extra):
    return w.add(name, "n8n-nodes-base.dataTable", 1.1, {
        "dataTableId": table(tbl),
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
        "options": {}}, x, y, onError="continueRegularOutput", **extra)


def get_rows(w, name, tbl, x, y=0, filters=None, **extra):
    p = {"operation": "get", "dataTableId": table(tbl), "returnAll": True}
    if filters:
        p.update(matchType="allConditions", filters={"conditions": filters})
    return w.add(name, "n8n-nodes-base.dataTable", 1.1, p, x, y, alwaysOutputData=True, **extra)


def slack(w, name, text_expr, x, y=0):
    return w.add(name, "n8n-nodes-base.slack", 2.3, {
        "authentication": "accessToken", "select": "channel",
        "channelId": {"__rl": True, "mode": "name", "value": CHANNEL},
        "text": text_expr, "otherOptions": {"includeLinkToWorkflow": False}}, x, y, cred="slackApi",
        onError="continueRegularOutput", retryOnFail=True, maxTries=3, waitBetweenTries=2000)


def webhook(w, name, method, path, x, y=0):
    return w.add(name, "n8n-nodes-base.webhook", 2.1, {"httpMethod": method, "path": path,
                                                       "responseMode": "responseNode", "options": {}}, x, y,
                 webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "q119/" + path)))


def respond(w, name, body_expr, x, y=0):
    return w.add(name, "n8n-nodes-base.respondToWebhook", 1.4,
                 {"respondWith": "json", "responseBody": body_expr, "options": {}}, x, y)


def http_messages(w, name, url, x, y=0, cred=None):
    p = {"method": "POST", "url": url, "sendBody": True, "specifyBody": "json",
         "jsonBody": "={{ JSON.stringify($json.body) }}",
         "options": {"timeout": "={{ $json.timeout_ms }}",
                     "response": {"response": {"fullResponse": True, "neverError": True, "responseFormat": "json"}}}}
    if cred:
        p.update(authentication="predefinedCredentialType", nodeCredentialType="anthropicApi", sendHeaders=True,
                 headerParameters={"parameters": [{"name": "anthropic-version", "value": "2023-06-01"},
                                                  {"name": "anthropic-beta", "value": "server-side-fallback-2026-07-01"}]})
    return w.add(name, "n8n-nodes-base.httpRequest", 4.2, p, x, y, cred=cred, onError="continueRegularOutput")


# ------------------------------------------------------------------------------------------------
def build_guard():
    w = WF("guard", "Q119 Guard: AI output guard")
    trigger(w)
    code(w, "Setup check", J.SETUP_CHECK, 1)
    if_true(w, "AI injection check?", "={{ $json.setup_ok && !!($json.options || {}).injection_check_step_id }}", 1.5, -1)
    code(w, "Prepare injection check", J.PREPARE_INJ, 1.5, -2)
    code(w, "Step input 0", J.STEP_ONLY, 1.8, -2)
    call(w, "Call AI injection check", "={{ $('Prepare injection check').first().json.state.options.injection_check_step_id }}", 2.1, -2)
    code(w, "Read injection check", J.READ_INJ, 2.4, -2)
    if_true(w, "Setup ok?", "={{ $json.setup_ok }}", 2)
    code(w, "Prepare try 1", J.PREPARE_1, 3)
    code(w, "Step input 1", J.STEP_ONLY, 4)
    call(w, "Call AI step (try 1)", "={{ $('Prepare try 1').first().json.state.ai_step_id }}", 5)
    code(w, "Check try 1", J.CHECK_1, 6)
    if_true(w, "Retry?", "={{ $json.next === 'retry' }}", 7)
    w.add("Wait before retry", "n8n-nodes-base.wait", 1.1, {"resume": "timeInterval", "amount": "={{ $json.wait }}",
                                                            "unit": "seconds"}, 8, 1,
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "q119/guard/wait")))
    code(w, "Prepare try 2", J.PREPARE_2, 9, 1)
    code(w, "Step input 2", J.STEP_ONLY, 10, 1)
    call(w, "Call AI step (try 2)", "={{ $('Prepare try 2').first().json.state.ai_step_id }}", 11, 1)
    code(w, "Check try 2", J.CHECK_2, 12, 1)
    if_true(w, "Second step?", "={{ $json.next === 'second' }}", 13)
    code(w, "Prepare second", J.PREPARE_SECOND, 14, 1)
    code(w, "Step input 3", J.STEP_ONLY, 15, 1)
    call(w, "Call second AI step", "={{ $('Prepare second').first().json.state.fallback.second_step_id }}", 16, 1)
    code(w, "Check second", J.CHECK_SECOND, 17, 1)
    code(w, "Decide", J.DECIDE, 18)
    if_true(w, "Review?", "={{ $json.final.review }}", 19)
    code(w, "Queue row", J.QUEUE_ROW, 20, 1)
    insert(w, "Add to review queue", "q119_queue", 21, 1)
    slack(w, "Slack review message", "={{ $('Decide').first().json.review_text }}", 22, 1)
    code(w, "After review", J.AFTER_REVIEW, 23, 1)
    if_true(w, "Alert?", "={{ $json.final.alert }}", 24)
    slack(w, "Slack alert", "={{ $('Alert?').first().json.alert_text }}", 25, 1)
    code(w, "After alert", J.AFTER_ALERT, 26, 1)
    code(w, "Final state", J.FINAL_STATE, 27)
    code(w, "Log row", J.LOG_ROW, 28)
    insert(w, "Write log", "q119_log", 29)
    code(w, "Result", J.RESULT, 30)

    w.chain("Start", "Setup check", "AI injection check?")
    w.link("AI injection check?", "Prepare injection check", 0)
    w.link("AI injection check?", "Setup ok?", 1)
    w.chain("Prepare injection check", "Step input 0", "Call AI injection check", "Read injection check", "Setup ok?")
    w.link("Setup ok?", "Prepare try 1", 0)
    w.link("Setup ok?", "Decide", 1)
    w.chain("Prepare try 1", "Step input 1", "Call AI step (try 1)", "Check try 1", "Retry?")
    w.link("Retry?", "Wait before retry", 0)
    w.link("Retry?", "Second step?", 1)
    w.chain("Wait before retry", "Prepare try 2", "Step input 2", "Call AI step (try 2)", "Check try 2", "Second step?")
    w.link("Second step?", "Prepare second", 0)
    w.link("Second step?", "Decide", 1)
    w.chain("Prepare second", "Step input 3", "Call second AI step", "Check second", "Decide")
    w.chain("Decide", "Review?")
    w.link("Review?", "Queue row", 0)
    w.link("Review?", "Alert?", 1)
    w.chain("Queue row", "Add to review queue", "Slack review message", "After review", "Alert?")
    w.link("Alert?", "Slack alert", 0)
    w.link("Alert?", "Final state", 1)
    w.chain("Slack alert", "After alert", "Final state", "Log row", "Write log", "Result")
    return w


def build_live_step(task, label):
    w = WF("step-" + task, f"Q119 AI step: {label} (Claude)")
    trigger(w)
    code(w, "Build request", J.LIVE_REQUEST.replace("__PROMPT__", json.dumps(J.PROMPTS[task] + J.PROMPT_TAIL)), 1)
    http_messages(w, "Call Claude", "https://api.anthropic.com/v1/messages", 2, cred="anthropicApi")
    code(w, "Normalize answer", J.NORMALIZE, 3)
    w.chain("Start", "Build request", "Call Claude", "Normalize answer")
    return w


def build_injection_check(url="https://api.anthropic.com/v1/messages", key="injection-check",
                          name="Q119 Injection check: Claude Haiku 5.5"):
    # one retry on an API error a retry can fix (owner decision 15); the last node that runs gives the answer
    w = WF(key, name)
    trigger(w)
    code(w, "Build request", J.INJ_REQUEST.replace("__PROMPT__", json.dumps(J.INJ_PROMPT)), 1)
    http_messages(w, "Ask Claude", url, 2, cred="anthropicApi")
    code(w, "Verdict", J.INJ_NORMALIZE.replace("__TRY__", "1"), 3)
    if_true(w, "Retry AI check?", "={{ $json.retry === true }}", 4)
    w.add("Wait before retry", "n8n-nodes-base.wait", 1.1, {"resume": "timeInterval", "amount": "={{ $json.wait }}",
                                                            "unit": "seconds"}, 5, 1,
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, f"q119/{key}/wait")))
    code(w, "Retry request", "return [{ json: $('Build request').first().json }];", 6, 1)
    http_messages(w, "Ask Claude (retry)", url, 7, 1, cred="anthropicApi")
    code(w, "Verdict (retry)", J.INJ_NORMALIZE.replace("__TRY__", "2"), 8, 1)
    w.chain("Start", "Build request", "Ask Claude", "Verdict", "Retry AI check?")
    w.chain("Retry AI check?", "Wait before retry", "Retry request", "Ask Claude (retry)", "Verdict (retry)")
    code(w, "Answer", "return $input.all();", 5, -1)
    w.link("Retry AI check?", "Answer", out=1)
    return w


def build_mock_step():
    w = WF("step-mock", "Q119 AI step: mock (simulated)")
    trigger(w)
    code(w, "Build request", J.MOCK_REQUEST, 1)
    http_messages(w, "Call mock AI", "http://127.0.0.1:8120/mock", 2)
    code(w, "Normalize answer", J.NORMALIZE, 3)
    w.chain("Start", "Build request", "Call mock AI", "Normalize answer")
    return w


def build_on_approved():
    w = WF("on-approved", "Q119 Test: on_approved recorder")
    trigger(w)
    code(w, "Row", r"""
const d = $input.first().json || {};
return [{ json: { review_id: String(d.review_id || ''), case_id: String(d.case_id || ''), task: String(d.task || ''),
  data: JSON.stringify(d.data === undefined ? null : d.data), at: new Date().toISOString() } }];
""", 1)
    insert(w, "Record call", "q119_approved", 2)
    w.chain("Start", "Row", "Record call")
    return w


def build_test_caller():
    w = WF("test-caller", "Q119 Test: caller")
    webhook(w, "Test request", "POST", "q119-test", 0)
    code(w, "Guard input", r"""
const b = $input.first().json.body || {};
return [{ json: Object.assign({}, b.guard_input || {}, { _t0: Date.now() }) }];
""", 1)
    call(w, "Call the guard", "__WF:guard__", 2)
    code(w, "Wrap", r"""
const t0 = $('Guard input').first().json._t0;
return [{ json: { result: $input.first().json, seconds: (Date.now() - t0) / 1000 } }];
""", 3)
    respond(w, "Send result", "={{ JSON.stringify($json) }}", 4)
    w.chain("Test request", "Guard input", "Call the guard", "Wrap", "Send result")
    return w


def build_review():
    w = WF("review", "Q119 Review: review form")
    webhook(w, "Review submit", "POST", "q119-review-submit", 0)
    get_rows(w, "Find review", "q119_queue", 1,
             filters=[{"keyName": "review_id", "condition": "eq",
                       "keyValue": "={{ String(($json.body || {}).id || 'none') }}"}])
    code(w, "Review decide", J.REVIEW_DECIDE, 2, executeOnce=True)
    if_true(w, "Allowed?", "={{ $json.ok }}", 3)
    code(w, "Update fields", J.REVIEW_UPDATE_FIELDS, 4)
    w.add("Update queue row", "n8n-nodes-base.dataTable", 1.1, {
        "operation": "update", "dataTableId": table("q119_queue"), "matchType": "allConditions",
        "filters": {"conditions": [{"keyName": "id", "condition": "eq",
                                    "keyValue": "={{ $('Review decide').first().json.row_id }}"}]},
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
        "options": {}}, 5)
    if_true(w, "Call on_approved?", "={{ $('Review decide').first().json.call }}", 6)
    code(w, "on_approved input", J.ON_APPROVED_INPUT, 7)
    call(w, "Call on_approved", "={{ $('Review decide').first().json.on_approved_id }}", 8)
    respond(w, "Done", "={{ JSON.stringify({ ok: true, status: $('Review decide').first().json.new_status }) }}", 9)
    respond(w, "Refused", "={{ JSON.stringify({ ok: false, reason: $('Review decide').first().json.reason }) }}", 4, 1)
    w.chain("Review submit", "Find review", "Review decide", "Allowed?")
    w.link("Allowed?", "Update fields", 0)
    w.link("Allowed?", "Refused", 1)
    w.chain("Update fields", "Update queue row", "Call on_approved?")
    w.link("Call on_approved?", "on_approved input", 0)
    w.link("Call on_approved?", "Done", 1)
    w.chain("on_approved input", "Call on_approved", "Done")

    webhook(w, "Review page", "GET", "q119-review", 0, 3)
    get_rows(w, "Find review item", "q119_queue", 1, 3,
             filters=[{"keyName": "review_id", "condition": "eq",
                       "keyValue": "={{ String(($json.query || {}).id || 'none') }}"}])
    code(w, "Page", J.REVIEW_PAGE, 2, 3, executeOnce=True)
    w.add("Show page", "n8n-nodes-base.respondToWebhook", 1.4, {
        "respondWith": "text", "responseBody": "={{ $json.html }}",
        "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "text/html; charset=utf-8"}]}}},
        3, 3)
    w.chain("Review page", "Find review item", "Page", "Show page")
    return w


def build_fixkit_before():
    """The broken workflow of the fix kit, shaped like research post C-17: claim e-mail -> AI -> JSON.parse
    -> claims table. No checks, no retry, no review: the way many client workflows are built."""
    w = WF("fixkit-before", "Q119 Fix kit: claims intake BEFORE (broken)")
    w.add("Claim e-mail (test entry)", "n8n-nodes-base.webhook", 2.1,
          {"httpMethod": "POST", "path": "q119-fixkit-before", "responseMode": "lastNode",
           "responseData": "firstEntryJson", "options": {}}, 0,
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "q119/q119-fixkit-before")))
    code(w, "Read e-mail", r"""
const b = $input.first().json.body || {};
return [{ json: { role: 'main', attempt: 1, ai_input: b.ai_input, error_list: null, meta: b.meta || {},
  options: { max_tokens: (b.options || {}).max_tokens || null, timeout_ms: 60000 } } }];
""", 1)
    w.add("Ask the AI", "n8n-nodes-base.executeWorkflow", 1.4, {
        "source": "database",
        "workflowId": {"__rl": True, "mode": "id", "value": "={{ $('Claim e-mail (test entry)').first().json.body.ai_step_id }}"},
        "options": {"waitForSubWorkflow": True}}, 2)
    code(w, "Parse JSON", r"""
// the original workflow: trust the AI and parse its text
const data = JSON.parse($input.first().json.text);
return [{ json: data }];
""", 3)
    code(w, "Claims row", r"""
const meta = $('Read e-mail').first().json.meta || {};
return [{ json: { case_id: String(meta.case_id || ''), run_label: String(meta.run_label || ''), workflow: 'before',
  row: JSON.stringify($input.first().json), at: new Date().toISOString() } }];
""", 4)
    w.add("Save claim", "n8n-nodes-base.dataTable", 1.1, {
        "dataTableId": table("q119_claims"),
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
        "options": {}}, 5)
    code(w, "Saved", "return [{ json: { saved: true } }];", 6)
    w.chain("Claim e-mail (test entry)", "Read e-mail", "Ask the AI", "Parse JSON", "Claims row", "Save claim", "Saved")
    return w


def build_fixkit_after():
    """The same workflow after the fix: the AI step goes through the guard, and a Switch on the status
    decides. Only checked data reaches the claims table; everything else is in the review queue."""
    w = WF("fixkit-after", "Q119 Fix kit: claims intake AFTER (guarded)")
    webhook(w, "Claim e-mail (test entry)", "POST", "q119-fixkit-after", 0)
    code(w, "Guard input", r"""
const b = $input.first().json.body || {};
return [{ json: b.guard_input || {} }];
""", 1)
    call(w, "AI output guard", "__WF:guard__", 2)
    if_true(w, "Checked data?", "={{ ['ok', 'ok_after_retry', 'fallback'].includes($json.status) }}", 3)
    code(w, "Claims row", r"""
const meta = $('Guard input').first().json.meta || {};
return [{ json: { case_id: String(meta.case_id || ''), run_label: String(meta.run_label || ''), workflow: 'after',
  row: JSON.stringify($('AI output guard').first().json.data), at: new Date().toISOString() } }];
""", 4)
    w.add("Save claim", "n8n-nodes-base.dataTable", 1.1, {
        "dataTableId": table("q119_claims"),
        "columns": {"mappingMode": "autoMapInputData", "value": {}, "matchingColumns": [], "schema": []},
        "options": {}}, 5, onError="continueRegularOutput")
    respond(w, "Saved", "={{ JSON.stringify({ result: $('AI output guard').first().json, saved: true }) }}", 6)
    respond(w, "Not saved", "={{ JSON.stringify({ result: $('AI output guard').first().json, saved: false }) }}", 4, 1)
    w.chain("Claim e-mail (test entry)", "Guard input", "AI output guard", "Checked data?")
    w.link("Checked data?", "Claims row", 0)
    w.link("Checked data?", "Not saved", 1)
    w.chain("Claims row", "Save claim", "Saved")
    return w


def build_report():
    w = WF("report", "Q119 Test: report")
    webhook(w, "Report request", "GET", "q119-report", 0)
    get_rows(w, "Log rows", "q119_log", 1, executeOnce=True)
    get_rows(w, "Queue rows", "q119_queue", 2, executeOnce=True)
    get_rows(w, "Approved calls", "q119_approved", 3, executeOnce=True)
    get_rows(w, "Claims rows", "q119_claims", 4, executeOnce=True)
    code(w, "Collect", r"""
const rows = (n) => $(n).all().map((i) => i.json).filter((j) => j && j.id !== undefined);
return [{ json: { log: rows('Log rows'), queue: rows('Queue rows'), approved: rows('Approved calls'), claims: rows('Claims rows') } }];
""", 5, executeOnce=True)
    respond(w, "Send report", "={{ JSON.stringify($json) }}", 6)
    w.chain("Report request", "Log rows", "Queue rows", "Approved calls", "Claims rows", "Collect", "Send report")
    return w


def build_reset():
    w = WF("reset", "Q119 Test: reset tables")
    webhook(w, "Reset request", "POST", "q119-reset", 0)
    if_true(w, "Confirmed?", "={{ ($json.body || {}).confirm === 'reset-q119-tables' }}", 1)
    names = []
    for i, t in enumerate(TABLES):
        n = f"Clear {t}"
        w.add(n, "n8n-nodes-base.dataTable", 1.1, {"resource": "table", "operation": "clear",
                                                   "dataTableId": table(t)}, 2 + i, executeOnce=True)
        names.append(n)
    respond(w, "Done", "={{ JSON.stringify({ reset: true }) }}", 2 + len(TABLES))
    respond(w, "Refused", "={{ JSON.stringify({ reset: false }) }}", 2, 1)
    w.link("Reset request", "Confirmed?")
    w.link("Confirmed?", names[0], 0)
    w.link("Confirmed?", "Refused", 1)
    w.chain(*names, "Done")
    return w


def build_setup():
    w = WF("setup", "Q119 Setup: create tables")
    webhook(w, "Run once", "POST", "q119-setup-tables", 0)
    names = []
    for i, (t, cols) in enumerate(TABLES.items()):
        n = f"Create {t}"
        w.add(n, "n8n-nodes-base.dataTable", 1.1, {
            "resource": "table", "operation": "create", "tableName": t,
            "columns": {"column": [{"name": c, "type": ty} for c, ty in cols]}}, 1 + i, executeOnce=True,
            onError="continueRegularOutput")
        names.append(n)
    respond(w, "Created", "={{ JSON.stringify({ done: true }) }}", 1 + len(TABLES))
    w.chain("Run once", *names, "Created")
    return w


# order matters for --push: a workflow's __WF:key__ references must already exist
BUILDERS = [
    ("setup", build_setup), ("mock-step", build_mock_step),
    ("step-claim_intake", lambda: build_live_step("claim_intake", "claim intake")),
    ("step-ticket_triage", lambda: build_live_step("ticket_triage", "ticket triage")),
    ("step-lead_score", lambda: build_live_step("lead_score", "lead score")),
    ("on-approved", build_on_approved), ("injection-check", build_injection_check), ("guard", build_guard), ("test-caller", build_test_caller),
    ("review", build_review), ("report", build_report), ("reset", build_reset),
    ("fixkit-before", build_fixkit_before), ("fixkit-after", build_fixkit_after),
]


def substitute(obj, creds, wf_ids):
    s = json.dumps(obj)
    for t, cid in creds.items():
        s = s.replace(f"__CRED:{t}__", cid)
    for k, wid in wf_ids.items():
        s = s.replace(f"__WF:{k}__", wid)
    if "__CRED:" in s or "__WF:" in s:
        raise SystemExit("unresolved placeholder in " + obj["name"])
    return json.loads(s)


def main():
    docs = []
    for key, fn in BUILDERS:
        d = fn().doc()
        (OUT / f"{key}.json").write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        docs.append((key, d))
    print("wrote %d workflow files" % len(docs))
    if "--push" not in sys.argv:
        return
    from n8n_api import Api
    api = Api()
    creds = {}
    for c in api.list_all("/credentials"):
        for t, n in CRED_NAMES.items():
            if c.get("name") == n and c.get("type") == t:
                creds[t] = c["id"]
    missing = set(CRED_NAMES) - set(creds)
    if missing:
        raise SystemExit("credentials missing in n8n: " + ", ".join(CRED_NAMES[m] for m in missing))
    wf_ids = {}
    for key, d in docs:
        wid = api.push(substitute(d, creds, wf_ids))
        wf_ids[key] = wid
        print(f"pushed {d['name']} -> {wid}")


if __name__ == "__main__":
    main()
