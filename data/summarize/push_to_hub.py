#!/usr/bin/env python3
"""
Push finetune_dataset.jsonl to Hugging Face Hub as a Dataset.

Usage:
    python push_to_hub.py --repo <username>/<dataset-name>
    python push_to_hub.py --repo kim586w/youtube-summary-finetune
"""

import json
import argparse
import os

from datasets import Dataset, DatasetDict


def load_jsonl(path: str) -> list[dict]:
    """Load records from a JSONL file.

    Args:
        path: Path to the JSONL file.

    Returns:
        List of parsed JSON records.
    """
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    """Load finetune JSONL and push to Hugging Face Hub."""
    parser = argparse.ArgumentParser(description="Push fine-tuning dataset to HF Hub")
    parser.add_argument(
        "--input", "-i",
        default="data/finetune_dataset.jsonl",
        help="Input fine-tuning JSONL (default: data/finetune_dataset.jsonl)",
    )
    parser.add_argument(
        "--repo", "-r",
        required=True,
        help="HF Hub repo id, e.g. kim586w/youtube-summary-finetune",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        default=False,
        help="Make the dataset private (default: public)",
    )
    parser.add_argument(
        "--split",
        default="train",
        help="Dataset split name (default: train)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: file not found: {args.input}")
        raise SystemExit(1)

    records = load_jsonl(args.input)
    print(f"Loaded {len(records)} records from {args.input}")

    # Flatten messages into separate columns for readability on HF Hub,
    # while keeping the original 'messages' list for direct fine-tuning use.
    dataset = Dataset.from_list(records)

    dataset_dict = DatasetDict({args.split: dataset})

    print(f"Pushing to https://huggingface.co/datasets/{args.repo} ...")
    dataset_dict.push_to_hub(
        repo_id=args.repo,
        private=args.private,
    )
    print(f"Done → https://huggingface.co/datasets/{args.repo}")


if __name__ == "__main__":
    main()
