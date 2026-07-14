#!/usr/bin/env bash
# EditScope container entrypoint - dispatches demo/run modes.
# Usage: docker run --rm editscope:0.1.0 [MODE] [args...]
set -euo pipefail

mode="${1:-freeze}"

run_freeze() {
  echo "== EditScope frozen oracle suite ========================================="
  echo "   soundness invariants + cross-file W2 + intra-unit hardening + grounding"
  echo "   (no dataset, no network required)"
  echo "==========================================================================="
  python -m scope_oracle.tests.test_audit_freeze
  python -m scope_oracle.tests.test_intra_unit_hardening
  python -m scope_oracle.tests.test_grounding_precision
  echo "== all frozen suites passed ==============================================="
}

case "$mode" in
  freeze)
    run_freeze
    ;;
  parity)
    # CanItEdit parity slice. Bind-mount the dataset to $CANITEDIT_DIR.
    shift || true
    exec python -m scope_oracle.parity_real --data "${CANITEDIT_DIR:-/data/canitedit}" "$@"
    ;;
  track-a)
    # Track A agent harness. Default agent (dry_run) needs no key/network.
    # For live models: docker run -e GROQ_API_KEY=... editscope track-a \
    #   --agent groq --model llama-3.1-8b-instant --data "$CANITEDIT_DIR"
    shift || true
    exec python -m track_a.run_agents "$@"
    ;;
  version)
    exec python -c "import scope_oracle, sys; print('editscope', getattr(scope_oracle,'__version__','0.1.0'), 'on', sys.version.split()[0])"
    ;;
  bash|sh|shell)
    exec bash
    ;;
  *)
    # Passthrough: run any arbitrary command, e.g.
    #   docker run --rm editscope python -m track_a.summarize --runs ...
    exec "$@"
    ;;
esac
