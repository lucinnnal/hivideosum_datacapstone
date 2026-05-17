#!/usr/bin/env python3
"""
Generate video summaries using the Gemini API.
Input : filtered_combined_data.jsonl
Output: summarized_data_gemini.jsonl

Generation config (temperature, top_p, max_output_tokens, thinking) is loaded
from configs/gemini.yaml. CLI flags override YAML values.

thinking.thinking_level: none | low | medium | high
"""

import json
import os
import sys
import argparse
import time
from typing import Any

import yaml

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Please install google-genai: pip install google-genai")
    sys.exit(1)


def load_model_config(config_path: str) -> dict:
    """Load generation config from a YAML file."""
    if not os.path.exists(config_path):
        print(f"Error: config not found: {config_path}")
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


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


def build_prompt(transcript_text: str, general_text: str, timestamp_text: str) -> str:
    """Build the summary prompt."""
    return f"""
당신은 유튜브 영상을 보고 독자에게 생생하게 전달하는 콘텐츠 작가입니다.
아래 세 가지 입력을 모두 소화하여 하나의 자연스러운 산문 요약을 작성해주세요.

[각 입력의 활용 방법]
- 자막: 영상의 전체 흐름과 내용 파악에만 사용
- 일반 댓글: 시청자들의 전반적인 반응과 여론 파악에만 사용
- 타임스탬프 댓글: 시청자들이 특히 집중하거나 반응한 장면과 시간 파악에만 사용

[산문 작성 규칙]
- 섹션 제목, 번호, 불릿 포인트 없이 문단으로만 구성
- 500~1000자 내외
- 아래 문단 흐름을 반드시 준수할 것:
  1문단 - 영상 내용: 자막만을 근거로 영상이 어떤 내용을 다루는지 서술.
           시간 정보(예: 3:24) 포함 금지.
  2문단 - 시청자 반응: 일반 댓글만을 근거로 시청자들의 전반적인 반응과 여론을 서술.
           시간 정보(예: 3:24) 포함 금지.
  3문단 - 집중 장면: 타임스탬프 댓글만을 근거로 시청자들이 특히 집중한 시간대와 그 반응을 서술.
           댓글에 기록된 시간 정보(예: 3:24)를 산문에 자연스럽게 녹여 쓸 것.
           예) "3:24에서는", "7:10 부근에서는"
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

[입력 데이터]
- 자막:
{transcript_text}

- 일반 댓글:
{general_text}

- 타임스탬프 댓글:
{timestamp_text}

산문만 출력하세요. 다른 텍스트는 포함하지 마세요.
"""


def load_processed_ids(output_path: str) -> set:
    """Load already-processed video IDs from output file."""
    processed = set()
    if os.path.exists(output_path):
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if "video_id" in data:
                        processed.add(data["video_id"])
                except Exception:
                    pass
    return processed


def main():
    """Run summarization pipeline using the Gemini API."""
    parser = argparse.ArgumentParser(description="Summarize videos via Gemini API")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "configs", "gemini.yaml"),
        help="Path to generation config YAML (default: configs/gemini.yaml)",
    )
    parser.add_argument("--input", "-i", default="data/filtered_comments_sample.jsonl")
    parser.add_argument("--output", "-o", default="data/summarized_data_gemini_filtered.jsonl")
    # Generation overrides — if omitted, YAML config values are used
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=None)
    parser.add_argument(
        "--thinking-level",
        default=None,
        choices=["none", "low", "medium", "high"],
        help="Thinking level (overrides YAML); none | low | medium | high",
    )
    args = parser.parse_args()

    cfg = load_model_config(args.config)
    gen_cfg = cfg.get("generation", {})
    model_name = cfg.get("model_name", "gemini-3.1-flash-lite-preview")

    # CLI flags override YAML; fall back to YAML defaults
    temperature = args.temperature if args.temperature is not None else gen_cfg.get("temperature", 1.0)
    top_p = args.top_p if args.top_p is not None else gen_cfg.get("top_p", 0.95)
    max_output_tokens = (
        args.max_output_tokens
        if args.max_output_tokens is not None
        else gen_cfg.get("max_output_tokens", 8192)
    )
    thinking_cfg = gen_cfg.get("thinking", {})
    thinking_level = args.thinking_level or thinking_cfg.get("thinking_level")

    if not os.path.exists(args.input):
        print(f"Error: input file not found: {args.input}")
        sys.exit(1)

    # 1. ADC를 이용한 클라이언트 초기화
    # API 키 없이 GCP 프로젝트 ID와 리전만 입력합니다.
    client = genai.Client(
        vertexai=True,
        project="hivideosum",
        location="global",
    )

    with open(args.input, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    print(f"Model          : {model_name}")
    print(f"Temperature    : {temperature}  top_p: {top_p}  max_output_tokens: {max_output_tokens}")
    print(f"Thinking level : {thinking_level or '(not set)'}")
    print(f"Loaded {len(records)} records from {args.input}")

    processed_ids = load_processed_ids(args.output)
    print(f"Already processed: {len(processed_ids)} videos — skipping")

    os.makedirs(
        os.path.dirname(args.output) if os.path.dirname(args.output) else ".",
        exist_ok=True,
    )

    generate_config = types.GenerateContentConfig(
        temperature=temperature,
        top_p=top_p,
        max_output_tokens=max_output_tokens,
        thinking_config=types.ThinkingConfig(thinking_level=thinking_level) if thinking_level else None,
    )

    with open(args.output, "a", encoding="utf-8") as f_out:
        for idx, record in enumerate(records, 1):
            video_id = record.get("video_id", "")
            video_url = record.get("video_url", "")
            title = record.get("title", "")

            if video_id in processed_ids:
                print(f"[{idx}/{len(records)}] Skip (already done): {video_id}")
                continue

            evaluation = record.get("evaluation_result", {})

            transcript_text = build_transcript_text(record.get("transcript", []))

            raw_general = record.get("regular_comments", [])
            eval_general = evaluation.get("general_comments", [])
            passed_general = filter_passing_comments(raw_general, eval_general, "g")
            general_text = build_comments_text(passed_general)

            raw_timestamp = record.get("timestamp_comments", [])
            eval_timestamp = evaluation.get("timestamp_comments", [])
            passed_timestamp = filter_passing_comments(raw_timestamp, eval_timestamp, "t")
            timestamp_text = build_comments_text(passed_timestamp)

            if not transcript_text and general_text == "(없음)" and timestamp_text == "(없음)":
                print(f"[{idx}/{len(records)}] Skip (no content): {video_id}")
                continue

            prompt = build_prompt(transcript_text, general_text, timestamp_text)
            print(f"[{idx}/{len(records)}] Summarizing: {title[:60]}")

            max_retries = 3
            summary = None
            for attempt in range(1, max_retries + 1):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=generate_config,
                    )
                    summary = response.text.strip()
                    break
                except Exception as e:
                    print(f"  ⚠ Attempt {attempt}/{max_retries} failed: {e}")
                    if attempt < max_retries:
                        time.sleep(3 * attempt)

            if summary is None:
                print(f"  ✗ All retries failed for {video_id}, skipping.")
                continue

            output_record = {
                "video_id": video_id,
                "video_url": video_url,
                "title": title,
                "channel_name": record.get("channel_name", ""),
                "summary": summary,
            }

            f_out.write(json.dumps(output_record, ensure_ascii=False) + "\n")
            f_out.flush()
            print(f"  ✓ Done.")


if __name__ == "__main__":
    main()
