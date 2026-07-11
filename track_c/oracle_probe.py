"""
oracle_probe.py

Purpose:
    Reverse engineer the EditScope oracle API.

Run:

python oracle_probe.py
"""

import os
import sys
import inspect
import traceback
from pprint import pprint
from dataclasses import is_dataclass, asdict


# ============================================================
# CONFIG
# ============================================================

# Change this if necessary.
REPO_ROOT = "/kaggle/input/datasets/aamer236/editscope/editscope-main"


# ============================================================
# Helpers
# ============================================================

def banner(title):
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


def locate_audit_module():

    banner("Searching for audit.py")

    candidates = []

    for root, _, files in os.walk(REPO_ROOT):

        if "audit.py" in files:

            path = os.path.join(root, "audit.py")

            print(path)

            candidates.append(path)

    return candidates


# ============================================================
# Main
# ============================================================

def main():

    banner("Repository")

    print(REPO_ROOT)

    if not os.path.exists(REPO_ROOT):

        print("Repository not found!")

        return

    sys.path.insert(0, REPO_ROOT)

    locate_audit_module()

    banner("Trying imports")

    audit = None

    import_attempts = [

        "scope_oracle.audit",
        "editscope.audit",
        "audit",

    ]

    for module_name in import_attempts:

        try:

            module = __import__(module_name, fromlist=["audit"])

            print(f"SUCCESS : {module_name}")

            print(module)

            if hasattr(module, "audit"):

                audit = module.audit

                break

        except Exception as e:

            print(f"FAILED : {module_name}")

            print(e)

    if audit is None:

        banner("Could not import audit()")

        print("Available python packages:\n")

        for root, dirs, files in os.walk(REPO_ROOT):

            level = root.replace(REPO_ROOT, "").count(os.sep)

            if level > 2:
                continue

            print("    " * level + os.path.basename(root))

            for f in files:

                if f.endswith(".py"):

                    print("    " * (level + 1) + f)

        return

    banner("audit() signature")

    print(inspect.signature(audit))

    banner("audit() source")

    print(inspect.getmodule(audit))

    banner("Calling oracle")

    #
    # Dummy inputs.
    #
    # We EXPECT this to fail.
    #
    # We only care about:
    #
    #   • required parameters
    #   • returned object
    #   • exception message
    #

    instruction = "Rename foo to bar."

    repo_before = {
        "main.py":
"""
def foo():
    return 1
"""
    }

    patch = {
        "main.py":
"""
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

            for k, v in result.__dict__.items():

                print(f"\n{k}")

                dump_object(v, 1)

    except Exception:

        banner("audit() raised")

        traceback.print_exc()


if __name__ == "__main__":

    main()