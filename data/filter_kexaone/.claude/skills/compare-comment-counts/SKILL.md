---
name: compare-comment-counts
description: filtered_comments_kexaone_kkp.jsonl의 video_url별 일반/timestamp 댓글 수가 combined_data_no_overlap_merged.jsonl의 대응 video_url과 일치하는지 검증해야 할 때 사용한다.
---

# compare-comment-counts

`data/filtered_comments_kexaone_kkp.jsonl`의 각 video_url별 일반 댓글 수·timestamp 댓글 수가
`data/combined_data_no_overlap_merged.jsonl`의 동일 video_url과 일치하는지 비교한다.

## 비교 기준

| filtered 파일 필드 | combined 파일 필드 |
|---|---|
| `evaluation_result.general_comments` (len) | `regular_comments` (len) |
| `evaluation_result.timestamp_comments` (len) | `timestamp_comments` (len) |

## 실행 방법

프로젝트 루트에서 아래 명령을 실행한다.

```bash
python3 .claude/skills/compare-comment-counts/compare_comment_counts.py
```

## 출력 해석

- **완전 일치**: 양쪽 파일에서 일반 댓글 수·timestamp 댓글 수가 모두 동일한 video_url 수.
- **일반 댓글만 불일치**: `evaluation_result.general_comments` 수 ≠ `regular_comments` 수인 video_url.
- **timestamp만 불일치**: `evaluation_result.timestamp_comments` 수 ≠ `timestamp_comments` 수인 video_url.
- **둘 다 불일치**: 두 가지 모두 다른 video_url.
- **combined에 없는 url**: filtered에는 있지만 combined에 대응 항목이 없는 경우 (크롤링 누락 가능성).

## 불일치 로그 (`data/mismatch_log.json`)

스크립트 실행 시 불일치 항목을 `data/mismatch_log.json`에 자동으로 누적 기록한다.

### 동작 방식

| 상황 | 처리 |
|---|---|
| 이번 실행에서 새로 발견된 불일치 url | `first_seen`, `last_seen` = 오늘 날짜로 신규 추가 |
| 이전에도 불일치였고 이번에도 불일치 | `last_seen` 및 filtered 수치 갱신 |
| 이전에 불일치였으나 이번에 일치로 바뀜 | 로그에서 삭제 (일치 항목은 기록하지 않음) |

### 로그 항목 구조

```json
{
  "https://www.youtube.com/watch?v=XXXX": {
    "video_url": "https://www.youtube.com/watch?v=XXXX",
    "mismatch_type": "general_only | timestamp_only | both | not_found",
    "filtered_general": 99,
    "combined_regular": 100,
    "filtered_timestamp": 18,
    "combined_timestamp": 18,
    "first_seen": "2026-04-23",
    "last_seen": "2026-04-23"
  }
}
```

### 실행 후 출력 예시

```
[mismatch_log.json 업데이트]
  신규 추가     : 5개
  수치 갱신     : 10개
  로그에서 제거 : 2개
  저장 경로     : data/mismatch_log.json
```

## 주요 불일치 원인 (기존 분석 결과 기준)

| video_id | 원인 추정 |
|---|---|
| `iqPlYzJVLeU`, `0Gpd_N0KLhs` | 평가 중 일반 댓글 1개 누락 |
| `MguTO0bHAME` | 100개 중 43개만 평가 포함 (부분 처리) |
| `GzC0dKkRWQk` | 일반 댓글 1개·timestamp 4개만 평가 (중단 가능성) |
