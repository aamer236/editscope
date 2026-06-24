"""Weakness #8: grounding/seed accuracy hardening (OPT-IN precise mode).

Run:  python3 -m scope_oracle.tests.test_grounding_precision

Grounding is name-level: the seed is the set of code identifiers the
instruction names, and seed => Authorized. The validated extractor
(`grounding_mode="legacy"`, the default) is a plain token ∩ AST-name
intersection with two accuracy failures. Precise mode fixes both, conservatively
and opt-in, so the frozen default path and the validated n=104 metrics are
untouched.

  P. PRECISION (soundness): a generic word in the instruction ("result") that
     coincides with a real identifier must NOT seed-authorize an unrequested
     edit to that identifier. Legacy grounds it (false authorization); precise
     filters the stop-word collision out, so the out-of-scope edit is flagged.
  R. RECALL: an instruction that names the target by a morphological variant
     ("the serializer" for `serialize`) must still authorize the legitimate
     edit. Legacy misses it (empty seed -> false Violation); precise grounds it
     via light stemming restricted to distinctive identifiers.
  N. NO-REGRESSION: on clean fixtures, precise produces the SAME seed as legacy,
     and an unrelated distinctive function is NOT grounded by recall.
"""
from __future__ import annotations

from .. import Classification, audit_case, is_soundly_authorized
from ..grounding import ground_seed


def _fail(msg):
    raise AssertionError(msg)


def _assert_sound(result):
    for u in result.verdicts:
        if not is_soundly_authorized(u):
            _fail(f"UNSOUND authorize: {u.unit_id} warrant={u.warrant}")


# ---- P. precision: a stop-word collision must not authorize creep -----------
# `result` is a real function AND a generic English noun. The instruction uses
# "result" as a noun ("normalize the result"), NOT as a request to edit the
# function literally named result.
BEFORE_P = "\n".join([
    "def result(payload):",
    "    return payload",
    "",
    "def normalize(text):",
    "    return text.strip()",
    "",
])
AFTER_P = "\n".join([
    "def result(payload):",
    "    return payload.upper()",        # OUT-OF-SCOPE creep
    "",
    "def normalize(text):",
    "    return text.strip().lower()",   # the actually-requested change
    "",
])


def test_precision_stopword_collision():
    instr = "normalize the result"

    # LEGACY over-grounds: "result" the noun matches the function `result`, so
    # the unrequested result-edit is FALSELY seed-authorized.
    legacy = ground_seed(instr, BEFORE_P, AFTER_P, mode="legacy")
    assert "result" in legacy.names, "setup: legacy should exhibit the false ground"
    base = audit_case(instr, BEFORE_P, AFTER_P, policy="P4")  # default = legacy
    rl = [u for u in base.verdicts if u._raw_name == "result"]
    assert rl and rl[0].classification == Classification.AUTHORIZED, (
        "setup: legacy should false-authorize the result edit (demonstrates weakness #8)"
    )

    # PRECISE drops the stop-word collision: `result` is no longer grounded, so
    # the out-of-scope edit is flagged; the real `normalize` edit stays Authorized.
    precise = ground_seed(instr, BEFORE_P, AFTER_P, mode="precise")
    assert "result" not in precise.names, "precise should not ground the stop-word `result`"
    assert "normalize" in precise.names, "precise should still ground the distinctive `normalize`"

    fixed = audit_case(instr, BEFORE_P, AFTER_P, policy="P4", grounding_mode="precise")
    rf = [u for u in fixed.verdicts if u._raw_name == "result"]
    assert rf and rf[0].classification != Classification.AUTHORIZED, (
        "precise must NOT authorize the unrequested result edit"
    )
    assert rf[0].classification == Classification.VIOLATION, "out-of-scope result edit should be Violation"
    nf = [u for u in fixed.verdicts if u._raw_name == "normalize"]
    assert nf and nf[0].classification == Classification.AUTHORIZED, "requested normalize edit should stay Authorized"
    _assert_sound(fixed)
    print("  [P] precision: stop-word collision no longer false-authorizes out-of-scope creep (sound)")


# ---- R. recall: a morphological variant should still ground -----------------
BEFORE_R = "\n".join([
    "def serialize(record):",
    "    return str(record)",
    "",
    "def helper(x):",
    "    return x",
    "",
])
AFTER_R = "\n".join([
    "def serialize(record):",
    "    return repr(record)",   # the actually-requested change
    "",
    "def helper(x):",
    "    return x",
    "",
])


def test_recall_morphological_variant():
    instr = "improve the serializer"  # "serializer" -> function `serialize`

    # LEGACY misses: no exact token matches `serialize`, so the seed is empty
    # and the legitimate edit is flagged Violation (false flag).
    legacy = ground_seed(instr, BEFORE_R, AFTER_R, mode="legacy")
    assert "serialize" not in legacy.names, "setup: legacy should miss the morphological variant"
    base = audit_case(instr, BEFORE_R, AFTER_R, policy="P4")
    sl = [u for u in base.verdicts if u._raw_name == "serialize"]
    assert sl and sl[0].classification == Classification.VIOLATION, (
        "setup: legacy should false-flag the requested serialize edit"
    )

    # PRECISE grounds `serialize` via stemming (serializer -> serial <- serialize).
    precise = ground_seed(instr, BEFORE_R, AFTER_R, mode="precise")
    assert "serialize" in precise.names, "precise should recover the morphological match"
    assert "helper" not in precise.names, "recall must stay targeted (helper is unrelated)"

    fixed = audit_case(instr, BEFORE_R, AFTER_R, policy="P4", grounding_mode="precise")
    sf = [u for u in fixed.verdicts if u._raw_name == "serialize"]
    assert sf and sf[0].classification == Classification.AUTHORIZED, "requested serialize edit should be Authorized"
    _assert_sound(fixed)
    print("  [R] recall: morphological variant (serializer->serialize) now grounds; recall stays targeted")


# ---- N. no-regression: precise == legacy on clean fixtures ------------------
def test_no_regression_on_clean_cases():
    before = "\n".join([
        "def slugify(s):",
        "    return s.lower()",
        "",
        "def greet(name):",
        "    return 'hi ' + name",
        "",
    ])
    after = before.replace("'hi '", "'hello '")
    for instr in ("update the greet function", "update greet", "fix slugify"):
        leg = ground_seed(instr, before, after, mode="legacy").names
        pre = ground_seed(instr, before, after, mode="precise").names
        assert leg == pre, f"precise diverged from legacy on clean case {instr!r}: {leg} vs {pre}"

    # explicit quoting overrides the stop-word filter (deliberate reference)
    q = ground_seed("edit the `result` helper", BEFORE_P, AFTER_P, mode="precise").names
    assert "result" in q, "explicitly quoted `result` should ground even though it is a stop-word"
    print("  [N] no-regression: precise == legacy on clean fixtures; quoting overrides the filter")


if __name__ == "__main__":
    print("grounding precision/recall tests (weakness #8):")
    test_precision_stopword_collision()
    test_recall_morphological_variant()
    test_no_regression_on_clean_cases()
    print("ALL PASS")
