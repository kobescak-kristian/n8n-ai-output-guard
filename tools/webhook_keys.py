"""Webhook keys for the Q119 webhooks (go-live pack: no open webhook).

    python tools/webhook_keys.py create   creates the 7 webhook credentials in n8n with new random keys
                                           and stores the same keys in Windows user variables (never printed)
    python tools/webhook_keys.py check    the 7 credentials (names, types, ids) and which user variables are set

Six machine webhooks use n8n Header Auth (header X-Guard-Token), one credential per workflow. The review page
and its submit button are opened by a person from the Slack link, so they share one Basic Auth credential
(user "reviewer"); the browser asks once. The test tools read the keys with secret() below.
Only credentials named "Webhook n8n-output-guard ..." are created or read.
"""
import base64
import os
import sys
from pathlib import Path

HEADER = "X-Guard-Token"
REVIEW_USER = "reviewer"
# credential name -> (n8n credential type, Windows user variable)
CREDS = {
    "Webhook n8n-output-guard test-caller": ("httpHeaderAuth", "GUARD_TOKEN_TEST_CALLER"),
    "Webhook n8n-output-guard report": ("httpHeaderAuth", "GUARD_TOKEN_REPORT"),
    "Webhook n8n-output-guard reset": ("httpHeaderAuth", "GUARD_TOKEN_RESET"),
    "Webhook n8n-output-guard setup": ("httpHeaderAuth", "GUARD_TOKEN_SETUP"),
    "Webhook n8n-output-guard fixkit-before": ("httpHeaderAuth", "GUARD_TOKEN_FIXKIT_BEFORE"),
    "Webhook n8n-output-guard fixkit-after": ("httpHeaderAuth", "GUARD_TOKEN_FIXKIT_AFTER"),
    "Webhook n8n-output-guard review": ("httpBasicAuth", "GUARD_REVIEW_PASSWORD"),
}
# webhook path -> credential name
PATHS = {
    "q119-test": "Webhook n8n-output-guard test-caller",
    "q119-report": "Webhook n8n-output-guard report",
    "q119-reset": "Webhook n8n-output-guard reset",
    "q119-setup-tables": "Webhook n8n-output-guard setup",
    "q119-fixkit-before": "Webhook n8n-output-guard fixkit-before",
    "q119-fixkit-after": "Webhook n8n-output-guard fixkit-after",
    "q119-review": "Webhook n8n-output-guard review",
    "q119-review-submit": "Webhook n8n-output-guard review",
}


def secret(var):
    """The value of a Windows user variable (or the process environment); None when not set."""
    v = os.environ.get(var)
    if v:
        return v
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, var)[0]
    except OSError:
        return None


def auth_headers(path):
    """Headers that open the webhook at this path; {} for paths without a credential."""
    name = PATHS.get(path)
    if not name:
        return {}
    ctype, var = CREDS[name]
    value = secret(var)
    if not value:
        sys.exit(f"user variable {var} is not set: run python tools/webhook_keys.py create")
    if ctype == "httpBasicAuth":
        return {"Authorization": "Basic " + base64.b64encode(f"{REVIEW_USER}:{value}".encode()).decode()}
    return {HEADER: value}


def _api():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from n8n_api import Api
    return Api()


def existing(api):
    return {c["name"]: c for c in api.list_all("/credentials") if c.get("name") in CREDS}


def cmd_create():
    import ctypes
    import secrets
    import winreg
    api = _api()
    have = existing(api)
    for name, (ctype, var) in CREDS.items():
        if name in have:
            print(f"exists, left as is: {name}")
            continue
        value = secrets.token_hex(32)
        data = {"name": HEADER, "value": value} if ctype == "httpHeaderAuth" else {"user": REVIEW_USER, "password": value}
        api.request("POST", "/credentials", {"name": name, "type": ctype, "data": data})
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, var, 0, winreg.REG_SZ, value)
        print(f"created: {name} in n8n, same key in user variable {var}")
    # tell Windows the user variables changed, so new terminals see them
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, None)


def cmd_check():
    have = existing(_api())
    for name, (ctype, var) in CREDS.items():
        c = have.get(name)
        print("%-42s %-15s %s  user variable %s %s" % (name, ctype, ("id " + c["id"]) if c else "MISSING",
                                                        var, "set" if secret(var) else "NOT SET"))
    sys.exit(0 if len(have) == len(CREDS) and all(secret(v) for _, v in CREDS.values()) else 1)


if __name__ == "__main__":
    {"create": cmd_create, "check": cmd_check}.get((sys.argv[1:] or [""])[0], lambda: sys.exit(__doc__))()
