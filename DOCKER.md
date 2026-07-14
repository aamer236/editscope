# EditScope - Docker

A reproducible container for the EditScope scope oracle. The canonical oracle is
pure-Python (optional `pyflakes` + `mypy` sharpen the W2 resolver), CPU-only, and
the **frozen soundness suite runs with no dataset and no network** - ideal for a
grading machine.

## Files
| File | Purpose |
|------|---------|
| `Dockerfile` | Builds the image; runs the frozen suite as a build gate. |
| `.dockerignore` | Keeps the build context small and deterministic. |
| `docker/entrypoint.sh` | Dispatches `freeze` / `parity` / `track-a` / passthrough modes. |
| `docker-compose.yml` | Optional convenience wrapper with dataset/key wiring. |

Drop all four into the **repo root** (with `entrypoint.sh` under `docker/`).

## Build
```bash
docker build -t editscope:0.1.0 .
```
The build itself runs the three frozen test modules, so a successful build *is*
proof the soundness invariants hold.

## Run

### 1. Frozen soundness suite (default; offline)
```bash
docker run --rm editscope:0.1.0
# equivalently: docker run --rm editscope:0.1.0 freeze
```

### 2. CanItEdit parity slice (offline; needs the pinned dataset)
Fetch the dataset once on the host (`python -m track_a.fetch_canitedit` -> `./canitedit`),
then bind-mount it:
```bash
docker run --rm -v "$PWD/canitedit:/data/canitedit:ro" editscope:0.1.0 \
  parity --limit 102
```

### 3. Track A - dry run (offline, replays gold edits, no key)
```bash
docker run --rm \
  -v "$PWD/canitedit:/data/canitedit:ro" \
  -v "$PWD/results_track_a:/app/results_track_a" \
  editscope:0.1.0 \
  track-a --agent dry_run --data /data/canitedit --limit 3
```

### 4. Track A - live model (needs network + key)
Live agents call the OpenAI-compatible Groq endpoint and import `openai` lazily,
so install it at build time (uncomment the line in the Dockerfile or `pip install
openai` in a derived image) and pass the key:
```bash
docker run --rm -e GROQ_API_KEY="$GROQ_API_KEY" \
  -v "$PWD/canitedit:/data/canitedit:ro" \
  -v "$PWD/results_track_a:/app/results_track_a" \
  editscope:0.1.0 \
  track-a --agent groq --model llama-3.1-8b-instant --data /data/canitedit --limit 20
```

### 5. Any other command (passthrough)
```bash
docker run --rm -v "$PWD/results_track_a:/app/results_track_a" editscope:0.1.0 \
  python -m track_a.summarize --runs results_track_a/runs_rescored.jsonl
```

## Notes
- **Scope:** this image ships the oracle + Track A analysis pipeline. Track C
  (DPO / QLoRA on Qwen-Coder) is intentionally excluded - it needs a GPU and a
  heavy ML stack, which does not belong in the reproducible-oracle deliverable.
- **Live models** require `openai` in the image. The base image keeps only the
  soft deps (`pyflakes`, `mypy`); add `openai` only if you need modes 4.
- Runs as non-root user `editscope` (uid 1000); mounted output dirs stay writable.
- Python is pinned to 3.13 to match `pyproject.toml` (`requires-python >=3.13`)
  and the CI matrix.
