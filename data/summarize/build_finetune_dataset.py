#!/usr/bin/env python3
"""
Build a fine-tuning dataset from summarized data.

Joins filtered_comments_sample.jsonl (input) with
summarized_data_gemini_filtered.jsonl (output) and formats each record as a
multi-turn conversation:
  system  → summary persona + writing rules
  user    → "이 영상 요약해줘" + input data (transcript, comments)
  assistant → generated summary

Output: data/finetune_dataset.jsonl
"""

import json
import argparse
import os
from typing import Any


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
        evaluations: Evaluation entries from evaluation_result (each has 'id', 'is_pass').
        prefix: ID prefix used in evaluation entries ('g' for general, 't' for timestamp).

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
    """Build fine-tuning dataset by joining input and summarized records."""
    parser = argparse.ArgumentParser(description="Build fine-tuning dataset")
    parser.add_argument(
        "--input", "-i",
        default="data/filtered_comments_sample.jsonl",
        help="Input JSONL with transcript and comments",
    )
    parser.add_argument(
        "--summaries", "-s",
        default="data/summarized_data_gemini_filtered.jsonl",
        help="Summarized output JSONL with generated summaries",
    )
    parser.add_argument(
        "--output", "-o",
        default="data/finetune_dataset.jsonl",
        help="Output fine-tuning JSONL",
    )
    parser.add_argument(
        "--user-prompt-index",
        type=int,
        default=None,
        help=(
            "Index into USER_PROMPT_VARIANTS (0-based) to use for all records. "
            "If omitted, cycles through variants in order."
        ),
    )
    args = parser.parse_args()

    for path in (args.input, args.summaries):
        if not os.path.exists(path):
            print(f"Error: file not found: {path}")
            raise SystemExit(1)

    with open(args.input, encoding="utf-8") as f:
        input_records = {
            rec["video_id"]: rec
            for line in f
            if line.strip()
            for rec in [json.loads(line)]
        }

    with open(args.summaries, encoding="utf-8") as f:
        summary_records = [json.loads(line) for line in f if line.strip()]

    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)

    written = 0
    skipped = 0

    with open(args.output, "w", encoding="utf-8") as f_out:
        for idx, summary_rec in enumerate(summary_records):
            video_id = summary_rec.get("video_id", "")
            summary = summary_rec.get("summary", "").strip()

            if not summary:
                print(f"[{idx+1}] Skip (no summary): {video_id}")
                skipped += 1
                continue

            input_rec = input_records.get(video_id)
            if input_rec is None:
                print(f"[{idx+1}] Skip (no input record): {video_id}")
                skipped += 1
                continue

            evaluation = input_rec.get("evaluation_result", {})

            transcript_text = build_transcript_text(input_rec.get("transcript", []))

            raw_general = input_rec.get("regular_comments", [])
            eval_general = evaluation.get("general_comments", [])
            passed_general = filter_passing_comments(raw_general, eval_general, "g")
            general_text = build_comments_text(passed_general)

            raw_timestamp = input_rec.get("timestamp_comments", [])
            eval_timestamp = evaluation.get("timestamp_comments", [])
            passed_timestamp = filter_passing_comments(raw_timestamp, eval_timestamp, "t")
            timestamp_text = build_comments_text(passed_timestamp)

            if args.user_prompt_index is not None:
                user_prompt = USER_PROMPT_VARIANTS[args.user_prompt_index % len(USER_PROMPT_VARIANTS)]
            else:
                user_prompt = USER_PROMPT_VARIANTS[idx % len(USER_PROMPT_VARIANTS)]

            user_message = build_user_message(transcript_text, general_text, timestamp_text, user_prompt)

            record = {
                "video_id": video_id,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": summary},
                ],
            }

            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1
            print(f"[{idx+1}] Written: {summary_rec.get('title', video_id)[:60]}")

    print(f"\nDone. Written: {written}  Skipped: {skipped} → {args.output}")


if __name__ == "__main__":
    main()
