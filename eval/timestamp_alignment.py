#!/usr/bin/env python3
"""Timestamp alignment metric for video-summary predictions.

Compares timestamps mentioned in a model's summary (T_pred) against the
timestamps found in the input timestamp comments (T_gold) using set-based
matching with ±1s tolerance. See ../timestamp_alignment_metric.md for the
formal definition.

Macro precision / recall / F1 are reported across all videos in the chosen
split (default ``test``).
"""

import argparse
import json
import os
import re
import sys
from typing import Optional

from datasets import load_dataset


TS_PATTERN = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?(?!\d)")


def extract_timestamps(text: str) -> list[int]:
    """Extract all timestamps from text and convert to seconds.

    Supports ``M:SS``, ``MM:SS`` and ``H:MM:SS`` patterns. Components
    that overflow (mm/ss >= 60) are skipped.

    Args:
        text: Source string.

    Returns:
        List of integer seconds in order of appearance.
    """
    out: list[int] = []
    for m in TS_PATTERN.finditer(text or ""):
        a, b, c = m.groups()
        if c is None:
            mm, ss = int(a), int(b)
            if ss < 60:
                out.append(mm * 60 + ss)
        else:
            hh, mm, ss = int(a), int(b), int(c)
            if mm < 60 and ss < 60:
                out.append(hh * 3600 + mm * 60 + ss)
    return out


def align_timestamps(
    pred: list[int],
    gold: list[int],
    tolerance: int = 1,
) -> tuple[int, int, int, int]:
    """Set-based alignment between predicted and gold timestamps.

    A pred timestamp counts as TP if at least one gold value is within
    ``tolerance`` seconds; a gold timestamp counts as TP if at least one
    pred value is within tolerance. The two TP counts can differ (no 1:1
    constraint), so precision and recall are computed independently.

    Args:
        pred: Predicted timestamps in seconds.
        gold: Gold timestamps in seconds.
        tolerance: Match window in seconds.

    Returns:
        ``(tp_pred, fp, tp_gold, fn)`` for downstream metric calculation.
    """
    pred_sorted = sorted(set(pred))
    gold_sorted = sorted(set(gold))

    def any_within(target: int, lst: list[int]) -> bool:
        for v in lst:
            if v < target - tolerance:
                continue
            if v > target + tolerance:
                return False
            return True
        return False

    tp_pred = sum(1 for p in pred_sorted if any_within(p, gold_sorted))
    tp_gold = sum(1 for g in gold_sorted if any_within(g, pred_sorted))
    fp = len(pred_sorted) - tp_pred
    fn = len(gold_sorted) - tp_gold
    return tp_pred, fp, tp_gold, fn


def extract_timestamp_section(user_msg: str) -> str:
    """Slice the timestamp-comments block from a dataset user message.

    The dataset user message contains ``- 타임스탬프 댓글:`` followed by a
    numbered list. We return the substring starting at that marker.

    Args:
        user_msg: Content string of the user-role message.

    Returns:
        Substring of the timestamp section, or ``""`` if marker missing.
    """
    idx = user_msg.find("- 타임스탬프 댓글:")
    return user_msg[idx:] if idx >= 0 else ""


def load_predictions(path: str) -> dict[str, str]:
    """Read a prediction JSONL file into ``{video_id: summary}``.

    Args:
        path: Path to JSONL with at least ``video_id`` and ``summary``.

    Returns:
        Mapping from video_id to predicted summary string.
    """
    preds: dict[str, str] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            vid = d.get("video_id")
            if vid:
                preds[vid] = d.get("summary", "") or d.get("prediction", "")
    return preds


def safe_div(num: float, den: float) -> Optional[float]:
    """Return ``num / den`` or ``None`` when the denominator is zero."""
    return num / den if den else None


def macro_average(values: list[Optional[float]]) -> tuple[Optional[float], int]:
    """Average non-None values; return (mean, denominator)."""
    xs = [v for v in values if v is not None]
    return (sum(xs) / len(xs) if xs else None, len(xs))


def main() -> None:
    """CLI entry point — see ``--help`` for arguments."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--predictions",
        "-p",
        required=True,
        help="JSONL of model predictions; each line has video_id + summary",
    )
    ap.add_argument("--dataset", default="kim586w/hivideosum")
    ap.add_argument("--split", default="test")
    ap.add_argument("--tolerance", type=int, default=1)
    ap.add_argument(
        "--output",
        "-o",
        default=None,
        help="Optional path to write per-record metrics as JSONL",
    )
    args = ap.parse_args()

    if not os.path.exists(args.predictions):
        print(f"error: predictions file not found: {args.predictions}", file=sys.stderr)
        sys.exit(1)

    ds = load_dataset(args.dataset, split=args.split)

    gold_map: dict[str, list[int]] = {}
    for ex in ds:
        user_msg = next(
            (m["content"] for m in ex["messages"] if m["role"] == "user"),
            "",
        )
        section = extract_timestamp_section(user_msg)
        gold_map[ex["video_id"]] = extract_timestamps(section)

    preds = load_predictions(args.predictions)

    rows: list[dict] = []
    missing: list[str] = []

    for vid, gold in gold_map.items():
        if vid not in preds:
            missing.append(vid)
            continue
        pred_seconds = extract_timestamps(preds[vid])
        tp_pred, fp, tp_gold, fn = align_timestamps(
            pred_seconds, gold, args.tolerance
        )
        precision = safe_div(tp_pred, tp_pred + fp)
        recall = safe_div(tp_gold, tp_gold + fn)
        if precision is not None and recall is not None and (precision + recall) > 0:
            f1 = 2 * precision * recall / (precision + recall)
        else:
            f1 = None
        rows.append(
            {
                "video_id": vid,
                "n_gold": len(gold),
                "n_pred_distinct": len(set(pred_seconds)),
                "tp_pred": tp_pred,
                "fp": fp,
                "tp_gold": tp_gold,
                "fn": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )

    p_mean, p_n = macro_average([r["precision"] for r in rows])
    r_mean, r_n = macro_average([r["recall"] for r in rows])
    f_mean, f_n = macro_average([r["f1"] for r in rows])

    print(f"Evaluated {len(rows)} videos (missing predictions: {len(missing)})")
    print(f"Macro Precision : {p_mean:.4f}  (n={p_n})" if p_mean is not None else "Macro Precision : -- (n=0)")
    print(f"Macro Recall    : {r_mean:.4f}  (n={r_n})" if r_mean is not None else "Macro Recall    : -- (n=0)")
    print(f"Macro F1        : {f_mean:.4f}  (n={f_n})" if f_mean is not None else "Macro F1        : -- (n=0)")

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"per-record metrics written to {args.output}")


if __name__ == "__main__":
    main()
