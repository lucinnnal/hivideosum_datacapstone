#!/usr/bin/env python3
"""
Build messages-format fine-tuning records for 7856_summary.jsonl and push to HF Hub.

Pipeline:
  1. Join combined_data_merged_unique.jsonl (transcript + comments)
     with 7856_filtered_comments_kexaone.jsonl (evaluation results) by video_id.
  2. Build messages format using the same logic as build_finetune_dataset.py,
     with gemini_summary as the assistant turn.
  3. Dedup against existing Hub records.
  4. Append new records to Hub and push.
"""

import json
import random
import argparse
from typing import Any

from datasets import Dataset, DatasetDict, load_dataset


SYSTEM_PROMPT = """당신은 유튜브 영상을 보고 독자에게 생생하게 전달하는 콘텐츠 작가입니다.
세 가지 입력(자막, 일반 댓글, 타임스탬프 댓글)을 소화하여 하나의 자연스러운 산문 요약을 작성합니다.

[각 입력의 활용 방법]
- 자막: 영상의 전체 흐름과 내용 파악에만 사용
- 일반 댓글: 시청자들의 전반적인 반응과 여론 파악에만 사용
- 타임스탬프 댓글: 시청자들이 특히 집중하거나 반응한 장면과 시간 파악에만 사용

[산문 작성 규칙]
- 섹션 제목, 번호, 불릿 포인트 없이 문단으로만 구성
- 500~1000자 내외
- 아래 문단 흐름을 반드시 준수할 것:
  1문단 - 영상 내용: 자막만을 근거로 영상이 어떤 내용을 다루는지 서술. 시간 정보(예: 3:24) 포함 금지.
  2문단 - 시청자 반응: 일반 댓글만을 근거로 시청자들의 전반적인 반응과 여론을 서술. 시간 정보(예: 3:24) 포함 금지.
  3문단 - 집중 장면: 타임스탬프 댓글만을 근거로 시청자들이 특히 집중한 시간대와 그 반응을 서술.
           댓글에 기록된 시간 정보(예: 3:24)를 산문에 자연스럽게 녹여 쓸 것. 예) "3:24에서는", "7:10 부근에서는"
- 각 문단은 자연스럽게 이어지도록 연결 표현을 사용할 것
- 문체는 '-이에요', '-요' 체로 통일하되 친근하고 자연스럽게

[절대 금지]
- 자막·댓글 문장을 단순히 나열하는 것
- 자막·댓글에 없는 내용을 추가하거나 사실을 지어내는 것
- 타임스탬프 댓글에 없는 시간 정보를 임의로 생성하는 것
- 각 문단의 소스를 혼용하는 것 (예: 1문단에 댓글 내용을 섞는 것)
- 1문단과 2문단에 시간 정보를 포함하는 것
- 근거 없는 추측이나 과장
- "이 영상은 매우 흥미로워요" 같은 평가성 도입 문장

산문만 출력하세요. 다른 텍스트는 포함하지 마세요."""

USER_PROMPT_VARIANTS = [
    "이 영상 요약해줘",
    "이 영상 요약해주세요",
    "영상 내용 요약해줘",
    "이 유튜브 영상 요약해줘",
    "영상 요약 부탁해",
]


def load_jsonl(path: str) -> list[dict]:
    """Load all records from a JSONL file.

    Args:
        path: Path to the JSONL file.

    Returns:
        List of parsed JSON records.
    """
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_transcript_text(transcript: list[dict[str, Any]]) -> str:
    """Join transcript segments into a single string."""
    return " ".join(
        item.get("text", "").strip()
        for item in transcript
        if item.get("text", "").strip()
    )


def build_comments_text(comments: list[dict[str, Any]]) -> str:
    """Format comment list as numbered text block."""
    if not comments:
        return "(없음)"
    lines = [
        f"{i}. {c.get('text', '').strip()}"
        for i, c in enumerate(comments, 1)
        if c.get("text", "").strip()
    ]
    return "\n".join(lines) if lines else "(없음)"


def filter_passing_comments(
    comments: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
    prefix: str,
) -> list[dict[str, Any]]:
    """Return only comments whose evaluation entry has is_pass=True.

    Args:
        comments: Raw comment objects (each has 'text', 'cid', etc.).
        evaluations: Evaluation entries from evaluation_result.
        prefix: ID prefix used in evaluation entries ('g' or 't').

    Returns:
        Filtered list of comment objects.
    """
    passing_indices = {
        int(e["id"][len(prefix):])
        for e in evaluations
        if e.get("is_pass") and e.get("id", "").startswith(prefix)
    }
    return [c for i, c in enumerate(comments) if i in passing_indices]


def build_user_message(
    transcript_text: str,
    general_text: str,
    timestamp_text: str,
    user_prompt: str,
) -> str:
    """Build the user turn: short request + input data."""
    return f"""{user_prompt}

[입력 데이터]
- 자막:
{transcript_text}

- 일반 댓글:
{general_text}

- 타임스탬프 댓글:
{timestamp_text}"""


def main():
    """Build 7856 fine-tuning records and push new ones to HF Hub."""
    parser = argparse.ArgumentParser(description="Build 7856 records and push to HF Hub")
    parser.add_argument("--raw", default="data/combined_data_merged_unique.jsonl",
                        help="Raw data JSONL with transcript + comments")
    parser.add_argument("--eval", default="data/7856_filtered_comments_kexaone.jsonl",
                        help="Evaluation results JSONL")
    parser.add_argument("--summaries", default="final_construction_data/7856_summary.jsonl",
                        help="Summary JSONL with gemini_summary field")
    parser.add_argument("--repo", default="kim586w/hivideosum_training_dataset",
                        help="HF Hub repo id")
    parser.add_argument("--split", default="train")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build records but do not push to Hub")
    args = parser.parse_args()

    print("=== Step 1: Loading files ===")
    raw_records = {r["video_id"]: r for r in load_jsonl(args.raw)}
    eval_records = {r["video_id"]: r for r in load_jsonl(args.eval)}
    summary_records = load_jsonl(args.summaries)
    print(f"  raw: {len(raw_records)}, eval: {len(eval_records)}, summaries: {len(summary_records)}")

    print("\n=== Step 2: Loading existing Hub data ===")
    hub_ds = load_dataset(args.repo, split=args.split)
    hub_ids = set(hub_ds["video_id"])
    print(f"  Hub 기존 records: {len(hub_ds)}, 고유 video_id: {len(hub_ids)}")

    print("\n=== Step 3: Building messages format ===")
    new_records = []
    skipped = 0

    for idx, summ_rec in enumerate(summary_records):
        video_id = summ_rec.get("video_id", "")
        summary = summ_rec.get("gemini_summary", "").strip()

        if not summary:
            print(f"  [{idx+1}] Skip (empty summary): {video_id}")
            skipped += 1
            continue

        if video_id in hub_ids:
            print(f"  [{idx+1}] Skip (already in Hub): {video_id}")
            skipped += 1
            continue

        raw_rec = raw_records.get(video_id)
        eval_rec = eval_records.get(video_id)
        if raw_rec is None or eval_rec is None:
            print(f"  [{idx+1}] Skip (missing raw/eval data): {video_id}")
            skipped += 1
            continue

        evaluation = eval_rec.get("evaluation_result", {})
        transcript_text = build_transcript_text(raw_rec.get("transcript", []))

        raw_general = raw_rec.get("regular_comments", [])
        eval_general = evaluation.get("general_comments", [])
        passed_general = filter_passing_comments(raw_general, eval_general, "g")
        general_text = build_comments_text(passed_general)

        raw_timestamp = raw_rec.get("timestamp_comments", [])
        eval_timestamp = evaluation.get("timestamp_comments", [])
        passed_timestamp = filter_passing_comments(raw_timestamp, eval_timestamp, "t")
        timestamp_text = build_comments_text(passed_timestamp)

        user_prompt = USER_PROMPT_VARIANTS[idx % len(USER_PROMPT_VARIANTS)]
        user_message = build_user_message(transcript_text, general_text, timestamp_text, user_prompt)

        new_records.append({
            "video_id": video_id,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": summary},
            ],
        })

    print(f"\n  빌드 완료: {len(new_records)}개, 스킵: {skipped}개")

    print("\n=== Step 4: Dedup check ===")
    new_ids = [r["video_id"] for r in new_records]
    overlap = set(new_ids) & hub_ids
    print(f"  새 레코드 중 Hub와 중복: {len(overlap)}개")
    if overlap:
        new_records = [r for r in new_records if r["video_id"] not in hub_ids]
        print(f"  중복 제거 후: {len(new_records)}개")

    print(f"\n=== Step 5: 최종 결과 ===")
    print(f"  기존 Hub: {len(hub_ds)}개")
    print(f"  추가할 새 레코드: {len(new_records)}개")
    print(f"  push 후 예상 총 레코드: {len(hub_ds) + len(new_records)}개")

    if args.dry_run:
        print("\n[dry-run] Hub push 생략")
        return

    print("\n=== Step 6: Pushing to Hub ===")
    existing_records = [dict(hub_ds[i]) for i in range(len(hub_ds))]
    all_records = existing_records + new_records

    dataset = Dataset.from_list(all_records)
    dataset_dict = DatasetDict({args.split: dataset})
    dataset_dict.push_to_hub(repo_id=args.repo, private=False)
    print(f"Done → https://huggingface.co/datasets/{args.repo}")
    print(f"Total records: {len(all_records)}")


if __name__ == "__main__":
    main()
