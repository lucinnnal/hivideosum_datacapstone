import json
from collections import defaultdict

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams

OUTPUT_FILTER = 'assets/filtering_result.png'
OUTPUT_SCORES = 'assets/score_distribution.png'
FILTERED_PATH = 'data/filtered_comments_kexaone_kkp.jsonl'

SCORE_METRICS = ['total_score', 'info', 'opinion', 'relevance']
METRIC_LABELS = {
    'total_score': 'Total Score',
    'info': 'Info',
    'opinion': 'Opinion',
    'relevance': 'Relevance',
}

COLOR_PASS = '#4C9BE8'
COLOR_FAIL = '#E8A04C'
COLOR_ALL = '#6DBE6D'
COLOR_GENERAL = '#4C9BE8'
COLOR_TIMESTAMP = '#E87B4C'


def load_data(path: str) -> dict:
    """filtered_comments JSONL에서 통계 및 점수 분포를 수집한다.

    Args:
        path: filtered_comments_kexaone_kkp.jsonl 경로.

    Returns:
        {
            'general_total': int, 'general_pass': int,
            'timestamp_total': int, 'timestamp_pass': int,
            'scores': {
                'general':   {'total_score': [...], 'info': [...], 'opinion': [...], 'relevance': [...]},
                'timestamp': {'total_score': [...], 'info': [...], 'opinion': [...], 'relevance': [...]},
            }
        }
    """
    general_total = general_pass = 0
    timestamp_total = timestamp_pass = 0
    scores = {
        'general': defaultdict(list),
        'timestamp': defaultdict(list),
    }

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            er = obj.get('evaluation_result', {})

            for c in er.get('general_comments', []):
                general_total += 1
                if c.get('is_pass'):
                    general_pass += 1
                scores['general']['total_score'].append(c.get('total_score'))
                for m in ('info', 'opinion', 'relevance'):
                    scores['general'][m].append(c.get('scores', {}).get(m))

            for c in er.get('timestamp_comments', []):
                timestamp_total += 1
                if c.get('is_pass'):
                    timestamp_pass += 1
                scores['timestamp']['total_score'].append(c.get('total_score'))
                for m in ('info', 'opinion', 'relevance'):
                    scores['timestamp'][m].append(c.get('scores', {}).get(m))

    return {
        'general_total': general_total,
        'general_pass': general_pass,
        'timestamp_total': timestamp_total,
        'timestamp_pass': timestamp_pass,
        'scores': scores,
    }


def draw_filter_chart(data: dict, output_path: str) -> None:
    """필터링 결과를 누적 막대 차트로 저장한다.

    Args:
        data: load_data() 결과.
        output_path: 저장할 이미지 경로.
    """
    rcParams['font.family'] = 'AppleGothic'
    rcParams['axes.unicode_minus'] = False

    total_total = data['general_total'] + data['timestamp_total']
    total_pass = data['general_pass'] + data['timestamp_pass']
    total_fail = total_total - total_pass
    g_pass = data['general_pass']
    g_fail = data['general_total'] - g_pass
    t_pass = data['timestamp_pass']
    t_fail = data['timestamp_total'] - t_pass

    labels = ['전체 댓글', '일반 댓글', '타임스탬프 댓글']
    passes = [total_pass, g_pass, t_pass]
    fails = [total_fail, g_fail, t_fail]
    totals = [total_total, data['general_total'], data['timestamp_total']]

    fig, ax = plt.subplots(figsize=(9, 5))
    x = range(len(labels))
    bar_width = 0.5

    ax.bar(x, fails, bar_width, color=COLOR_FAIL)
    ax.bar(x, passes, bar_width, bottom=fails, color=COLOR_PASS)

    for i, (p, f, total) in enumerate(zip(passes, fails, totals)):
        pass_pct = p / total * 100 if total else 0
        fail_pct = f / total * 100 if total else 0
        if f > 0:
            ax.text(i, f / 2, f'{f:,}\n({fail_pct:.1f}%)',
                    ha='center', va='center', fontsize=9, color='white', fontweight='bold')
        if p > 0:
            ax.text(i, f + p / 2, f'{p:,}\n({pass_pct:.1f}%)',
                    ha='center', va='center', fontsize=9, color='white', fontweight='bold')
        ax.text(i, total + total * 0.01, f'합계 {total:,}',
                ha='center', va='bottom', fontsize=9, color='#333333')

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylabel('댓글 수', fontsize=10)
    ax.set_title('K-EXAONE 필터링 결과', fontsize=14, fontweight='bold', pad=16)
    ax.legend(handles=[
        mpatches.Patch(color=COLOR_PASS, label='통과'),
        mpatches.Patch(color=COLOR_FAIL, label='필터링 제거'),
    ], loc='upper right', fontsize=10)
    ax.set_ylim(0, max(totals) * 1.12)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{int(v):,}'))
    ax.spines[['top', 'right']].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()


def _score_freq(values: list) -> dict:
    """값 목록에서 각 점수의 빈도를 반환한다.

    Args:
        values: 점수 값 목록 (None 포함 가능).

    Returns:
        {score_value: count} dict (None 제외).
    """
    freq = defaultdict(int)
    for v in values:
        if v is not None:
            freq[v] += 1
    return freq


def draw_score_distribution(data: dict, output_path: str) -> None:
    """total_score·info·opinion·relevance 분포를 4개 서브플롯으로 저장한다.

    각 서브플롯은 전체(초록)/일반(파랑)/타임스탬프(주황) 세 그룹을 묶음 막대로 표시한다.

    Args:
        data: load_data() 결과.
        output_path: 저장할 이미지 경로.
    """
    rcParams['font.family'] = 'AppleGothic'
    rcParams['axes.unicode_minus'] = False

    scores = data['scores']
    all_scores = {
        m: scores['general'][m] + scores['timestamp'][m]
        for m in SCORE_METRICS
    }

    fig, axes = plt.subplots(1, 4, figsize=(18, 5))
    fig.suptitle('K-EXAONE 점수 분포 (전체 / 일반 / 타임스탬프)',
                 fontsize=14, fontweight='bold', y=1.02)

    w = 0.26
    for ax, metric in zip(axes, SCORE_METRICS):
        freq_all = _score_freq(all_scores[metric])
        freq_gen = _score_freq(scores['general'][metric])
        freq_ts = _score_freq(scores['timestamp'][metric])

        all_keys = sorted(set(freq_all) | set(freq_gen) | set(freq_ts))
        x = range(len(all_keys))

        ax.bar([i - w for i in x], [freq_all.get(k, 0) for k in all_keys],
               width=w, color=COLOR_ALL, label='전체')
        ax.bar([i for i in x], [freq_gen.get(k, 0) for k in all_keys],
               width=w, color=COLOR_GENERAL, label='일반')
        ax.bar([i + w for i in x], [freq_ts.get(k, 0) for k in all_keys],
               width=w, color=COLOR_TIMESTAMP, label='타임스탬프')

        ax.set_xticks(list(x))
        ax.set_xticklabels([str(k) for k in all_keys], fontsize=9)
        ax.set_title(METRIC_LABELS[metric], fontsize=12, fontweight='bold', pad=8)
        ax.set_xlabel('점수', fontsize=9)
        ax.set_ylabel('댓글 수', fontsize=9)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{int(v):,}'))
        ax.spines[['top', 'right']].set_visible(False)
        ax.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()


def _print_score_summary(label: str, values: list) -> None:
    """점수 목록의 평균·최솟값·최댓값을 출력한다.

    Args:
        label: 출력 레이블.
        values: 점수 값 목록.
    """
    valid = [v for v in values if v is not None]
    if not valid:
        print(f"  {label}: 데이터 없음")
        return
    avg = sum(valid) / len(valid)
    print(f"  {label}: 평균 {avg:.2f}  최솟값 {min(valid)}  최댓값 {max(valid)}  (n={len(valid):,})")


if __name__ == '__main__':
    data = load_data(FILTERED_PATH)

    total_total = data['general_total'] + data['timestamp_total']
    total_pass = data['general_pass'] + data['timestamp_pass']

    print("=== 필터링 결과 ===")
    print(f"전체 댓글    : {total_total:>8,}개  통과 {total_pass:,} ({total_pass/total_total*100:.1f}%)  제거 {total_total-total_pass:,} ({(total_total-total_pass)/total_total*100:.1f}%)")
    print(f"일반 댓글    : {data['general_total']:>8,}개  통과 {data['general_pass']:,} ({data['general_pass']/data['general_total']*100:.1f}%)  제거 {data['general_total']-data['general_pass']:,} ({(data['general_total']-data['general_pass'])/data['general_total']*100:.1f}%)")
    print(f"타임스탬프   : {data['timestamp_total']:>8,}개  통과 {data['timestamp_pass']:,} ({data['timestamp_pass']/data['timestamp_total']*100:.1f}%)  제거 {data['timestamp_total']-data['timestamp_pass']:,} ({(data['timestamp_total']-data['timestamp_pass'])/data['timestamp_total']*100:.1f}%)")

    scores = data['scores']
    all_scores = {m: scores['general'][m] + scores['timestamp'][m] for m in SCORE_METRICS}

    print("\n=== 점수 분포 요약 ===")
    for metric in SCORE_METRICS:
        print(f"[{METRIC_LABELS[metric]}]")
        _print_score_summary('전체      ', all_scores[metric])
        _print_score_summary('일반      ', scores['general'][metric])
        _print_score_summary('타임스탬프', scores['timestamp'][metric])

    draw_filter_chart(data, OUTPUT_FILTER)
    print(f"\n필터링 차트 저장 완료: {OUTPUT_FILTER}")

    draw_score_distribution(data, OUTPUT_SCORES)
    print(f"점수 분포 차트 저장 완료: {OUTPUT_SCORES}")
