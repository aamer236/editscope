"""
reward.py

EditScope reward adapter.

This file converts EditScope's AuditResult into a scalar reward
that can be used for:

    • Best-of-N ranking
    • Preference pair generation
    • DPO

The oracle remains the source of truth.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from scope_oracle.audit import audit_case
from scope_oracle.schema import Classification


class EditScopeReward:
    """
    Thin wrapper around EditScope's oracle.

    The oracle performs the reasoning.

    This class only converts AuditResult into
    a scalar reward.
    """

    def __init__(
        self,
        violation_weight: float = 1.0,
        uncertain_weight: float = 0.5,
        loc_penalty: float = 0.01,
        block_penalty: float = 0.05,
    ):

        self.violation_weight = violation_weight
        self.uncertain_weight = uncertain_weight
        self.loc_penalty = loc_penalty
        self.block_penalty = block_penalty

    # ----------------------------------------------------------

    def _summarize(self, audit):

        verdicts = audit.verdicts

        total = len(verdicts)

        authorized = 0
        violations = 0
        uncertain = 0

        seed_overlap = 0.0

        for v in verdicts:

            if v.classification == Classification.AUTHORIZED:
                authorized += 1

            elif v.classification == Classification.VIOLATION:
                violations += 1

            else:
                uncertain += 1

            seed_overlap += v.seed_overlap

        if total:
            seed_overlap /= total

        return {

            "total_units": total,

            "authorized": authorized,

            "violations": violations,

            "uncertain": uncertain,

            "authorized_rate": authorized / max(total, 1),

            "violation_rate": violations / max(total, 1),

            "uncertain_rate": uncertain / max(total, 1),

            "seed_overlap": seed_overlap,

            "metric_card": asdict(audit.metric_card),
        }

    # ----------------------------------------------------------

    def _compute_reward(self, summary):

        reward = summary["authorized_rate"]

        reward -= (
            self.violation_weight
            * summary["violation_rate"]
        )

        reward -= (
            self.uncertain_weight
            * summary["uncertain_rate"]
        )

        reward += (
            0.20
            * summary["seed_overlap"]
        )

        reward -= (
            self.loc_penalty
            * summary["metric_card"]["extra_edit_loc"]
        )

        reward -= (
            self.block_penalty
            * summary["metric_card"]["extra_edit_blocks"]
        )

 sys.path.append("/kaggle/working/editscope_dpo")
       reward = max(-1.0, min(1.0, reward))

        return reward

    # ----------------------------------------------------------

    def score(
        self,
        instruction: str,
        before: str,
        after: str,
        tests: Optional[str] = None,
    ):

        audit = audit_case(
            instruction=instruction,
            before=before,
            after=after,
            tests=tests,
        )

        summary = self._summarize(audit)

        reward = self._compute_reward(summary)

        return {

            "reward": reward,

            "summary": summary,

            "audit": audit,
        }
