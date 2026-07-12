"""
oracle_probe.py

Purpose:
    Reverse engineer the EditScope oracle API.

Run:

    python oracle_probe.py
"""

from __future__ import annotations

import inspect
import traceback
from dataclasses import asdict, is_dataclass
from pprint import pprint
from pathlib import Path
import sys


# ============================================================
# Make repository importable
# ============================================================

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ============================================================
# Helpers
# ============================================================

def banner(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def dump_object(obj, depth=0):

    indent = "    " * depth

    print(f"{indent}TYPE : {type(obj)}")

    try:
        print(f"{indent}REPR :")
        print(indent + repr(obj))
    except Exception:
        pass

    if hasattr(obj, "__dict__"):
        print(f"\n{indent}__dict__")
        pprint(obj.__dict__)

    if is_dataclass(obj):
        print(f"\n{indent}DATACLASS")
        pprint(asdict(obj))


# ============================================================
# Main
# ============================================================

def main():

    banner("Repository")
    print(REPO_ROOT)

    banner("Importing oracle")

    try:
        from scope_oracle.audit import audit

        print("SUCCESS : scope_oracle.audit")
        print(inspect.getmodule(audit))

    except Exception:

        banner("Import failed")
        traceback.print_exc()
        return

    banner("audit() signature")
    print(inspect.signature(audit))

    banner("Calling oracle")

    instruction = "Rename foo to bar."

    repo_before = {
        "main.py": """
def foo():
    return 1
"""
    }

    patch = {
        "main.py": """
def bar():
    return 1
"""
    }

    try:

        result = audit(
            instruction=instruction,
            repo_before=repo_before,
            patch=patch,
        )

        banner("RESULT")

        dump_object(result)

        if hasattr(result, "__dict__"):

            banner("Nested fields")

            for key, value in result.__dict__.items():

                print(f"\n{key}")

                dump_object(value, 1)

    except Exception:

        banner("audit() raised")
        traceback.print_exc()


if __name__ == "__main__":
    main()
