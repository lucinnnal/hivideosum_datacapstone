import json
import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from collections import defaultdict

# ── 데이터 로드 ──────────────────────────────────────────────────────────────
DATA_DIR = "/Users/kipyokim/Desktop/datacaptstone/filtering_results"
FILES = {
    "EXAONE 4.0": "filtered_comments_exaone_4.0.jsonl",
    "Kanana":     "filtered_comments_kanana.jsonl",
    "KORMO":      "filtered_comments_kormo.jsonl",
}

def load_model_data(filepath):
    records = []
    with open(filepath, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records

def pass_stats(comments):
    """(total, passed) 반환. 댓글 없으면 (0, 0)."""
    if not comments:
        return 0, 0
    total  = len(comments)
    passed = sum(1 for c in comments if c.get("is_pass"))
    return total, passed

# 모델별 집계: {model: {video_id: {g: (tot,pass), t: (tot,pass)}}}
model_data = {}
for model_name, filename in FILES.items():
    path = os.path.join(DATA_DIR, filename)
    records = load_model_data(path)
    model_data[model_name] = {}
    for rec in records:
        vid  = rec["video_id"]
        res  = rec["evaluation_result"]
        g_tot, g_pass = pass_stats(res.get("general_comments",   []))
        t_tot, t_pass = pass_stats(res.get("timestamp_comments", []))
        model_data[model_name][vid] = {
            "g": (g_tot, g_pass),
            "t": (t_tot, t_pass),
        }

# ── 공통 video_id 집합 ────────────────────────────────────────────────────────
all_vids = set()
for md in model_data.values():
    all_vids.update(md.keys())
all_vids = sorted(all_vids)

MODELS   = list(FILES.keys())
COLORS   = {"EXAONE 4.0": "#E15759", "Kanana": "#4E79A7", "KORMO": "#59A14F"}
BAR_W    = 0.25

# ── 집계 함수 ────────────────────────────────────────────────────────────────
def aggregate(model, vid_list, key="all"):
    tot = pass_ = 0
    for v in vid_list:
        if v not in model_data[model]:
            continue
        g_tot, g_pass = model_data[model][v]["g"]
        t_tot, t_pass = model_data[model][v]["t"]
        if key == "all":
            tot   += g_tot + t_tot
            pass_ += g_pass + t_pass
        elif key == "g":
            tot   += g_tot
            pass_ += g_pass
        elif key == "t":
            tot   += t_tot
            pass_ += t_pass
    return (pass_ / tot * 100) if tot else 0.0

# ── 비디오별 pass rate (모델×비디오) ──────────────────────────────────────────
def per_video_rates(key="all"):
    result = {}
    for m in MODELS:
        rates = []
        for v in all_vids:
            if v not in model_data[m]:
                rates.append(np.nan)
                continue
            g_tot, g_pass = model_data[m][v]["g"]
            t_tot, t_pass = model_data[m][v]["t"]
            if key == "all":
                tot, p = g_tot + t_tot, g_pass + t_pass
            elif key == "g":
                tot, p = g_tot, g_pass
            elif key == "t":
                tot, p = t_tot, t_pass
            rates.append((p / tot * 100) if tot else np.nan)
        result[m] = rates
    return result

# ── 짧은 video label ──────────────────────────────────────────────────────────
short_labels = [v[:8] for v in all_vids]

# ─────────────────────────────────────────────────────────────────────────────
# Figure 1 : 전체 댓글 pass rate
# ─────────────────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("Filtering Pass Rate – All Comments", fontsize=14, fontweight="bold")

# (A) 모델별 전체 평균 pass rate
ax = axes[0]
overall = [aggregate(m, all_vids, "all") for m in MODELS]
bars = ax.bar(MODELS, overall, color=[COLORS[m] for m in MODELS], width=0.5, edgecolor="white")
for bar, val in zip(bars, overall):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
            f"{val:.1f}%", ha="center", va="bottom", fontsize=11, fontweight="bold")
ax.set_ylim(0, 100)
ax.set_ylabel("Pass Rate (%)")
ax.set_title("Overall Average Pass Rate per Model")
ax.axhline(np.mean(overall), color="gray", linestyle="--", linewidth=1.2, label=f"Mean {np.mean(overall):.1f}%")
ax.legend(fontsize=9)
ax.grid(axis="y", alpha=0.3)

# (B) 비디오별 pass rate (grouped bar)
ax = axes[1]
rates = per_video_rates("all")
x = np.arange(len(all_vids))
for i, m in enumerate(MODELS):
    offset = (i - 1) * BAR_W
    vals = [v if not np.isnan(v) else 0 for v in rates[m]]
    ax.bar(x + offset, vals, width=BAR_W, label=m, color=COLORS[m], edgecolor="white")
ax.set_xticks(x)
ax.set_xticklabels(short_labels, rotation=45, ha="right", fontsize=8)
ax.set_ylim(0, 100)
ax.set_ylabel("Pass Rate (%)")
ax.set_title("Per-Video Pass Rate per Model")
ax.legend(fontsize=9)
ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
out1 = "/Users/kipyokim/Desktop/datacaptstone/filtering_results/fig1_overall_pass_rate.png"
plt.savefig(out1, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out1}")

# ─────────────────────────────────────────────────────────────────────────────
# Figure 2 : General vs Timestamp 구별
# ─────────────────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("Filtering Pass Rate – General vs Timestamp Comments", fontsize=14, fontweight="bold")

# (A) 모델별 G vs T 평균 pass rate (grouped bar)
ax = axes[0]
g_rates = [aggregate(m, all_vids, "g") for m in MODELS]
t_rates = [aggregate(m, all_vids, "t") for m in MODELS]
x = np.arange(len(MODELS))
b1 = ax.bar(x - 0.2, g_rates, 0.35, label="General",   color=[COLORS[m] for m in MODELS], edgecolor="white")
b2 = ax.bar(x + 0.2, t_rates, 0.35, label="Timestamp", color=[COLORS[m] for m in MODELS],
            edgecolor="white", hatch="///", alpha=0.75)
for bar, val in zip(b1, g_rates):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
            f"{val:.1f}%", ha="center", va="bottom", fontsize=9)
for bar, val in zip(b2, t_rates):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
            f"{val:.1f}%", ha="center", va="bottom", fontsize=9)
ax.set_xticks(x)
ax.set_xticklabels(MODELS)
ax.set_ylim(0, 100)
ax.set_ylabel("Pass Rate (%)")
ax.set_title("Average Pass Rate: General vs Timestamp")
# legend: solid = General, hatch = Timestamp
solid_patch = mpatches.Patch(facecolor="lightgray", edgecolor="white", label="General (solid)")
hatch_patch  = mpatches.Patch(facecolor="lightgray", edgecolor="white", hatch="///", label="Timestamp (hatch)")
ax.legend(handles=[solid_patch, hatch_patch], fontsize=9)
ax.grid(axis="y", alpha=0.3)

# (B) 비디오별 G vs T pass rate – line plot per model
ax = axes[1]
g_vid = per_video_rates("g")
t_vid = per_video_rates("t")
x = np.arange(len(all_vids))
for m in MODELS:
    ax.plot(x, g_vid[m], marker="o", color=COLORS[m], label=f"{m} General", linewidth=1.8)
    ax.plot(x, t_vid[m], marker="s", color=COLORS[m], label=f"{m} Timestamp",
            linewidth=1.8, linestyle="--", alpha=0.7)
ax.set_xticks(x)
ax.set_xticklabels(short_labels, rotation=45, ha="right", fontsize=8)
ax.set_ylim(0, 105)
ax.set_ylabel("Pass Rate (%)")
ax.set_title("Per-Video Pass Rate: General vs Timestamp")
ax.legend(fontsize=7, ncol=2)
ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
out2 = "/Users/kipyokim/Desktop/datacaptstone/filtering_results/fig2_general_vs_timestamp.png"
plt.savefig(out2, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out2}")

# ─────────────────────────────────────────────────────────────────────────────
# Figure 3 : 3-panel 요약 (전체 / General / Timestamp 평균 pass rate)
# ─────────────────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(14, 5))
fig.suptitle("Model Filtering Pass Rate Summary", fontsize=14, fontweight="bold")

panel_cfg = [
    ("All Comments",        "all"),
    ("General Comments",    "g"),
    ("Timestamp Comments",  "t"),
]
for ax, (title, key) in zip(axes, panel_cfg):
    vals = [aggregate(m, all_vids, key) for m in MODELS]
    bars = ax.bar(MODELS, vals, color=[COLORS[m] for m in MODELS], width=0.5, edgecolor="white")
    for bar, val in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
                f"{val:.1f}%", ha="center", va="bottom", fontsize=11, fontweight="bold")
    mean_val = np.nanmean([v for v in vals if v > 0])
    ax.axhline(mean_val, color="gray", linestyle="--", linewidth=1.2,
               label=f"Mean {mean_val:.1f}%")
    ax.set_ylim(0, 100)
    ax.set_ylabel("Pass Rate (%)")
    ax.set_title(title)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
out3 = "/Users/kipyokim/Desktop/datacaptstone/filtering_results/fig3_summary.png"
plt.savefig(out3, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out3}")
