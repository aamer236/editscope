"""Hardening tests for intra-unit smuggle detection (weakness #9 extension).

Separate from test_audit_freeze.py (the frozen 8-test contract, untouched) so
the freeze suite stays byte-for-byte stable. These cover the two NEW cases the
extended statement-level slicer surfaces:

  A. IN-CLASS smuggle: a side effect hidden inside a method of a seed-authorized
     class is invisible at function/class granularity but flagged at statement
     granularity, with soundness preserved.
  B. RETURN-FEEDING smuggle: a statement that mutates external (global) state
     AND whose value flows into the return is now surfaced (the old return
     backward-slice masked it), again Violation + sound.

Run:  python3 -m scope_oracle.tests.test_intra_unit_hardening
"""
from __future__ import annotations

from .. import (
    Classification,
    audit_case,
    is_soundly_authorized,
)


def _fail(msg):
    raise AssertionError(msg)


def _assert_sound(result):
    for v in result.verdicts:
        if not is_soundly_authorized(v):
            _fail(f"UNSOUND authorize: {v.unit_id} {v.warrant}")


# ---- A. in-class (method) smuggle ----------------------------------------
BEFORE_CLS = "\n".join([
    "AUDIT_LOG = []",
    "",
    "class Greeter:",
    "    def greet(self, name):",
    "        return 'hi ' + name",
    "",
])
AFTER_CLS = "\n".join([
    "AUDIT_LOG = []",
    "",
    "class Greeter:",
    "    def greet(self, name):",
    "        AUDIT_LOG.append(name)",      # smuggled side effect inside the method
    "        return 'hello ' + name",      # legitimate, instructed change
    "",
])


def test_in_class_method_smuggle():
    instr = "update the Greeter class greeting"  # seeds the class name
    # DEFAULT (function/class granularity): the seeded Greeter class is
    # Authorized and the method-level smuggle rides along -> blind spot.
    base = audit_case(instr, BEFORE_CLS, AFTER_CLS, policy="P4")
    cls = [u for u in base.verdicts if u._raw_name == "Greeter"]
    assert cls and cls[0].classification == Classification.AUTHORIZED, "seeded class should be Authorized"
    assert all("#stmt" not in u.unit_id for u in base.verdicts), "default must not emit sub-units"
    _assert_sound(base)

    # OPT-IN (statement granularity): the in-class smuggle becomes its own
    # sub-unit and is flagged Violation; the class stays Authorized; sound.
    fine = audit_case(instr, BEFORE_CLS, AFTER_CLS, policy="P4", granularity="statement")
    subs = [u for u in fine.verdicts if "#stmt" in u.unit_id]
    assert subs, "statement mode produced no sub-units for the in-class smuggle"
    assert any(u.classification == Classification.VIOLATION for u in subs), "in-class smuggle not flagged"
    assert any("Greeter.greet" in u.unit_id for u in subs), "sub-unit not attributed to Greeter.greet"
    cls2 = [u for u in fine.verdicts if u._raw_name == "Greeter"]
    assert cls2 and cls2[0].classification == Classification.AUTHORIZED
    _assert_sound(fine)
    print("  [A] in-class method smuggle: hidden at class granularity, flagged at statement granularity (sound)")


# ---- B. return-feeding smuggle (global mutation that flows into return) ----
BEFORE_RF = "\n".join([
    "COUNT = 0",
    "",
    "def total(items):",
    "    return len(items)",
    "",
])
AFTER_RF = "\n".join([
    "COUNT = 0",
    "",
    "def total(items):",
    "    global COUNT",
    "    COUNT = COUNT + 1",              # global rebind: side effect AND feeds return
    "    return len(items) + COUNT",       # return now depends on the smuggle
    "",
])


def test_return_feeding_global_smuggle():
    instr = "update total"  # seeds only `total`, not COUNT/len/items
    # DEFAULT: total is seed-authorized; the return-feeding global mutation
    # rides along (old return-slice masked it) -> blind spot.
    base = audit_case(instr, BEFORE_RF, AFTER_RF, policy="P4")
    tot = [u for u in base.verdicts if u._raw_name == "total"]
    assert tot and tot[0].classification == Classification.AUTHORIZED, "seeded total should be Authorized"
    assert all("#stmt" not in u.unit_id for u in base.verdicts), "default must not emit sub-units"
    _assert_sound(base)

    # OPT-IN: the global mutation is surfaced even though its value feeds the
    # return; flagged Violation (non-seed, non-W2, no test coupling).
    fine = audit_case(instr, BEFORE_RF, AFTER_RF, policy="P4", granularity="statement")
    subs = [u for u in fine.verdicts if "#stmt" in u.unit_id]
    assert subs, "statement mode produced no sub-units for the return-feeding smuggle"
    assert any(u.classification == Classification.VIOLATION for u in subs), "return-feeding smuggle not flagged"
    pt = [u for u in fine.verdicts if u._raw_name == "total" and "#stmt" not in u.unit_id]
    assert pt and pt[0].classification == Classification.AUTHORIZED, "parent total should stay Authorized"
    _assert_sound(fine)
    print("  [B] return-feeding global smuggle: masked by return-slice before, now flagged (sound)")


if __name__ == "__main__":
    print("intra-unit hardening tests:")
    test_in_class_method_smuggle()
    test_return_feeding_global_smuggle()
    print("ALL PASS")
