"""Re-exports the CANONICAL frozen resolver so cie_harness shares identical W2
semantics. Previously this file held a duplicate check()/newly_broken() with the
pre-fix pyflakes logic, which could spuriously fire W2 on 'unused'-class lint left
by a revert. Re-exporting eliminates that drift."""
from scope_oracle.resolver import check, newly_broken  # noqa: F401