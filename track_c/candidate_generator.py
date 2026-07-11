"""
candidate_generator.py

Generate multiple candidate edits from a coding model.
"""

from __future__ import annotations

import gc
import re
from dataclasses import dataclass
from typing import List

import torch
from transformers import PreTrainedModel, PreTrainedTokenizer


@dataclass
class Candidate:
    candidate_id: int
    raw_output: str
    code: str
    reward: float | None = None
    summary: dict | None = None
    audit = None


class CandidateGenerator:

    def __init__(
        self,
        model: PreTrainedModel,
        tokenizer: PreTrainedTokenizer,
        temperature: float = 1.0,
        top_p: float = 0.95,
        max_new_tokens: int = 512,
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.temperature = temperature
        self.top_p = top_p
        self.max_new_tokens = max_new_tokens

        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id

    def _build_prompt(self, instruction: str, before_code: str) -> str:
        return f"""
You are an expert software engineer.

Apply ONLY the requested edit.

Do NOT:
- refactor unrelated code
- rename unrelated identifiers
- reformat unrelated code
- add comments
- change behaviour outside the instruction

Instruction:

{instruction}

Original file:

```python
{before_code}
```

Return ONLY the complete updated Python file.

Do NOT explain anything.
Do NOT wrap the answer in markdown.
"""

    def _clean_code(self, text: str) -> str:
        fence = re.search(
            r"```(?:python)?\s*(.*?)```",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

        if fence:
            text = fence.group(1)

        text = text.strip()
        lines = text.splitlines()

        start = 0
        for i, line in enumerate(lines):
            if re.match(r"\s*(from|import|class|def|@)", line):
                start = i
                break

        return "\n".join(lines[start:]).strip()

    @torch.no_grad()
    def generate(
        self,
        instruction: str,
        before_code: str,
        num_candidates: int,
        max_attempts: int = 3,
    ) -> List[Candidate]:

        prompt = self._build_prompt(instruction, before_code)

        messages = [{"role": "user", "content": prompt}]

        chat = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = self.tokenizer(
            chat,
            return_tensors="pt",
        ).to(self.model.device)

        prompt_len = inputs["input_ids"].shape[1]

        candidates = []
        seen = set()

        attempts = 0
        max_total_attempts = max_attempts * num_candidates

        while len(candidates) < num_candidates and attempts < max_total_attempts:

            attempts += 1

            print(f"Generating candidate {len(candidates)+1}/{num_candidates}")

            outputs = self.model.generate(
                **inputs,
                do_sample=True,
                temperature=self.temperature,
                top_p=self.top_p,
                max_new_tokens=self.max_new_tokens,
                pad_token_id=self.tokenizer.pad_token_id,
            )

            decoded = self.tokenizer.decode(
                outputs[0][prompt_len:],
                skip_special_tokens=True,
            )

            cleaned = self._clean_code(decoded)

            del outputs
            gc.collect()

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            if not cleaned:
                continue

            if cleaned in seen:
                continue

            seen.add(cleaned)

            candidates.append(
                Candidate(
                    candidate_id=len(candidates),
                    raw_output=decoded,
                    code=cleaned,
                )
            )

        if len(candidates) < num_candidates:
            print(
                f"Warning: generated only {len(candidates)} unique candidates after {attempts} attempts."
            )

        return candidates
