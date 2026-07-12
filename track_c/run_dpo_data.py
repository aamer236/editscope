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

print("=" * 80)
print("RUN_DPO_DATA VERSION 4")
print(__file__)
print("=" * 80)

from track_c.candidate_generator import CandidateGenerator
from track_c.pair_builder import PairBuilder
from track_c.reward import EditScopeReward

import random
import numpy as np
import torch
from transformers import set_seed

SEED = 20260625

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
set_seed(SEED)

if torch.cuda.is_available():
    torch.cuda.manual_seed_all(SEED)


# ============================================================
# Configuration
# ============================================================

MODEL_NAME = "Qwen/Qwen2.5-Coder-7B-Instruct"

NUM_CANDIDATES = 8

OUTPUT_FILE = "dpo_pairs.jsonl"

MAX_PROBLEMS = 1        # None -> full dataset

DATASET_REVISION = "3c07f38b1f9385f3214fcea94d4664c79df0d36a"

GIT_SHA = "YOUR_COMMIT_HASH"
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
    revision="3c07f38b1f9385f3214fcea94d4664c79df0d36a",
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
                pair["model"] = MODEL_NAME
                pair["seed"] = SEED
                pair["dataset_revision"] = DATASET_REVISION
                pair["git_sha"] = GIT_SHA

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
