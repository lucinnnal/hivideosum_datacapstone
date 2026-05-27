#!/usr/bin/env python3
"""Content-alignment metric via MCQ accuracy.

Given:
  - a JSONL of MCQs generated from the gold summaries (``--mcq``)
  - a JSONL of model predictions (``--predictions``, one record per video
    with ``video_id`` + ``summary``)

For each video, the prediction is sent to Gemini together with the MCQs and
Gemini is asked to answer **using only the prediction**. The script scores
its answers against the gold answers and reports macro / micro accuracy.

The output JSONL (``--output``) stores Gemini's answer for every question so
results are inspectable after the fact.
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


ANSWER_PROMPT = """다음은 한 유튜브 영상에 대한 요약문입니다. **이 요약문에 담긴 정보만**을 근거로 아래 객관식 질문들에 답해주세요.

[요약문]
{summary}

[질문 목록]
{questions_block}

[답변 규칙]
- 반드시 요약문에 명시적으로 등장하는 정보를 근거로 선택지를 고르세요.
- 요약문에 명확한 단서가 없다면 가장 그럴듯한 보기를 선택하세요. (반드시 하나의 답을 골라야 함)
- 답은 "A", "B", "C", "D" 중 하나로만 표기.

[출력 형식]
순수한 JSON 객체 하나만 출력하세요. 마크다운 코드 펜스 금지.

{{
  "answers": {{
    "q0": "A",
    "q1": "C"
  }}
}}
"""


def format_questions(questions: list[dict[str, Any]]) -> str:
    """Render a list of MCQ dicts as a single readable text block.

    Args:
        questions: Validated MCQs with ``id``, ``question``, ``choices``.

    Returns:
        Multi-line string presenting each question and its 4 choices.
    """
    lines: list[str] = []
    for q in questions:
        lines.append(f"[{q['id']}] {q['question']}")
        for k in ("A", "B", "C", "D"):
            lines.append(f"  {k}. {q['choices'][k]}")
        lines.append("")
    return "\n".join(lines).strip()


def parse_answers(text: str) -> dict[str, str]:
    """Parse Gemini's answer JSON, returning ``{question_id: choice}``.

    Args:
        text: Raw model response.

    Returns:
        Mapping from question id to a single-letter choice. Empty if parse
        fails or the response is malformed.
    """
    if not text:
        return {}
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    parsed: Optional[dict[str, Any]] = None
    try:
        parsed = json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                parsed = None
    if not isinstance(parsed, dict):
        return {}
    answers = parsed.get("answers")
    if not isinstance(answers, dict):
        return {}
    out: dict[str, str] = {}
    for qid, choice in answers.items():
        if isinstance(choice, str) and choice.upper() in ("A", "B", "C", "D"):
            out[qid] = choice.upper()
    return out


def load_jsonl(path: str) -> list[dict[str, Any]]:
    """Read a JSONL file into a list of dicts."""
    out: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_predictions(path: str) -> dict[str, str]:
    """Read predictions JSONL → ``{video_id: summary}``."""
    preds: dict[str, str] = {}
    for d in load_jsonl(path):
        vid = d.get("video_id")
        if vid:
            preds[vid] = d.get("summary", "") or d.get("prediction", "")
    return preds


def load_processed_ids(path: str) -> set[str]:
    """Return video_ids that already have an answer record in ``path``."""
    done: set[str] = set()
    if os.path.exists(path):
        for d in load_jsonl(path):
            vid = d.get("video_id")
            if vid:
                done.add(vid)
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
    """CLI entry point — score predictions against MCQs."""
    here = os.path.dirname(os.path.abspath(__file__))
    default_config = os.path.join(here, "gemini.yaml")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=default_config)
    ap.add_argument(
        "--mcq", default=os.path.join(here, "data", "test_mcq.jsonl"),
        help="JSONL of MCQs produced by generate_mcq.py",
    )
    ap.add_argument(
        "--predictions",
        "-p",
        required=True,
        help="JSONL of predictions; each has video_id + summary",
    )
    ap.add_argument(
        "--output",
        "-o",
        required=True,
        help="JSONL path to write per-question answers and correctness",
    )
    ap.add_argument("--project", default="hivideosum")
    ap.add_argument("--location", default="global")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    if not os.path.exists(args.config):
        print(f"config not found: {args.config}", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(args.mcq):
        print(f"mcq file not found: {args.mcq}", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(args.predictions):
        print(f"predictions file not found: {args.predictions}", file=sys.stderr)
        sys.exit(1)

    with open(args.config) as f:
        cfg = yaml.safe_load(f)
    model_name = cfg.get("model_name")
    generate_config = build_generate_config(cfg.get("generation", {}) or {})

    client = genai.Client(vertexai=True, project=args.project, location=args.location)

    mcq_records = load_jsonl(args.mcq)
    mcq_by_vid = {r["video_id"]: r for r in mcq_records}
    preds = load_predictions(args.predictions)
    done = load_processed_ids(args.output)

    targets = [vid for vid in mcq_by_vid if vid in preds and vid not in done]
    if args.limit:
        targets = targets[: args.limit]

    print(f"MCQ records   : {len(mcq_by_vid)}")
    print(f"Predictions   : {len(preds)}")
    print(f"To evaluate   : {len(targets)} (already done: {len(done)})")

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    total_correct = 0
    total_questions = 0
    per_video_accuracy: list[float] = []

    with open(args.output, "a", encoding="utf-8") as f_out:
        for i, vid in enumerate(targets, 1):
            mcq_rec = mcq_by_vid[vid]
            questions = mcq_rec.get("questions", [])
            if not questions:
                continue
            prompt = ANSWER_PROMPT.format(
                summary=preds[vid],
                questions_block=format_questions(questions),
            )

            answers: dict[str, str] = {}
            for attempt in range(1, 4):
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=generate_config,
                    )
                    answers = parse_answers(resp.text or "")
                    if answers:
                        break
                except Exception as e:
                    print(f"  attempt {attempt}/3 failed: {e}")
                    time.sleep(2 * attempt)

            qa_results = []
            correct = 0
            for q in questions:
                pred_ans = answers.get(q["id"])
                gold_ans = q["answer"]
                is_correct = pred_ans == gold_ans
                if is_correct:
                    correct += 1
                qa_results.append(
                    {
                        "id": q["id"],
                        "gold": gold_ans,
                        "pred": pred_ans,
                        "correct": is_correct,
                    }
                )

            acc = correct / len(questions) if questions else 0.0
            per_video_accuracy.append(acc)
            total_correct += correct
            total_questions += len(questions)

            f_out.write(
                json.dumps(
                    {
                        "video_id": vid,
                        "num_questions": len(questions),
                        "num_correct": correct,
                        "accuracy": acc,
                        "results": qa_results,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            f_out.flush()
            print(f"[{i}/{len(targets)}] {vid}  acc={acc:.2f}  ({correct}/{len(questions)})")

    if per_video_accuracy:
        macro = sum(per_video_accuracy) / len(per_video_accuracy)
        micro = total_correct / total_questions if total_questions else 0.0
        print(f"\nMacro accuracy : {macro:.4f}  (n_videos={len(per_video_accuracy)})")
        print(
            f"Micro accuracy : {micro:.4f}  ({total_correct}/{total_questions} questions)"
        )
    else:
        print("\nNo videos were evaluated.")


if __name__ == "__main__":
    main()
