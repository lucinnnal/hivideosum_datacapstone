#!/usr/bin/env python3
"""
Generate video summaries using a vLLM-served EXAONE model.
Input : filtered_combined_data.jsonl
Output: summarized_data.jsonl

Generation config (temperature, top_p, max_tokens, chat_template_kwargs) is
loaded from configs/{model_family}.yaml. CLI flags override YAML values.
"""

import json
import os
import sys
import argparse
import time
from typing import Any

import yaml

try:
    from openai import OpenAI
except ImportError:
    print("Please install openai: pip install openai")
    sys.exit(1)


def load_model_config(model_family: str) -> dict:
    """Load model config from configs/{model_family}.yaml."""
    config_path = os.path.join(
        os.path.dirname(__file__), "configs", f"{model_family}.yaml"
    )
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
    """Run summarization pipeline using model config from YAML."""
    parser = argparse.ArgumentParser(description="Summarize videos via vLLM")
    parser.add_argument(
        "--model-family",
        default=os.environ.get("MODEL_FAMILY", "exaone40"),
        help="Model family key (matches configs/<key>.yaml)",
    )
    parser.add_argument("--input", "-i", default="data/filtered_combined_data.jsonl")
    parser.add_argument("--output", "-o", default="data/summarized_data.jsonl")
    parser.add_argument("--host", default="http://localhost:8000/v1")
    # Generation overrides — if omitted, YAML config values are used
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    args = parser.parse_args()

    cfg = load_model_config(args.model_family)
    gen_cfg = cfg.get("generation", {})

    # CLI flags override YAML; fall back to YAML defaults
    temperature = args.temperature if args.temperature is not None else gen_cfg.get("temperature", 0.6)
    top_p = args.top_p if args.top_p is not None else gen_cfg.get("top_p", 0.95)
    max_tokens = args.max_tokens if args.max_tokens is not None else gen_cfg.get("max_tokens", 4096)
    chat_template_kwargs = gen_cfg.get("chat_template_kwargs", {})

    # Use served_model_name for the API call if set (e.g. EXAONE-4.5 uses a short alias)
    api_model_name = cfg.get("served_model_name") or cfg["model_name"]

    if not os.path.exists(args.input):
        print(f"Error: input file not found: {args.input}")
        sys.exit(1)

    client = OpenAI(base_url=args.host, api_key="EMPTY")

    with open(args.input, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    print(f"Model family : {args.model_family}")
    print(f"API model    : {api_model_name}")
    print(f"Temperature  : {temperature}  top_p: {top_p}  max_tokens: {max_tokens}")
    print(f"Loaded {len(records)} records from {args.input}")

    processed_ids = load_processed_ids(args.output)
    print(f"Already processed: {len(processed_ids)} videos — skipping")

    os.makedirs(
        os.path.dirname(args.output) if os.path.dirname(args.output) else ".",
        exist_ok=True,
    )

    with open(args.output, "a", encoding="utf-8") as f_out:
        for idx, record in enumerate(records, 1):
            video_id = record.get("video_id", "")
            video_url = record.get("video_url", "")
            title = record.get("title", "")

            if video_id in processed_ids:
                print(f"[{idx}/{len(records)}] Skip (already done): {video_id}")
                continue

            transcript_text = build_transcript_text(record.get("transcript", []))
            general_text = build_comments_text(record.get("general_comments", []))
            timestamp_text = build_comments_text(record.get("timestamp_comments", []))

            if not transcript_text and general_text == "(없음)" and timestamp_text == "(없음)":
                print(f"[{idx}/{len(records)}] Skip (no content): {video_id}")
                continue

            prompt = build_prompt(transcript_text, general_text, timestamp_text)
            print(f"[{idx}/{len(records)}] Summarizing: {title[:60]}")

            extra_body = {}
            if chat_template_kwargs:
                extra_body["chat_template_kwargs"] = chat_template_kwargs

            max_retries = 3
            summary = None
            for attempt in range(1, max_retries + 1):
                try:
                    response = client.chat.completions.create(
                        model=api_model_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=temperature,
                        top_p=top_p,
                        max_tokens=max_tokens,
                        extra_body=extra_body or None,
                    )
                    summary = response.choices[0].message.content.strip()
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
