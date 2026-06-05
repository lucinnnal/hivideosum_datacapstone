"""Local HuggingFace Transformers inference backend (no vLLM required)."""

from __future__ import annotations

import asyncio
from functools import lru_cache

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


@lru_cache(maxsize=1)
def _load_local_model(model_path: str):
    tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto" if torch.cuda.is_available() else None,
        low_cpu_mem_usage=True,
    )
    model.eval()
    return tokenizer, model


def _generate_sync(
    model_path: str,
    prompt: str,
    max_new_tokens: int = 1024,
    temperature: float = 0.7,
    top_p: float = 0.95,
) -> str:
    tokenizer, model = _load_local_model(model_path)

    if tokenizer.chat_template:
        templated = tokenizer.apply_chat_template(
            [{"role": "user", "content": prompt}],
            add_generation_prompt=True,
            tokenize=True,
            return_tensors="pt",
        )
        if hasattr(templated, "input_ids"):
            input_ids = templated.input_ids
        else:
            input_ids = templated
    else:
        input_ids = tokenizer(prompt, return_tensors="pt").input_ids

    if torch.cuda.is_available():
        input_ids = input_ids.to(model.device)

    with torch.no_grad():
        output_ids = model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=temperature,
            top_p=top_p,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    gen_ids = output_ids[:, input_ids.shape[-1] :]
    return tokenizer.decode(gen_ids[0], skip_special_tokens=True).strip()


async def generate_summary_local(model_path: str, prompt: str) -> str:
    return await asyncio.to_thread(_generate_sync, model_path, prompt)
