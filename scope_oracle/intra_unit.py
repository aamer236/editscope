"""Intra-unit smuggling detection (weakness #9) — OPT-IN statement-level units.

The frozen function-level partitioner has a known blind spot (plan §3.4): an
out-of-scope side effect SMUGGLED inside an otherwise seed-authorized function
(or method) rides along under that unit's seed warrant and is never flagged.

This module decomposes a seed-authorized function/method into statement-level
sub-units and surfaces *added, side-effecting* statements as their own units,
so the policy re-examines each one under the normal sound rule (seed ∪ W2;
else routed/flagged).

SYMBOLIC ONLY. No LLM, no execution. Conservative by construction: it only
ever EMITS extra candidate units (warrant NONE) — it never authorizes — so it
cannot break the soundness invariant. Default audit() granularity stays
"unit", so the validated single-file path is byte-for-byte unchanged; this runs
only when the caller opts into granularity="statement".

Coverage (what is surfaced as a candidate smuggle):
  * separable side-effecting statements in seed-authorized TOP-LEVEL functions
    (discarded calls like `log(x)` / `lst.append(y)`; attribute / subscript
    mutation like `obj.attr = ...`, `d[k] = ...`; rebinding a declared global);
  * the same, inside METHODS of a class — when either the method name or its
    enclosing class name is in the seed (in-class smuggles);
  * RETURN-FEEDING smuggles: a statement that performs one of the external
    side effects above is now surfaced even when its value also flows into the
    function's return (previously such statements were masked by the return
    backward-slice).

Out of scope (treated as no-finding, honest limits):
  * a side effect embedded directly inside a return / operand expression
    (e.g. `return lst.append(x) or value`) — not separable as its own line;
  * pure-local dead code that never escapes the frame (no external write,
    no return contribution);
  * control-flow-entangled creep woven through branches/loops.

Precision note: seed grounding is NAME-level, not semantic, so statement mode
can over-surface a side effect the instruction legitimately asked for (it has
no way to know `append` was authorized). It therefore trades precision for
recall and only ever raises *candidates* for review — it never authorizes.
Downgrades weakness #9, does not close it.
"""
from __future__ import annotations

import ast


def _reads(node: ast.AST) -> set:
    out: set = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def _has_side_effect(stmt: ast.stmt, global_names: set) -> bool:
    """True if the statement mutates state observable outside its own locals."""
    # discarded expression that is a call, e.g. log_to_server(x), lst.append(y)
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        return True
    # assignment/aug-assign whose target is an attribute or subscript -> mutates
    # an aliased / external object (self.x = ..., obj.attr = ..., d[k] = ...)
    targets = []
    if isinstance(stmt, ast.Assign):
        targets = list(stmt.targets)
    elif isinstance(stmt, (ast.AugAssign, ast.AnnAssign)):
        targets = [stmt.target]
    for t in targets:
        if isinstance(t, (ast.Attribute, ast.Subscript)):
            return True
        if isinstance(t, ast.Name) and t.id in global_names:
            return True  # rebinding a declared global/nonlocal
    return False


def _func_global_names(fn: ast.AST) -> set:
    out: set = set()
    for n in ast.walk(fn):
        if isinstance(n, (ast.Global, ast.Nonlocal)):
            out.update(n.names)
    return out


def _body_stmt_strings(body: list) -> list:
    return [ast.dump(s) for s in body]


def _iter_target_funcs(tree: ast.Module, seed_names: set):
    """Yield (func_node, qualname) for functions whose smuggles should surface.

    Targets are seed-authorized callables:
      * a TOP-LEVEL function whose name is in the seed;
      * a METHOD whose own name is in the seed, OR whose enclosing class name
        is in the seed (so a smuggle inside a seed-authorized class is caught).
    """
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name in seed_names:
                yield node, node.name
        elif isinstance(node, ast.ClassDef):
            class_seeded = node.name in seed_names
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if class_seeded or sub.name in seed_names:
                        yield sub, f"{node.name}.{sub.name}"


def _before_bodies(before_tree) -> dict:
    """Map qualname -> statement body for every before-side function/method."""
    out: dict = {}
    if before_tree is None:
        return out
    for node in before_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node.body
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[f"{node.name}.{sub.name}"] = sub.body
    return out


def find_smuggles(after_src: str, before_src: str, seed_names: set) -> list:
    """Return smuggle records for seed-authorized functions and methods.

    Each record: {name, lineno, end_lineno, loc, reverted_src} where `name` is
    the qualified owner (`func` or `Class.method`) and `reverted_src` is
    `after_src` with exactly the smuggled statement removed (so the W2 resolver
    / W1 router can evaluate it via the normal sound path).
    """
    try:
        after_tree = ast.parse(after_src)
    except SyntaxError:
        return []
    try:
        before_tree = ast.parse(before_src)
    except SyntaxError:
        before_tree = None

    before_bodies = _before_bodies(before_tree)
    after_lines = after_src.splitlines()
    records: list = []
    for fn, qualname in _iter_target_funcs(after_tree, seed_names):
        before_pool = list(_body_stmt_strings(before_bodies.get(qualname, [])))
        global_names = _func_global_names(fn)
        for stmt in fn.body:
            d = ast.dump(stmt)
            # statement present unchanged in the before-body is not "added"
            if d in before_pool:
                before_pool.remove(d)
                continue
            # reads a seed name -> treat as part of the authorized seed work
            if _reads(stmt) & seed_names:
                continue
            # only surface statements with an EXTERNAL side effect. A statement
            # is surfaced even when its value also feeds the return value
            # (return-feeding smuggle); a non-side-effecting return-relevant or
            # pure-local statement is legitimate and skipped.
            if not _has_side_effect(stmt, global_names):
                continue
            start = getattr(stmt, "lineno", None)
            end = getattr(stmt, "end_lineno", start)
            if start is None:
                continue
            reverted_lines = after_lines[: start - 1] + after_lines[end:]
            reverted_src = "\n".join(reverted_lines)
            if after_src.endswith("\n"):
                reverted_src += "\n"
            records.append({
                "name": qualname,
                "lineno": start,
                "end_lineno": end,
                "loc": end - start + 1,
                "reverted_src": reverted_src,
            })
    return records
