"""
Global configuration for the EditScope DPO pipeline.
"""

# -------------------------
# Model
# -------------------------

MODEL_NAME = "Qwen/Qwen2.5-Coder-7B-Instruct"

# -------------------------
# Generation
# -------------------------

NUM_CANDIDATES = 8
MAX_NEW_TOKENS = 256

TEMPERATURE = 1.0
TOP_P = 0.95

# -------------------------
# Oracle
# -------------------------

POLICY = "P4"

# -------------------------
# Reward
# -------------------------

VIOLATION_WEIGHT = 1.0
UNCERTAIN_WEIGHT = 0.5

LOC_PENALTY = 0.01
BLOCK_PENALTY = 0.05