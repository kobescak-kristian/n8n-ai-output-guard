"""Negative test for the test-set checks in make_cases.py (BLUEPRINT.md v1.3 U4.2).

Plants one mistake at a time in a copy of the visible cases; the checks must
stop on every one of them, and must pass on the unchanged set.
Run: python tests/test_make_cases.py
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_cases as mc  # noqa: E402


def by_id(cases, cid):
    return next(c for c in cases if c["id"] == cid)


def plant(name, change):
    cases = copy.deepcopy(mc.CASES)
    change(cases)
    try:
        mc.validate(cases)
        mc.self_check(cases)
    except mc.CaseError as err:
        return name, True, str(err)
    return name, False, "not caught"


PLANTS = [
    ("duplicate id", lambda cs: cs.append(copy.deepcopy(by_id(cs, "MJ01")))),
    ("unknown kind", lambda cs: by_id(cs, "MJ01").update(kind="malformed")),
    ("unknown status", lambda cs: by_id(cs, "MJ01")["expected"].update(status=["okay"])),
    ("status not a list", lambda cs: by_id(cs, "MJ01")["expected"].update(status="ok_after_retry")),
    ("mock on a live case", lambda cs: by_id(cs, "OK01").update(mock=[mc.ok(mc.CLAIM_1_OK)])),
    ("simulated case without mock", lambda cs: by_id(cs, "MJ04").pop("mock")),
    ("broken mock entry", lambda cs: by_id(cs, "AE01").update(mock=[{"status": 500}])),
    ("review action on an ok case", lambda cs: by_id(cs, "OK05").update(review_action={"action": "reject"})),
    ("correct without data", lambda cs: by_id(cs, "SF02").update(review_action={"action": "correct"})),
    ("invalid correction not marked", lambda cs: by_id(cs, "OR07").update(
        review_action={"action": "correct", "data": mc.with_(mc.CLAIM_3_OK, currency="eur")})),
    ("injection flag on a non-injection case", lambda cs: by_id(cs, "MJ01").update(obvious_injection=True)),
    ("setup case with attempts", lambda cs: by_id(cs, "SU01")["expected"].update(attempts=1)),
    ("data on a needs_review case", lambda cs: by_id(cs, "MJ02")["expected"].update(data=mc.CLAIM_2_OK)),
    ("expected ok but first answer fails", lambda cs: by_id(cs, "MJ01")["expected"].update(status=["ok"])),
    ("wrong expected data", lambda cs: by_id(cs, "AE01")["expected"].update(data=mc.CLAIM_2_OK)),
    ("wrong fallback data", lambda cs: by_id(cs, "MJ03")["expected"].update(data=mc.TICKET_1_OK)),
    ("second step that fails under fallback", lambda cs: by_id(cs, "SF04")["fallback"].update(
        mock=[mc.raw("not json")])),
]


def main():
    failures = 0
    try:
        mc.validate(copy.deepcopy(mc.CASES))
        mc.self_check(copy.deepcopy(mc.CASES))
        print("PASS unchanged set accepted")
    except mc.CaseError as err:
        failures += 1
        print("FAIL unchanged set rejected: %s" % err)
    for name, change in PLANTS:
        name, caught, msg = plant(name, change)
        failures += not caught
        print(("PASS " if caught else "FAIL ") + name + " | " + msg)
    print("%d of %d checks failed" % (failures, len(PLANTS) + 1))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
