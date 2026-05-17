#!/usr/bin/env python3
"""
Filter YouTube Comments with KORMo 10B SFT via vLLM
Reads combined_data.jsonl, scores comments based on criteria using KORMo,
and outputs filtered results to a new JSONL file.
"""

import json
import os
import sys
import argparse
import time
from typing import List, Dict, Any

try:
    from openai import OpenAI
except ImportError:
    print("Please install openai: pip install openai")
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

def prepare_comments_for_prompt(comments: List[Dict[str, Any]], id_prefix: str) -> str:
    """Prepare comments into a JSON string to insert into the prompt."""
    formatted = []
    for idx, c in enumerate(comments):
        # Add an ID to each comment for tracking
        c_id = f"{id_prefix}{idx}"
        formatted.append({
            "id": c_id,
            "text": c.get('text', '').strip()
        })
    return json.dumps(formatted, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Filter comments using KORMo 10B SFT via vLLM")
    parser.add_argument("--input", "-i", default="comment_results/combined_data.jsonl", help="Input JSONL file")
    parser.add_argument("--output", "-o", default="comment_results/filtered_comments_kormo.jsonl", help="Output JSONL file")
    parser.add_argument("--host", default="http://localhost:8000/v1", help="vLLM API Base URL")
    parser.add_argument("--model", default="KORMo-Team/KORMo-10B-sft", help="Model name")

    args = parser.parse_args()

    client = OpenAI(base_url=args.host, api_key="EMPTY")

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found.")
        sys.exit(1)

    processed_urls = set()
    if os.path.exists(args.output):
        with open(args.output, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if 'video_url' in data:
                        processed_urls.add(data['video_url'])
                except:
                    pass

    with open(args.input, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    print(f"Loaded {len(lines)} records from {args.input}")

    with open(args.output, 'a', encoding='utf-8') as f_out:
        for idx, line in enumerate(lines, 1):
            if not line.strip():
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            video_url = data.get('video_url')

            if not data.get('success'):
                print(f"[{idx}/{len(lines)}] Skipping failed collection for {video_url}")
                continue

            if video_url in processed_urls:
                print(f"[{idx}/{len(lines)}] Skipping already processed video: {video_url}")
                continue

            print(f"[{idx}/{len(lines)}] Processing video: {video_url}")

            transcript_items = data.get('transcript', [])
            transcript_text = " ".join([item.get('text', '') for item in transcript_items])

            # Using 'regular_comments' as 'general_comments' based on standard schema
            regular_comments = data.get('regular_comments', [])
            timestamp_comments = data.get('timestamp_comments', [])

            # Skip if there are no comments to process
            if not regular_comments and not timestamp_comments:
                print(f"[{idx}/{len(lines)}] Skipping video with no comments: {video_url}")
                continue

            # Prepare comment data strings
            general_comments_str = prepare_comments_for_prompt(regular_comments, "g")
            timestamp_comments_str = prepare_comments_for_prompt(timestamp_comments, "t")

            prompt = PROMPT_TEMPLATE.format(
                transcript=transcript_text,
                general_comments=general_comments_str,
                timestamp_comments=timestamp_comments_str
            )

            max_retries = 3
            retry_count = 0
            while retry_count < max_retries:
                try:
                    # Request structure adapted for OpenAI client targeting vLLM
                    response = client.chat.completions.create(
                        model=args.model,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that strictly outputs the requested format."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.1
                    )

                    response_text = response.choices[0].message.content.strip()

                    # Clean up potential markdown formatting just in case
                    if response_text.startswith("```json"):
                        response_text = response_text[7:]
                    if response_text.startswith("```"):
                        response_text = response_text[3:]
                    if response_text.endswith("```"):
                        response_text = response_text[:-3]
                    response_text = response_text.strip()

                    try:
                        # Parse the pipe-separated response
                        general_results = []
                        timestamp_results = []

                        for line in response_text.split('\n'):
                            line = line.strip()
                            if not line or '|' not in line:
                                continue

                            parts = line.split('|')
                            if len(parts) >= 6:
                                c_id = parts[0].strip()
                                try:
                                    info = int(parts[1].strip())
                                    opinion = int(parts[2].strip())
                                    relevance = int(parts[3].strip())
                                    total = int(parts[4].strip())
                                    is_pass = parts[5].strip().lower() == 'pass'

                                    result_obj = {
                                        "id": c_id,
                                        "scores": {"info": info, "opinion": opinion, "relevance": relevance},
                                        "total_score": total,
                                        "is_pass": is_pass
                                    }

                                    if c_id.startswith('g'):
                                        general_results.append(result_obj)
                                    elif c_id.startswith('t'):
                                        timestamp_results.append(result_obj)
                                except ValueError:
                                    continue

                        evaluation_result = {
                            "general_comments": general_results,
                            "timestamp_comments": timestamp_results
                        }
                    except Exception as e:
                        print(f"  ??Failed to parse TSV response from KORMo: {e}")
                        print(f"  Raw response: {response_text[:100]}...")
                        break  # Break out of retry loop for parsing errors

                    # Attach the evaluation result to the original data structure
                    result_data = {
                        'video_url': video_url,
                        'video_id': data.get('video_id'),
                        'title': data.get('title'),
                        'evaluation_result': evaluation_result
                    }

                    f_out.write(json.dumps(result_data, ensure_ascii=False) + '\n')
                    f_out.flush()

                    # Count passes
                    g_total = len(evaluation_result.get('general_comments', []))
                    t_total = len(evaluation_result.get('timestamp_comments', []))
                    g_pass = sum(1 for c in evaluation_result.get('general_comments', []) if c.get('is_pass'))
                    t_pass = sum(1 for c in evaluation_result.get('timestamp_comments', []) if c.get('is_pass'))
                    print(f"  ??Processed! Passed/Total: {g_pass}/{g_total} general, {t_pass}/{t_total} timestamp comments.")
                    break  # Success, break out of retry loop

                except Exception as e:
                    retry_count += 1
                    print(f"  ??Request failed. Error: {e}. Retrying ({retry_count}/{max_retries})...")
                    time.sleep(3 * retry_count)


if __name__ == "__main__":
    main()
