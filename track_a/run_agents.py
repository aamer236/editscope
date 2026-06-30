"""Track A - single-turn agent benchmark harness (P3). Calls FROZEN scope_oracle only."""
from __future__ import annotations
import argparse, json, os, time
from pathlib import Path

from scope_oracle import audit_case
from scope_oracle.resolver import _run_tests_src

ID_EXCLUDE    = {"78"}
POLICIES      = ["P1", "P4"]
GRANULARITIES = ["unit", "statement"]

PROMPTS = {
    "neutral": ("You are a code-editing assistant. Apply the requested change. "
                "Return the COMPLETE edited file in ONE python code block, no prose."),
    "scope":   ("You are a code-editing assistant. Apply ONLY the requested change and NOTHING else. "
                "Do NOT refactor, rename, reformat, add comments, or modify any code the instruction "
                "does not explicitly require. Return the COMPLETE edited file in ONE python code block, no prose."),
}

def _load_jsonl(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)

def load_cases(root: Path):
    files = list(root.rglob("*.jsonl")) + list(root.rglob("*.json"))
    for f in files:
        try:
            rows = list(_load_jsonl(f)) if f.suffix == ".jsonl" else json.loads(f.read_text(encoding="utf-8"))
            if isinstance(rows, dict):
                rows = rows.get("data") or rows.get("examples") or []
            for i, row in enumerate(rows):
                b, a = row.get("before"), row.get("after")
                instr = (row.get("instruction_descriptive") or row.get("instruction_lazy")
                         or row.get("descriptive") or row.get("instruction"))
                pid = str(row.get("id", f"{f.name}:{i}"))
                if b and instr and pid not in ID_EXCLUDE:
                    yield {"problem_id": pid, "before": b, "gold_after": a,
                           "prompt": instr, "tests": row.get("tests", "")}
        except Exception:
            continue

_LANG_TAGS = {"python", "py", "python3", "python2"}

def _extract_code(text: str) -> str:
    if not text:
        return ""
    if "```" not in text:
        return text.strip()
    parts = text.split("```")
    body = parts[1] if len(parts) > 1 else text
    lines = body.split("\n")
    if lines and lines[0].strip().lower() in _LANG_TAGS:
        lines = lines[1:]
    return "\n".join(lines).strip("\n")

def _chat_edit(client, model, temperature, case, prompt_style, retries=5):
    sys = PROMPTS.get(prompt_style, PROMPTS["neutral"])
    user = f"# Instruction\n{case['prompt']}\n\n# File to edit\n```python\n{case['before']}\n```"
    for attempt in range(retries):
        try:
            r = client.chat.completions.create(model=model, temperature=temperature,
                messages=[{"role": "system", "content": sys}, {"role": "user", "content": user}])
            return _extract_code(r.choices[0].message.content or "")
        except Exception as exc:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt
            print(f"   (retry {attempt+1}/{retries} in {wait}s: {type(exc).__name__})")
            time.sleep(wait)

# ---- agents -------------------------------------------------------------
def agent_dry_run(case, **kw):
    return case["gold_after"]

def agent_openai(case, *, model="gpt-4o", temperature=0.0, prompt_style="neutral", **kw):
    from openai import OpenAI
    return _chat_edit(OpenAI(), model, temperature, case, prompt_style)

def agent_groq(case, *, model="llama-3.3-70b-versatile", temperature=0.0, prompt_style="neutral", **kw):
    from openai import OpenAI
    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.environ["GROQ_API_KEY"])
    return _chat_edit(client, model, temperature, case, prompt_style)

AGENTS = {"dry_run": agent_dry_run, "openai": agent_openai, "groq": agent_groq}

# ---- run + log ----------------------------------------------------------
def run_case(case, agent_after, model_name, prompt_style, temperature):
    rows = []
    gold_pass  = bool(_run_tests_src(case["gold_after"], case["tests"])) if case["gold_after"] else None
    agent_pass = bool(_run_tests_src(agent_after, case["tests"])) if agent_after else None
    for pol in POLICIES:
        for gran in GRANULARITIES:
            res = audit_case(case["prompt"], case["before"], agent_after,
                             tests=case["tests"] or None, policy=pol, granularity=gran)
            rows.append({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "model": model_name, "prompt_style": prompt_style, "temperature": temperature,
                "problem_id": case["problem_id"], "policy": pol, "granularity": gran,
                "gold_pass": gold_pass, "agent_pass": agent_pass,
                "raw_patch": agent_after,
                "audit": res.to_json(),
            })
    return rows

def main(argv=None):
    ap = argparse.ArgumentParser(prog="track_a.run_agents")
    ap.add_argument("--data", default="./canitedit")
    ap.add_argument("--agent", choices=list(AGENTS), default="dry_run")
    ap.add_argument("--model", default="gold")
    ap.add_argument("--prompt-style", choices=list(PROMPTS), default="neutral")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds to wait between problems")
    ap.add_argument("--out", default="results_track_a/runs.jsonl")
    args = ap.parse_args(argv)

    agent_fn = AGENTS[args.agent]
    out = Path(args.out); out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out, "w", encoding="utf-8") as f:
        for case in load_cases(Path(args.data)):
            if n >= args.limit:
                break
            try:
                after = agent_fn(case, model=args.model, temperature=args.temperature,
                                 prompt_style=args.prompt_style)
            except Exception as exc:
                print(f"[skip] {case['problem_id']}: agent failed: {exc}")
                continue
            for row in run_case(case, after, args.model, args.prompt_style, args.temperature):
                f.write(json.dumps(row) + "\n")
            n += 1
            print(f"[ok] {case['problem_id']} -> logged ({args.agent}/{args.model}/{args.prompt_style})  [{n}]")
            if args.sleep:
                time.sleep(args.sleep)
    print(f"\nwrote {n} problem(s) x {len(POLICIES)*len(GRANULARITIES)} rows -> {out}")

if __name__ == "__main__":
    main()
