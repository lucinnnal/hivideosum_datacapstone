"""
영상별 timestamp 댓글 수 vs 일반 댓글 수 분포 시각화
"""

import json
import matplotlib.pyplot as plt
import matplotlib

matplotlib.rcParams['font.family'] = 'AppleGothic'
matplotlib.rcParams['axes.unicode_minus'] = False

DATA_PATH = "comment_results/combined_data.jsonl"

ts_counts = []
reg_counts = []

with open(DATA_PATH, 'r', encoding='utf-8') as f:
    for line in f:
        data = json.loads(line)
        ts_counts.append(len(data.get('timestamp_comments', [])))
        reg_counts.append(len(data.get('regular_comments', [])))

print(f"총 영상 수: {len(ts_counts)}")
print(f"Timestamp 댓글/영상 - 평균: {sum(ts_counts)/len(ts_counts):.1f}, 최소: {min(ts_counts)}, 최대: {max(ts_counts)}")
print(f"일반 댓글/영상     - 평균: {sum(reg_counts)/len(reg_counts):.1f}, 최소: {min(reg_counts)}, 최대: {max(reg_counts)}")

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle('영상별 댓글 수 분포', fontsize=15, fontweight='bold')

colors = ['#4C72B0', '#DD8452']

ax = axes[0]
ax.hist(ts_counts, bins=20, color=colors[0], edgecolor='white', alpha=0.85)
ax.set_xlabel('Timestamp 댓글 수')
ax.set_ylabel('영상 수')
ax.set_title('Timestamp 댓글 per Video')
ax.axvline(sum(ts_counts)/len(ts_counts), color='red', linestyle='--', label=f'평균: {sum(ts_counts)/len(ts_counts):.1f}')
ax.legend()

ax = axes[1]
ax.hist(reg_counts, bins=20, color=colors[1], edgecolor='white', alpha=0.85)
ax.set_xlabel('일반 댓글 수')
ax.set_ylabel('영상 수')
ax.set_title('일반 댓글 per Video')
ax.axvline(sum(reg_counts)/len(reg_counts), color='red', linestyle='--', label=f'평균: {sum(reg_counts)/len(reg_counts):.1f}')
ax.legend()

plt.tight_layout()
plt.savefig('output_dir/comment_stats.png', dpi=150, bbox_inches='tight')
plt.show()
print("차트 저장: output_dir/comment_stats.png")
