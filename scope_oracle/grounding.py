"""Seed grounding (what the instruction authorizes).

Ports the VALIDATED cie_harness grounding (token ∩ AST-name extraction) and
exposes ground_seed(...) in the shape the audit() orchestration expects.

Weakness #8 hardening (OPT-IN, default unchanged)
-------------------------------------------------
Grounding is NAME-level: the seed is the set of code identifiers the instruction
names. The validated extractor (`mode="legacy"`) is a plain token ∩ AST-name
intersection. It has two well-understood accuracy failures:

  * FALSE GROUND (precision / SOUNDNESS risk): a common English or generic
    programming word in the instruction ("update", "result", "list", "data")
    coincides with a real identifier, so an UN-requested edit to that identifier
    gets seed-authorized. Because seed => Authorized, this is the dangerous
    direction: it can silently authorize out-of-scope creep.

  * MISSED GROUND (recall): the instruction refers to a target by a
    morphological variant ("the serializer" for `serialize`, "greeting helper"
    for `greet`), so a legitimately-requested edit is flagged Violation.

`mode="precise"` addresses both, conservatively:

  1. Stop-word / common-word filter (precision, soundness-improving): a bare
     unquoted token only grounds when it is a DISTINCTIVE identifier
     (snake_case, camelCase, contains a digit, or a non-stopword word >= 4
     chars). Generic words never ground on their own. Removing names only ever
     makes the oracle MORE conservative, so this strictly helps soundness.
     Explicitly quoted/backticked identifiers always ground (deliberate
     reference), even if they are stopwords.

  2. Morphological recall (reduces false Violation flags): instruction tokens
     are light-stemmed and matched against the stems of DISTINCTIVE code names
     (and their snake/camel sub-tokens). Restricting to distinctive names keeps
     this from grounding generic-word collisions. This direction adds names, so
     it is a precision/recall trade rather than a soundness improvement; it is
     bounded to high-confidence distinctive matches and stays opt-in.

The default path (`mode="legacy"`) is byte-for-byte the validated extractor, so
the frozen audit() contract and the validated n=104 metrics are untouched.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Union

from .partitioner import _all_sources, _primary_source

RepoBefore = Union[str, dict]


@dataclass
class Grounding:
    names: set[str]
    confidence: float
    missed: bool


_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_QUOTED = re.compile(r"[`'\"]([A-Za-z_][A-Za-z0-9_]*)[`'\"]")


def code_names(src: str) -> set[str]:
    names: set[str] = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return names
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


# --------------------------------------------------------------------------
# precise-mode helpers (weakness #8)
# --------------------------------------------------------------------------
# Common English + generic-programming words that frequently appear in editing
# instructions. On their own they must NOT ground a seed -- when they coincide
# with a real identifier they cause false authorizations.
_STOPWORDS = frozenset({
    # articles / conjunctions / prepositions / pronouns / aux
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "when", "while",
    "for", "of", "to", "in", "on", "at", "by", "with", "without", "from", "into",
    "onto", "as", "is", "are", "be", "been", "being", "was", "were", "it", "its",
    "this", "that", "these", "those", "they", "them", "their", "there", "here",
    "we", "you", "do", "does", "done", "not", "no", "yes", "so", "such", "than",
    "too", "very", "only", "both", "either", "neither",
    # generic edit verbs
    "make", "makes", "set", "sets", "get", "gets", "add", "adds", "added",
    "remove", "removes", "removed", "update", "updates", "updated", "change",
    "changes", "changed", "fix", "fixes", "fixed", "use", "uses", "used",
    "using", "create", "creates", "created", "ensure", "ensures", "handle",
    "handles", "handled", "support", "supports", "return", "returns",
    "returned", "call", "calls", "called", "allow", "allows", "please",
    "should", "must", "need", "needs", "want", "wants", "also", "now", "just",
    "improve", "improves", "improved", "refactor", "rename", "move", "keep",
    # generic programming nouns
    "function", "functions", "func", "method", "methods", "class", "classes",
    "code", "file", "files", "line", "lines", "value", "values", "val", "data",
    "item", "items", "list", "lists", "dict", "dicts", "set", "sets", "type",
    "types", "id", "ids", "name", "names", "arg", "args", "argument",
    "arguments", "param", "params", "parameter", "parameters", "result",
    "results", "output", "outputs", "input", "inputs", "key", "keys", "field",
    "fields", "object", "objects", "new", "old", "all", "any", "each", "every",
    "some", "none", "null", "true", "false", "str", "int", "float", "bool",
    "number", "string", "text", "case", "cases", "test", "tests", "error",
    "errors", "message", "messages", "logic", "behavior", "behaviour",
})

# Longest-first so the most specific suffix is stripped.
_SUFFIXES = (
    "ization", "isation",
    "izer", "iser", "izes", "ises", "ized", "ised", "izing", "ising",
    "ize", "ise",
    "tions", "sions", "ments",
    "tion", "sion", "ment", "ness",
    "ings", "ing",
    "ers", "ors", "er", "or",
    "ies", "es", "ed", "ly", "s",
)


def _is_distinctive(name: str) -> bool:
    """True if `name` is specific enough to ground from a bare unquoted token.

    Distinctive = snake_case, camelCase/PascalCase, contains a digit, or a
    non-stopword word of >= 4 chars. Generic short/common words are NOT
    distinctive and require an explicit quote (or a morphological match) to
    ground.
    """
    if "_" in name:
        return True
    if any(c.isupper() for c in name) and any(c.islower() for c in name):
        return True
    if any(c.isdigit() for c in name):
        return True
    return name.lower() not in _STOPWORDS and len(name) >= 4


def _stem(tok: str) -> str:
    t = tok.lower()
    for suf in _SUFFIXES:
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            base = t[: -len(suf)]
            if suf == "ies":
                base += "y"
            return base
    return t


def _split_identifier(name: str) -> list[str]:
    """Split snake_case and camelCase/PascalCase into sub-tokens."""
    out: list[str] = []
    for part in name.split("_"):
        cur = ""
        for ch in part:
            if ch.isupper() and cur and not cur[-1].isupper():
                out.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            out.append(cur)
    return [o for o in out if o]


def _legacy_names(text: str, known: set[str]) -> tuple[set[str], set[str]]:
    raw = set(_WORD.findall(text or ""))
    quoted = set(_QUOTED.findall(text or ""))
    return (raw | quoted) & known, quoted


def _precise_names(text: str, known: set[str]) -> tuple[set[str], set[str]]:
    raw = set(_WORD.findall(text or ""))
    quoted = set(_QUOTED.findall(text or ""))

    # 1) Explicit quoted/backticked references always ground (even stopwords).
    names: set[str] = set(quoted & known)

    # 2) Bare exact-token matches ONLY for distinctive identifiers.
    for tok in raw:
        if tok in known and _is_distinctive(tok):
            names.add(tok)

    # 3) Conservative morphological recall against distinctive code names.
    instr_stems = {_stem(t) for t in raw if t.lower() not in _STOPWORDS and len(t) >= 3}
    if instr_stems:
        for cn in known:
            if cn in names or not _is_distinctive(cn):
                continue
            cn_stems = {_stem(cn)} | {_stem(p) for p in _split_identifier(cn) if len(p) >= 3}
            if cn_stems & instr_stems:
                names.add(cn)

    return names, quoted


def _confidence(names: set[str], quoted: set[str], known: set[str]) -> float:
    if not names:
        return 0.0
    return min(1.0, 0.45 + 0.1 * len(names) + (0.25 if (quoted & known) else 0.0))


def _resolve(text: str, known: set[str], mode: str) -> tuple[set[str], set[str]]:
    if mode == "precise":
        return _precise_names(text, known)
    if mode not in ("legacy", "precise"):
        raise ValueError(f"unknown grounding mode: {mode!r} (expected 'legacy' or 'precise')")
    return _legacy_names(text, known)


def extract(prompt: str, src: str, mode: str = "legacy") -> Grounding:
    known = code_names(src)
    names, quoted = _resolve(prompt, known, mode)
    return Grounding(names=names, confidence=_confidence(names, quoted, known), missed=not bool(names))


def ground_seed(
    instruction: str,
    repo_before: RepoBefore,
    patch: str,
    mode: str = "legacy",
) -> Grounding:
    """Grounds the instruction against the PRE-edit source (the before).

    Grounding deliberately uses the before-source: the seed is what the
    instruction names in the code that already exists.

    mode="legacy" (default): the VALIDATED token ∩ AST-name extractor. Frozen.
    mode="precise": opt-in weakness-#8 hardening (stop-word filtering +
        conservative morphological recall). See module docstring.
    """
    sources = _all_sources(repo_before)
    known: set = set()
    for src in sources.values():
        known |= code_names(src)
    names, quoted = _resolve(instruction, known, mode)
    return Grounding(names=names, confidence=_confidence(names, quoted, known), missed=not bool(names))
