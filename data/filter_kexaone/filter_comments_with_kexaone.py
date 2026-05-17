#!/usr/bin/env python3
"""
Filter YouTube comments using the K-EXAONE API (Elice mlapi.run).
Input : combined_data_merged.jsonl
Output: filtered_comments_kexaone.jsonl

Generation config is loaded from configs/kexaone.yaml. CLI flags override YAML values.
"""

import json
import os
import re
import sys
import argparse
import time
from typing import Any

import yaml

try:
    import requests
except ImportError:
    print("Please install requests: pip install requests")
    sys.exit(1)


PROMPT_TEMPLATE = """
당신은 YouTube 영상의 댓글을 분석하고 필터링하는 전문가입니다.
당신의 목표는 주어진 Transcript(영상 자막/대본)를 바탕으로, 시청자들의 유의미한 반응과 정보가 담긴 댓글을 선별하는 것입니다. 아래의 평가 기준에 따라 각 댓글에 점수를 매기고, 총점이 6점 이상인 댓글만 '통과(Pass)'로 분류하세요.

[평가 기준]
1. 정보성 (1-3점): 댓글이 의미 있는 정보나 요약을 담고 있는가?
- 1점: 내용이 없거나 무의미한 텍스트 (예: "ㅋㅋ", "1빠", 스팸)
- 2점: 영상에 등장하는 단편적인 사실을 언급함
- 3점: 영상 내용을 훌륭하게 요약했거나, 영상과 관련된 유용한 추가 정보/인사이트를 제공함

2. 의견성 (1-3점): 시청자의 주관적인 의견, 감정, 반응이 잘 담겨 있는가?
- 1점: 의견이나 감정이 전혀 드러나지 않음 (단순 사실 나열)
- 2점: 평범하고 일상적인 반응 (예: "잘 봤습니다", "재밌네요")
- 3점: 영상에 대한 깊은 공감, 날카로운 비판, 또는 독창적인 시각이나 강렬한 주관적 감정이 드러남

3. 연관성 (1-3점): 제공된 Transcript의 내용과 직접적으로 연관되어 있는가?
- 1점: 영상의 내용과 전혀 무관함 (딴소리, 어그로)
- 2점: 영상의 전반적인 주제와는 관련이 있으나, 구체적인 내용은 아님
- 3점: Transcript에 등장하는 특정 발언, 장면, 맥락을 정확히 짚어서 이야기함

[평가 규칙]
- 총점 = 정보성 + 의견성 + 연관성
- 총점이 6점 이상(>= 6)인 경우에만 "Pass"로 분류하세요. 미만인 경우 "Fail"로 분류합니다.
- 아래의 [출력 형식]과 같이 각 줄마다 `댓글ID|정보성점수|의견성점수|연관성점수|총점|Pass/Fail` 형식으로만 출력하십시오.
- 헤더, 인사말, 마크다운(예: ```) 등 다른 텍스트는 절대 포함하지 마십시오. 오로지 각 댓글에 대한 결과만 한 줄씩 출력해야 합니다.

[출력 형식 예시]
g0|1|2|1|4|Fail
g1|2|3|3|8|Pass
t0|1|1|1|3|Fail
t1|3|3|2|8|Pass

[입력 데이터]
## Transcript
\"\"\"
{transcript}
\"\"\"

## 일반 댓글
{general_comments}

## Timestamp 댓글
{timestamp_comments}
"""


def load_config(config_path: str) -> dict:
    """Load generation config from a YAML file."""
    if not os.path.exists(config_path):
        print(f"Error: config not found: {config_path}")
        sys.exit(1)
    with open(config_path) as f:
        return yaml.safe_load(f)


def prepare_comments_for_prompt(comments: list[dict[str, Any]], id_prefix: str) -> str:
    """Prepare comments into a JSON string to insert into the prompt."""
    formatted = []
    for idx, c in enumerate(comments):
        formatted.append({
            "id": f"{id_prefix}{idx}",
            "text": c.get("text", "").strip(),
        })
    return json.dumps(formatted, ensure_ascii=False, indent=2)


def strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> blocks that some models prepend to their output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def parse_filter_response(response_text: str) -> dict:
    """Parse the pipe-separated scoring output into structured results.

    Returns:
        dict with 'general_comments' and 'timestamp_comments' lists.
    """
    general_results = []
    timestamp_results = []

    for line in response_text.split("\n"):
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) < 6:
            continue
        c_id = parts[0].strip()
        try:
            info = int(parts[1].strip())
            opinion = int(parts[2].strip())
            relevance = int(parts[3].strip())
            total = int(parts[4].strip())
            is_pass = parts[5].strip().lower() == "pass"
        except ValueError:
            continue

        result_obj = {
            "id": c_id,
            "scores": {"info": info, "opinion": opinion, "relevance": relevance},
            "total_score": total,
            "is_pass": is_pass,
        }
        if c_id.startswith("g"):
            general_results.append(result_obj)
        elif c_id.startswith("t"):
            timestamp_results.append(result_obj)

    return {"general_comments": general_results, "timestamp_comments": timestamp_results}


def main():
    """Run comment filtering pipeline using the K-EXAONE API."""
    parser = argparse.ArgumentParser(description="Filter comments via K-EXAONE API")
    parser.add_argument(
        "--config",
        default=os.path.join(os.path.dirname(__file__), "configs", "kexaone.yaml"),
        help="Path to generation config YAML (default: configs/kexaone.yaml)",
    )
    parser.add_argument("--input", "-i", default="data/combined_data_merged.jsonl")
    parser.add_argument("--output", "-o", default="data/filtered_comments_kexaone.jsonl")
    parser.add_argument("--api-key", default=None, help="K-EXAONE API key (overrides K_EXAONE_API_KEY env var)")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    gen_cfg = cfg.get("generation", {})
    model_name = cfg["model_name"]
    base_url = cfg["api"]["base_url"]

    temperature = args.temperature if args.temperature is not None else gen_cfg.get("temperature", 0.1)
    top_p = args.top_p if args.top_p is not None else gen_cfg.get("top_p", 0.95)
    max_tokens = args.max_tokens if args.max_tokens is not None else gen_cfg.get("max_tokens", 8192)
    presence_penalty = gen_cfg.get("presence_penalty", 0.0)
    chat_template_kwargs = gen_cfg.get("chat_template_kwargs", {})

    api_key = args.api_key or os.environ.get("K_EXAONE_API_KEY", "")
    if not api_key:
        print("Error: K_EXAONE_API_KEY is not set. Use --api-key or export K_EXAONE_API_KEY=...")
        sys.exit(1)

    if not os.path.exists(args.input):
        print(f"Error: input file not found: {args.input}")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "accept": "application/json",
        "content-type": "application/json",
    }

    processed_urls = set()
    if os.path.exists(args.output):
        with open(args.output, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    if "video_url" in d:
                        processed_urls.add(d["video_url"])
                except Exception:
                    pass

    with open(args.input, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    print(f"Model          : {model_name}")
    print(f"Temperature    : {temperature}  top_p: {top_p}  max_tokens: {max_tokens}")
    print(f"Loaded {len(records)} records from {args.input}")
    print(f"Already processed: {len(processed_urls)} videos — skipping")

    os.makedirs(
        os.path.dirname(args.output) if os.path.dirname(args.output) else ".",
        exist_ok=True,
    )

    with open(args.output, "a", encoding="utf-8") as f_out:
        for idx, data in enumerate(records, 1):
            video_url = data.get("video_url")

            if not data.get("success"):
                print(f"[{idx}/{len(records)}] Skip (failed collection): {video_url}")
                continue

            if video_url in processed_urls:
                print(f"[{idx}/{len(records)}] Skip (already done): {video_url}")
                continue

            print(f"[{idx}/{len(records)}] Processing: {video_url}")

            transcript_text = " ".join(
                item.get("text", "") for item in data.get("transcript", [])
            )
            regular_comments = data.get("regular_comments", [])
            timestamp_comments = data.get("timestamp_comments", [])

            if not regular_comments and not timestamp_comments:
                print(f"[{idx}/{len(records)}] Skip (no comments): {video_url}")
                continue

            general_comments_str = prepare_comments_for_prompt(regular_comments, "g")
            timestamp_comments_str = prepare_comments_for_prompt(timestamp_comments, "t")

            prompt = PROMPT_TEMPLATE.format(
                transcript=transcript_text,
                general_comments=general_comments_str,
                timestamp_comments=timestamp_comments_str,
            )

            payload = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "top_p": top_p,
                "max_tokens": max_tokens,
                "presence_penalty": presence_penalty,
            }
            if chat_template_kwargs:
                payload["chat_template_kwargs"] = chat_template_kwargs

            max_retries = 3
            evaluation_result = None
            for attempt in range(1, max_retries + 1):
                try:
                    response = requests.post(base_url, headers=headers, json=payload, timeout=300)
                    response.raise_for_status()
                    content = response.json()["choices"][0]["message"]["content"]
                    if content is None:
                        raise ValueError("API returned null content — check enable_thinking setting")
                    response_text = strip_thinking_tags(content)

                    # Strip accidental markdown fences
                    response_text = re.sub(r"^```[a-z]*\n?", "", response_text).rstrip("```").strip()

                    evaluation_result = parse_filter_response(response_text)
                    break
                except Exception as e:
                    print(f"  ⚠ Attempt {attempt}/{max_retries} failed: {e}")
                    if attempt < max_retries:
                        time.sleep(3 * attempt)

            if evaluation_result is None:
                print(f"  ✗ All retries failed for {video_url}, skipping.")
                continue

            result_data = {
                "video_url": video_url,
                "video_id": data.get("video_id"),
                "title": data.get("title"),
                "evaluation_result": evaluation_result,
            }
            f_out.write(json.dumps(result_data, ensure_ascii=False) + "\n")
            f_out.flush()

            g_total = len(evaluation_result["general_comments"])
            t_total = len(evaluation_result["timestamp_comments"])
            g_pass = sum(1 for c in evaluation_result["general_comments"] if c["is_pass"])
            t_pass = sum(1 for c in evaluation_result["timestamp_comments"] if c["is_pass"])
            print(f"  ✓ Done. Passed/Total: {g_pass}/{g_total} general, {t_pass}/{t_total} timestamp")


if __name__ == "__main__":
    main()
