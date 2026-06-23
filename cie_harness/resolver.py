import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path


def _write(src: str, stem: str) -> Path:
    d = Path(tempfile.mkdtemp(prefix="cie_audit_"))
    p = d / f"{stem}.py"
    p.write_text("import sys\nsys.dont_write_bytecode = True\n" + src, encoding="utf-8")
    return p


def check(src: str, stem: str = "case") -> dict:
    p = _write(src, stem)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    out = {"compile_ok": True, "pyflakes_ok": True, "mypy_ok": None, "messages": []}
    try:
        py_compile.compile(str(p), doraise=True)
    except py_compile.PyCompileError as exc:
        out["compile_ok"] = False
        out["messages"].append(str(exc))
    pf = subprocess.run([sys.executable, "-m", "pyflakes", str(p)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=20)
    out["pyflakes_ok"] = pf.returncode == 0
    if pf.stdout:
        out["messages"].append(pf.stdout)
    try:
        my = subprocess.run([sys.executable, "-m", "mypy", "--strict", str(p)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, timeout=40)
        if "No module named mypy" not in my.stdout and my.returncode != 1_000:
            out["mypy_ok"] = my.returncode == 0
            if my.stdout:
                out["messages"].append(my.stdout)
    except subprocess.TimeoutExpired:
        out["mypy_ok"] = None
        out["messages"].append("mypy timed out; treating as inconclusive")
    return out


def newly_broken(base: dict, variant: dict) -> bool:
    return (base.get("compile_ok") and not variant.get("compile_ok")) or (base.get("pyflakes_ok") and not variant.get("pyflakes_ok")) or (base.get("mypy_ok") is True and variant.get("mypy_ok") is False)
