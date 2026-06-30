"""Track A - offline re-score (P3). Replay cached agent patches through the CURRENT scope_oracle.
Zero model calls. Reads results_track_a/*.jsonl, re-audits each cached patch with the installed
oracle, writes <name>_rescored.jsonl with the identical row schema. Run from repo root:
    python -m track_a.rescore --data ./canitedit --runs results_track_a/groq_llama8b.jsonl ...
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

from track_a.run_agents import load_cases, run_case, ID_EXCLUDE


def _load_jsonl(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)


def _index_cases(data_root: Path) -> dict:
    return {c["problem_id"]: c for c in load_cases(data_root)}


def _cached_patches(rows) -> dict:
    """problem_id -> (raw_patch, model, prompt_style, temperature) from the first row per problem."""
    seen = {}
    for r in rows:
        pid = str(r.get("problem_id"))
        if pid not in seen:
            seen[pid] = (r.get("raw_patch"), r.get("model", "unknown"),
                         r.get("prompt_style", "neutral"), r.get("temperature", 0.0))
    return seen


def rescore_file(in_path: Path, out_path: Path, cases: dict):
    patches = _cached_patches(_load_jsonl(in_path))
    out_rows, n_ok, n_skip = [], 0, 0
    for pid, (raw_patch, model, style, temp) in patches.items():
        if pid in ID_EXCLUDE:
            continue
        case = cases.get(pid)
        if case is None:
            print(f"  [skip] {pid}: not in dataset"); n_skip += 1; continue
        if not raw_patch:
            print(f"  [skip] {pid}: empty raw_patch"); n_skip += 1; continue
        out_rows.extend(run_case(case, raw_patch, model, style, temp))
        n_ok += 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for row in out_rows:
            f.write(json.dumps(row) + "\n")
    print(f"  rescored {n_ok} problem(s), {n_skip} skipped -> {out_path}  ({len(out_rows)} rows)")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="track_a.rescore",
        description="Replay cached agent patches through the current scope_oracle (no model calls).")
    ap.add_argument("--data", default="./canitedit")
    ap.add_argument("--runs", nargs="+", required=True)
    ap.add_argument("--suffix", default="_rescored")
    args = ap.parse_args(argv)

    cases = _index_cases(Path(args.data))
    print(f"loaded {len(cases)} dataset cases from {args.data}")
    for run in args.runs:
        in_path = Path(run)
        out_path = in_path.with_name(in_path.stem + args.suffix + in_path.suffix)
        print(f"re-scoring {in_path.name} ...")
        rescore_file(in_path, out_path, cases)


if __name__ == "__main__":
    main()
