"""First-hour check (BLUEPRINT.md phase P2): can n8n 2.43.7 call a sub-workflow
whose ID is set at run time, and does an error inside it come back as data?

Creates Q119 Probe workflows through the n8n API, calls them through a test
webhook, prints a pass/fail line per check, then unpublishes the probe
webhooks. Not a gated run; no AI, no credentials.
Run: python tools/probe_dynamic_call.py
"""
import json
import sys
import urllib.request
import uuid

sys.path.insert(0, __import__("os").path.dirname(__file__))
from n8n_api import Api, load_env  # noqa: E402


def node(wid, name, ntype, version, params, x, **extra):
    n = {"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"q119-probe/{wid}/{name}")), "name": name,
         "type": ntype, "typeVersion": version, "position": [x * 260, 0], "parameters": params}
    n.update(extra)
    return n


def chain(names):
    return {a: {"main": [[{"node": b, "type": "main", "index": 0}]]} for a, b in zip(names, names[1:])}


def wf(key, name, nodes):
    return {"name": name, "nodes": nodes, "connections": chain([n["name"] for n in nodes]),
            "settings": {"executionOrder": "v1"}}


def child(key, label, typed=False, throws=False):
    trig = {"inputSource": "passthrough"}
    if typed:
        trig = {"inputSource": "workflowInputs", "workflowInputs": {"values": [{"name": "text", "type": "string"}]}}
    code = ("throw new Error('probe error from step " + label + "');" if throws else
            "return [{json: {which: '" + label + "', got: $input.first().json.text}}];")
    return wf(key, "Q119 Probe: step " + label, [
        node(key, "Start", "n8n-nodes-base.executeWorkflowTrigger", 1.3, trig, 0),
        node(key, "Answer", "n8n-nodes-base.code", 2, {"jsCode": code}, 1),
    ])


def parent(key, path, typed=False):
    call = {"source": "database",
            "workflowId": {"__rl": True, "mode": "id", "value": "={{ $json.body.step_id }}"},
            "options": {"waitForSubWorkflow": True}}
    if typed:
        call["workflowInputs"] = {
            "mappingMode": "defineBelow", "value": {"text": "={{ $json.body.text }}"}, "matchingColumns": [],
            "schema": [{"id": "text", "displayName": "text", "required": False, "defaultMatch": False,
                        "display": True, "canBeUsedToMatch": True, "type": "string"}],
            "attemptToConvertTypes": False, "convertFieldsToString": True}
    else:
        # passthrough child gets the input item as it is
        pass
    pre = node(key, "Input", "n8n-nodes-base.code", 2,
               {"jsCode": "const b = $input.first().json.body; return [{json: {body: b, text: b.text}}];"}, 1)
    return wf(key, "Q119 Probe: caller " + ("typed" if typed else "passthrough"), [
        node(key, "Webhook", "n8n-nodes-base.webhook", 2,
             {"httpMethod": "POST", "path": path, "responseMode": "lastNode", "options": {}}, 0,
             webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "q119-probe/" + path))),
        pre,
        node(key, "Call step", "n8n-nodes-base.executeWorkflow", 1.4, call, 2, onError="continueRegularOutput"),
        node(key, "Wrap", "n8n-nodes-base.code", 2,
             {"jsCode": "return [{json: {out: $input.all().map(i => i.json)}}];"}, 3),
    ])


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]


def main():
    api = Api()
    base = load_env()["N8N_URL"].rstrip("/") + "/webhook/"
    ids = {}
    for key, doc in [("A", child("A", "A")), ("B", child("B", "B")), ("C", child("C", "C", throws=True)),
                     ("T", child("T", "T", typed=True))]:
        ids[key] = api.push(doc)
    parents = {"pass": api.push(parent("pass", "q119-probe-pass")),
               "typed": api.push(parent("typed", "q119-probe-typed", typed=True))}
    checks = [
        ("run-time ID -> step A (passthrough)", "q119-probe-pass", {"step_id": ids["A"], "text": "hello A"},
         lambda o: o == [{"which": "A", "got": "hello A"}]),
        ("same node, run-time ID -> step B", "q119-probe-pass", {"step_id": ids["B"], "text": "hello B"},
         lambda o: o == [{"which": "B", "got": "hello B"}]),
        ("error inside step C comes back as data", "q119-probe-pass", {"step_id": ids["C"], "text": "x"},
         lambda o: len(o) == 1 and "error" in o[0]),
        ("unknown step ID comes back as data", "q119-probe-pass", {"step_id": "Q119doesNotExist", "text": "x"},
         lambda o: len(o) == 1 and "error" in o[0]),
        ("run-time ID with typed inputs -> step T", "q119-probe-typed", {"step_id": ids["T"], "text": "hello T"},
         lambda o: o == [{"which": "T", "got": "hello T"}]),
    ]
    failed = 0
    for label, path, body, ok in checks:
        status, res = post(base + path, body)
        out = res.get("out") if isinstance(res, dict) else None
        good = status == 200 and out is not None and ok(out)
        failed += not good
        print(("PASS " if good else "FAIL ") + label + " | http " + str(status) + " | " + json.dumps(out if out is not None else res)[:300])
    for wid in parents.values():
        api.request("POST", f"/workflows/{wid}/unpublish", {})
    print("probe webhooks unpublished; %d of %d checks failed" % (failed, len(checks)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
