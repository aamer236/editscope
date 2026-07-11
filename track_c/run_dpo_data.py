"""
run_dpo_data.py

Generate DPO preference pairs using:

CanItEdit
        ↓
Candidate Generator
        ↓
EditScope Oracle
        ↓
Preference Pairs
        ↓
JSONL
"""

from __future__ import annotations

import json
import sys
import traceback

from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.append("/kaggle/working/editscope_dpo")

print("=" * 80)
print("RUN_DPO_DATA VERSION 4")
print(__file__)
print("=" * 80)

from candidate_generator import CandidateGenerator
from pair_builder import PairBuilder
from reward import EditScopeReward


# ============================================================
# Configuration
# ============================================================

MODEL_NAME = "Qwen/Qwen2.5-Coder-7B-Instruct"

NUM_CANDIDATES = 8

OUTPUT_FILE = "dpo_pairs.jsonl"

MAX_PROBLEMS = 1        # None -> full dataset


# ============================================================
# Load model
# ============================================================

print("=" * 80)
print("Loading tokenizer...")
print("=" * 80)

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

print("=" * 80)
print("Loading model...")
print("=" * 80)

model = AutoModelForCausalLM.from_pretrained(
    MODEL_NAME,
    device_map="auto",
    torch_dtype="auto",
)

generator = CandidateGenerator(
    model=model,
    tokenizer=tokenizer,
)

reward_model = EditScopeReward()

builder = PairBuilder(
    generator=generator,
    reward_model=reward_model,
)


# ============================================================
# Load CanItEdit
# ============================================================

print("=" * 80)
print("Loading CanItEdit...")
print("=" * 80)

dataset = load_dataset(
    "nuprl/CanItEdit",
    split="test",
)

print(dataset)


# ============================================================
# Generate
# ============================================================

total_pairs = 0
processed = 0
failed = 0

with open(OUTPUT_FILE, "w") as f:

    for sample in dataset:

        if MAX_PROBLEMS is not None and processed >= MAX_PROBLEMS:
            break

        instruction = (
            sample["instruction_descriptive"]
            or sample["instruction_lazy"]
        )

        before = sample["before"]

        tests = sample.get("tests", "")

        print()
        print("=" * 80)
        print(f"Problem {processed + 1}")
        print("=" * 80)
        print(instruction)

        try:

            ranked, pairs = builder.build_pairs(
                instruction=instruction,
                before_code=before,
                tests=tests,
                num_candidates=NUM_CANDIDATES,
            )

            print()
            print(f"Generated {len(ranked)} candidates.")
            print(f"Generated {len(pairs)} preference pairs.")

            builder.print_ranking(ranked)

            for pair in pairs:

                pair["problem_id"] = sample["id"]
                pair["taxonomy"] = sample["taxonomy"]

                f.write(json.dumps(pair))
                f.write("\n")

            # Save progress immediately
            f.flush()

            total_pairs += len(pairs)

        except Exception:

            failed += 1

            print()
            print("=" * 80)
            print("FAILED ON THIS EXAMPLE")
            print("=" * 80)

            traceback.print_exc()

            print("=" * 80)
            print("Continuing...")
            print("=" * 80)

        processed += 1


print()
print("=" * 80)
print("Finished!")
print("=" * 80)

print(f"Problems processed : {processed}")
print(f"Problems failed    : {failed}")
print(f"Preference pairs   : {total_pairs}")
print(f"Saved to           : {OUTPUT_FILE}")