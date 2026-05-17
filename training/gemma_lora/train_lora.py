"""LoRA fine-tuning script for Jiunsong/supergemma4-26b-abliterated-multimodal.

Runs in full bf16 on A100 80 GB (26B model ≈ 52 GB weights, ~28 GB headroom).
Dataset: kim586w/hivideosum_training_dataset (system/user/assistant chat format)

Usage:
    python train_lora.py                        # uses config.yaml
    python train_lora.py --config my.yaml       # custom config
"""

import argparse
import os
from pathlib import Path

import torch
import wandb
import yaml
from dotenv import load_dotenv

load_dotenv()
from datasets import load_dataset
from peft import LoraConfig, TaskType, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer


def load_config(path: str) -> dict:
    """Load and return the YAML config as a nested dict."""
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml", help="Path to YAML config file")
    args = parser.parse_args()

    cfg = load_config(args.config)
    lora_cfg = cfg["lora"]
    train_cfg = cfg["training"]

    print(f"Loaded config: {args.config}")

    # -----------------------------------------------------------------------
    # W&B 초기화
    # -----------------------------------------------------------------------
    wandb_cfg = cfg.get("wandb", {})
    wandb.init(
        project=wandb_cfg.get("project", "hivideosum-lora"),
        name=wandb_cfg.get("run_name") or None,
        config={
            "model_id": cfg["model_id"],
            "dataset_id": cfg["dataset_id"],
            **{f"lora/{k}": v for k, v in cfg["lora"].items()},
            **{f"training/{k}": v for k, v in cfg["training"].items()},
        },
    )

    # -----------------------------------------------------------------------
    # Tokenizer
    # -----------------------------------------------------------------------
    tokenizer = AutoTokenizer.from_pretrained(cfg["model_id"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # -----------------------------------------------------------------------
    # Dataset
    # -----------------------------------------------------------------------
    dataset = load_dataset(cfg["dataset_id"], split="train")

    def format_sample(sample):
        """Apply chat template to messages list → plain text field."""
        text = tokenizer.apply_chat_template(
            sample["messages"],
            add_generation_prompt=False,
            tokenize=False,
        )
        return {"text": text}

    dataset = dataset.map(format_sample, remove_columns=dataset.column_names, num_proc=4)
    print(f"Dataset size: {len(dataset)}")
    print("Sample text (first 200 chars):", dataset[0]["text"][:200])

    # -----------------------------------------------------------------------
    # Model — full bf16 (A100 80 GB: 26B ≈ 52 GB weights, ~28 GB headroom)
    # -----------------------------------------------------------------------
    model = AutoModelForCausalLM.from_pretrained(
        cfg["model_id"],
        dtype=torch.bfloat16,
        device_map="auto",
        attn_implementation="sdpa",
    )

    # Freeze audio/vision towers — train language model weights only
    for name, param in model.named_parameters():
        if not name.startswith("model.language_model"):
            param.requires_grad = False

    # -----------------------------------------------------------------------
    # LoRA
    # -----------------------------------------------------------------------
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=lora_cfg["r"],
        lora_alpha=lora_cfg["alpha"],
        target_modules=lora_cfg["target_modules"],
        lora_dropout=lora_cfg["dropout"],
        bias="none",
    )

    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # -----------------------------------------------------------------------
    # SFT Training
    # -----------------------------------------------------------------------
    trainer = SFTTrainer(
        model=model,
        args=SFTConfig(
            output_dir=cfg["output_dir"],
            num_train_epochs=train_cfg["num_train_epochs"],
            per_device_train_batch_size=train_cfg["per_device_train_batch_size"],
            gradient_accumulation_steps=train_cfg["gradient_accumulation_steps"],
            gradient_checkpointing=train_cfg["gradient_checkpointing"],
            gradient_checkpointing_kwargs={"use_reentrant": False},
            use_cache=False,
            learning_rate=train_cfg["learning_rate"],
            lr_scheduler_type=train_cfg["lr_scheduler_type"],
            optim=train_cfg["optim"],
            warmup_ratio=train_cfg["warmup_ratio"],
            bf16=train_cfg["bf16"],
            logging_steps=train_cfg["logging_steps"],
            packing=train_cfg["packing"],
            save_strategy=train_cfg["save_strategy"],
            save_total_limit=train_cfg["save_total_limit"],
            max_seq_length=train_cfg["max_seq_length"],
            dataset_text_field="text",
            report_to=train_cfg["report_to"],
        ),
        train_dataset=dataset,
        processing_class=tokenizer,
    )

    trainer.train()

    # Save LoRA adapter weights only (base model is not modified)
    trainer.save_model(cfg["output_dir"])
    tokenizer.save_pretrained(cfg["output_dir"])
    print(f"LoRA adapter saved to: {cfg['output_dir']}")

    wandb.finish()


if __name__ == "__main__":
    main()
