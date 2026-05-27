#!/usr/bin/env python3
"""Generate multiple-choice questions (MCQs) from gold summaries with Gemini.

For each record in the chosen split, the assistant-role message (the gold
summary written during dataset construction) is sent to the Gemini API, which
returns N MCQs as JSON. The output JSONL has one record per video with the
shape::

    {
      "video_id": "...",
      "channel_name": "...",
      "questions": [
        {"id": "q0", "question": "...", "choices": {"A":..,"B":..,"C":..,"D":..}, "answer": "B"},
        ...
      ]
    }

Generation parameters are loaded from ``gemini.yaml`` (overridable via CLI).
The script is resumable — already-processed video_ids in the output file are
skipped on re-run.
"""

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Optional

import yaml

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Please install google-genai: pip install google-genai", file=sys.stderr)
    sys.exit(1)

from datasets import load_dataset


MCQ_PROMPT = """다음은 한 유튜브 영상에 대한 한국어 요약문입니다.

[요약문]
{summary}

위 요약문의 **내용**을 정확히 이해했는지 평가할 객관식 4지선다 문제 {num_questions}개를 만들어주세요.

[문제 작성 규칙]
- 각 문제는 요약문에 명시적으로 등장하는 정보만으로 풀 수 있어야 합니다.
- 정답은 요약문에 분명히 나오는 사실, 주제, 시청자 반응, 또는 집중 장면이어야 합니다.
- 오답(distractor)은 그럴듯하지만 요약문 내용과 명확히 다른 선택지여야 합니다.
- 문제 유형은 다양화해주세요 (영상 내용 / 시청자 반응 / 집중 장면 등을 골고루).
- 사소한 문구를 글자 그대로 묻기보다 핵심 내용 중심으로.
- 한국어로 작성.

[출력 형식]
순수한 JSON 객체 하나만 출력하세요. 다른 텍스트나 마크다운 코드 펜스를 절대 포함하지 마세요.

{{
  "questions": [
    {{
      "question": "질문 텍스트",
      "choices": {{"A": "보기1", "B": "보기2", "C": "보기3", "D": "보기4"}},
      "answer": "B"
    }}
  ]
}}
"""


def get_assistant_message(messages: list[dict[str, str]]) -> str:
    """Return the assistant-role content from a chat-style messages list.

    Args:
        messages: List of role/content dicts from the dataset.

    Returns:
        The assistant message content, or an empty string if absent.
    """
    return next(
        (m["content"] for m in messages if m.get("role") == "assistant"),
        "",
    )


def parse_mcq_response(text: str) -> Optional[dict[str, Any]]:
    """Parse a Gemini MCQ JSON response, tolerating code fences and prose.

    Args:
        text: Raw response string.

    Returns:
        Parsed dict on success, ``None`` otherwise.
    """
    if not text:
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def validate_questions(parsed: Any, expected: int) -> list[dict[str, Any]]:
    """Sanity-check and normalize the question list.

    A question is kept only if it has a string ``question``, a
    ``choices`` dict containing keys ``A``-``D``, and an ``answer`` that
    matches one of those keys.

    Args:
        parsed: Parsed JSON object from Gemini.
        expected: Target number of questions (used only for logging).

    Returns:
        Cleaned list of question dicts (may be shorter than expected).
    """
    if not isinstance(parsed, dict) or "questions" not in parsed:
        return []
    out: list[dict[str, Any]] = []
    for j, q in enumerate(parsed["questions"]):
        if not isinstance(q, dict):
            continue
        question = q.get("question")
        choices = q.get("choices")
        answer = q.get("answer")
        if not isinstance(question, str) or not isinstance(choices, dict):
            continue
        if not all(k in choices for k in ("A", "B", "C", "D")):
            continue
        if answer not in ("A", "B", "C", "D"):
            continue
        out.append(
            {
                "id": f"q{j}",
                "question": question.strip(),
                "choices": {k: str(choices[k]).strip() for k in ("A", "B", "C", "D")},
                "answer": answer,
            }
        )
    return out


def load_processed_ids(path: str) -> set[str]:
    """Return the set of video_ids that already appear in ``path``."""
    done: set[str] = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["video_id"])
                except Exception:
                    continue
    return done


def build_generate_config(gen_cfg: dict[str, Any]) -> "types.GenerateContentConfig":
    """Build a Gemini ``GenerateContentConfig`` from a YAML config dict."""
    thinking_cfg = gen_cfg.get("thinking", {}) or {}
    thinking_level = thinking_cfg.get("thinking_level")
    return types.GenerateContentConfig(
        temperature=gen_cfg.get("temperature", 1.0),
        top_p=gen_cfg.get("top_p", 0.95),
        max_output_tokens=gen_cfg.get("max_output_tokens", 4096),
        thinking_config=(
            types.ThinkingConfig(thinking_level=thinking_level)
            if thinking_level
            else None
        ),
        response_mime_type="application/json",
    )


def main() -> None:
    """CLI entry point — generate MCQs for a dataset split."""
    here = os.path.dirname(os.path.abspath(__file__))
    default_config = os.path.join(here, "gemini.yaml")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=default_config)
    ap.add_argument("--dataset", default="kim586w/hivideosum")
    ap.add_argument("--split", default="test")
    ap.add_argument(
        "--output",
        "-o",
        default=os.path.join(here, "data", "test_mcq.jsonl"),
    )
    ap.add_argument("--num-questions", type=int, default=4)
    ap.add_argument(
        "--project", default="hivideosum", help="GCP project for Vertex AI"
    )
    ap.add_argument("--location", default="global")
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on number of records to process (smoke test)",
    )
    args = ap.parse_args()

    if not os.path.exists(args.config):
        print(f"config not found: {args.config}", file=sys.stderr)
        sys.exit(1)
    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    model_name = cfg.get("model_name")
    gen_cfg = cfg.get("generation", {}) or {}
    generate_config = build_generate_config(gen_cfg)

    client = genai.Client(vertexai=True, project=args.project, location=args.location)

    ds = load_dataset(args.dataset, split=args.split)
    done = load_processed_ids(args.output)
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    print(f"Model      : {model_name}")
    print(f"Split      : {args.split}  ({len(ds)} records)")
    print(f"Already    : {len(done)} processed")
    print(f"Output     : {args.output}")

    written = 0
    with open(args.output, "a", encoding="utf-8") as f_out:
        for i, ex in enumerate(ds, 1):
            if args.limit and written >= args.limit:
                break
            vid = ex["video_id"]
            if vid in done:
                continue
            summary = get_assistant_message(ex["messages"]).strip()
            if not summary:
                print(f"[{i}/{len(ds)}] skip empty summary: {vid}")
                continue

            prompt = MCQ_PROMPT.format(
                summary=summary, num_questions=args.num_questions
            )

            questions: list[dict[str, Any]] = []
            for attempt in range(1, 4):
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=generate_config,
                    )
                    parsed = parse_mcq_response(resp.text or "")
                    questions = validate_questions(parsed, args.num_questions)
                    if questions:
                        break
                    print(
                        f"  attempt {attempt}/3 produced 0 valid questions; retrying"
                    )
                except Exception as e:
                    print(f"  attempt {attempt}/3 failed: {e}")
                    time.sleep(2 * attempt)

            if not questions:
                print(f"[{i}/{len(ds)}] ✗ skip {vid}: no valid questions")
                continue

            rec = {
                "video_id": vid,
                "channel_name": ex.get("channel_name"),
                "questions": questions,
            }
            f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f_out.flush()
            written += 1
            print(f"[{i}/{len(ds)}] ✓ {vid}  ({len(questions)} q)")

    print(f"\nDone. Wrote {written} new records to {args.output}")


if __name__ == "__main__":
    main()
