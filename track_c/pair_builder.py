"""
pair_builder.py

This module:

1. Generates candidate edits
2. Scores them with the EditScope oracle
3. Ranks them
4. Builds DPO preference pairs
"""

from __future__ import annotations

import json
from typing import List

from candidate_generator import Candidate, CandidateGenerator
from reward import EditScopeReward

class PairBuilder:

    def __init__(
        self,
        generator: CandidateGenerator,
        reward_model: EditScopeReward,
        reward_gap: float = 0.10,
    ):
        self.generator = generator
        self.reward_model = reward_model
        self.reward_gap = reward_gap

    # ------------------------------------------------------------

    def score_candidates(
        self,
        instruction: str,
        before_code: str,
        candidates: List[Candidate],
        tests: str | None = None,
    ) -> List[Candidate]:

        for candidate in candidates:

            result = self.reward_model.score(
                instruction=instruction,
                before=before_code,
                after=candidate.code,
                tests=tests,
            )

            candidate.reward = result["reward"]
            candidate.summary = result["summary"]
            candidate.audit = result["audit"]

        candidates.sort(
            key=lambda c: c.reward,
            reverse=True,
        )

        return candidates

    # ------------------------------------------------------------

    def generate_ranked_candidates(
        self,
        instruction: str,
        before_code: str,
        tests: str | None = None,
        num_candidates: int = 8,
    ) -> List[Candidate]:

        candidates = self.generator.generate(
            instruction=instruction,
            before_code=before_code,
            num_candidates=num_candidates,
        )

        return self.score_candidates(
            instruction=instruction,
            before_code=before_code,
            candidates=candidates,
            tests=tests,
        )

    # ------------------------------------------------------------

    def build_pairs(
        self,
        instruction: str,
        before_code: str,
        tests: str | None = None,
        num_candidates: int = 8,
    ):

        ranked = self.generate_ranked_candidates(
            instruction=instruction,
            before_code=before_code,
            tests=tests,
            num_candidates=num_candidates,
        )

        pairs = []

        n = len(ranked)

        for i in range(n):

            for j in range(i + 1, n):

                chosen = ranked[i]
                rejected = ranked[j]

                if (
                    chosen.reward - rejected.reward
                    < self.reward_gap
                ):
                    continue

                pairs.append(
                    {
                        "prompt": instruction,
                        "chosen": chosen.code,
                        "rejected": rejected.code,
                        "chosen_reward": chosen.reward,
                        "rejected_reward": rejected.reward,
                        "chosen_summary": chosen.summary,
                        "rejected_summary": rejected.summary,
                        "chosen_id": chosen.candidate_id,
                        "rejected_id": rejected.candidate_id,
                    }
                )

        return ranked, pairs

    # ------------------------------------------------------------

    def save_pairs(
        self,
        pairs,
        output_file,
    ):

        with open(output_file, "w", encoding="utf-8") as f:

            for pair in pairs:
                f.write(json.dumps(pair))
                f.write("\n")

        print(
            f"Saved {len(pairs)} preference pairs "
            f"to {output_file}"
        )

    # ------------------------------------------------------------

    @staticmethod
    def print_ranking(
        ranked: List[Candidate],
    ):

        print()

        print("=" * 80)
        print("Candidate Ranking")
        print("=" * 80)

        for candidate in ranked:

            print(
                f"Candidate {candidate.candidate_id:2d}"
                f" | Reward = {candidate.reward:.4f}"
            )

        print("=" * 80)

    # ------------------------------------------------------------

    @staticmethod
    def print_pairs(
        pairs,
    ):

        print()

        print(f"Generated {len(pairs)} preference pairs\n")

        for i, pair in enumerate(pairs[:5]):

            print("=" * 80)

            print(f"Pair {i}")

            print("=" * 80)

            print(
                "Chosen Reward  :",
                pair["chosen_reward"],
            )

            print(
                "Rejected Reward:",
                pair["rejected_reward"],
            )

            print()

            print("Chosen\n")

            print(pair["chosen"][:500])

            print()

            print("Rejected\n")

            print(pair["rejected"][:500])

            print()

    # ------------------------------------------------------------

    @staticmethod
    def best_candidate(
        ranked: List[Candidate],
    ) -> Candidate:

        return ranked[0]
