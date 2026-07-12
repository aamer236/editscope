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
import os
import sys

from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
)


from candidate_generator import CandidateGenerator
from pair_builder import PairBuilder
from reward import EditScopeReward


# ============================================================
# Configuration
# ============================================================

MODEL_NAME = "Qwen/Qwen2.5-Coder-7B-Instruct"

NUM_CANDIDATES = 8

OUTPUT_FILE = "dpo_pairs.jsonl"

MAX_PROBLEMS = 15      # set to an integer for debugging


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
    generator,
    reward_model,
)


# ============================================================
# Load CanItEdit
# ============================================================

print("=" * 80)
print("Loading CanItEdit...")
print("=" * 80)

dataset = load_dataset(
    "nuprl/CanItEdit",
    revision="3c07f38b1f9385f3214fcea94d4664c79df0d36a",
    split="test",
)

print(dataset)


# ============================================================
# Generate preference data
# ============================================================

total_pairs = 0
processed = 0

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

            builder.print_ranking(ranked)

            for pair in pairs:

                pair["problem_id"] = sample["id"]
                pair["taxonomy"] = sample["taxonomy"]

                f.write(json.dumps(pair))
                f.write("\n")

            print(f"Generated {len(pairs)} preference pairs.")

            total_pairs += len(pairs)

        except Exception as e:

             import traceback
            
             print("=" * 80)
             traceback.print_exc()
             print("=" * 80)
        processed += 1


print()
print("=" * 80)
print("Finished!")
print("=" * 80)

print(f"Problems processed : {processed}")
print(f"Preference pairs   : {total_pairs}")
print(f"Saved to           : {OUTPUT_FILE}")
