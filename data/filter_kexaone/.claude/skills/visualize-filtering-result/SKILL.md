---
name: visualize-filtering-result
description: filtered_comments_kexaone_kkp.jsonl의 필터링 결과 및 점수(total_score·info·opinion·relevance) 분포를 전체/일반/타임스탬프 댓글 기준으로 시각화할 때 사용한다.
---

# visualize-filtering-result

`data/filtered_comments_kexaone_kkp.jsonl`을 집계해 두 가지 차트를 생성한다.

1. **필터링 결과** — 전체·일반·타임스탬프 댓글의 통과/제거 비율 (누적 막대 차트)
2. **점수 분포** — `total_score`, `info`, `opinion`, `relevance` 각각의 점수별 빈도 (묶음 막대 차트, 전체/일반/타임스탬프 3개 그룹 비교)

## 실행 방법

프로젝트 루트에서 아래 명령을 실행한다.

```bash
python3 .claude/skills/visualize-filtering-result/visualize_filtering_result.py
```

## 출력

| 항목 | 내용 |
|---|---|
| 콘솔 | 필터링 통과·제거 수 및 점수 평균/최솟값/최댓값 요약 |
| `assets/filtering_result.png` | 통과/제거 누적 막대 차트 |
| `assets/score_distribution.png` | total_score·info·opinion·relevance 점수 분포 차트 |

### 콘솔 출력 예시

```
=== 필터링 결과 ===
전체 댓글    :   150,000개  통과 72,000 (48.0%)  제거 78,000 (52.0%)
일반 댓글    :   100,000개  통과 50,000 (50.0%)  제거 50,000 (50.0%)
타임스탬프   :    50,000개  통과 22,000 (44.0%)  제거 28,000 (56.0%)

=== 점수 분포 요약 ===
[Total Score]
  전체      : 평균 6.12  최솟값 3  최댓값 9  (n=150,000)
  일반      : 평균 5.80  최솟값 3  최댓값 9  (n=100,000)
  타임스탬프: 평균 6.74  최솟값 3  최댓값 9  (n=50,000)
...
```

## 집계 기준

| 필드 | 의미 |
|---|---|
| `evaluation_result.general_comments[].is_pass` | 일반 댓글 통과 여부 |
| `evaluation_result.timestamp_comments[].is_pass` | 타임스탬프 댓글 통과 여부 |
| `evaluation_result.*.total_score` | 댓글 총점 |
| `evaluation_result.*.scores.info` | 정보성 점수 |
| `evaluation_result.*.scores.opinion` | 의견성 점수 |
| `evaluation_result.*.scores.relevance` | 관련성 점수 |
