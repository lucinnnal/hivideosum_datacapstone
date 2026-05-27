# timestamp_alignment_metric

# Timestamp Alignment Metric

요약 모델이 입력 타임스탬프 댓글의 시점들을 얼마나 정확하게 요약문에 반영했는지 측정하는 지표.

## 1. 정의

- **Gold (T_gold)**: 입력 타임스탬프 댓글에 등장하는 타임스탬프 집합 (초 단위)
- **Pred (T_pred)**: 모델이 생성한 요약문에 등장하는 타임스탬프 집합 (초 단위)
- **매칭 기준 (set-based)**:
    - Pred의 각 시점은 gold 중 `|Δ| ≤ 1초`가 **하나라도 있으면** 정답 처리 (precision용 TP)
    - Gold의 각 시점은 pred 중 `|Δ| ≤ 1초`가 **하나라도 있으면** 커버됨 (recall용 TP)
    - 1:1 제약 없음 → 한 gold가 여러 pred를 동시에 커버할 수 있고, 요약문이 같은 장면을 여러 번 언급해도 페널티 없음

지표:

| 이름 | 정의 | 의미 |
| --- | --- | --- |
| Precision | TP / (TP + FP) | 요약에 등장한 타임스탬프 중 입력에서 근거를 찾을 수 있는 비율 (환각 방지) |
| Recall | TP / (TP + FN) | 입력 타임스탬프 중 요약에 반영된 비율 (정보 커버리지) |
| F1 | 2·P·R / (P+R) | 둘의 조화평균 |

집계는 **macro 평균** (영상별 P·R·F1을 평균; gold/pred가 비어있는 영상은 해당 지표에서 제외).

## 2. 알고리즘

### 2.1 타임스탬프 추출

정규식으로 `M:SS`, `MM:SS`, `H:MM:SS` 모두 지원. 초/분이 60 이상이면 무시.

```python
TS_PATTERN = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?(?!\d)")

def extract_timestamps(text: str) -> list[int]:
    out = []
    for m in TS_PATTERN.finditer(text):
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
```

### 2.2 매칭 (set-based, ±1초)

각 pred 시점에 대해 gold 중 tolerance 이내가 하나라도 있으면 정답으로 인정. 반대로 gold 쪽도 pred 중 tolerance 이내가 있으면 커버된 것으로 처리. 1:1 제약이 없으므로 precision용 TP와 recall용 TP가 다를 수 있어요.

```python
def align_timestamps(pred, gold, tolerance=1):
    pred_sorted = sorted(set(pred))
    gold_sorted = sorted(set(gold))

    def any_within(target, sorted_list):
        for v in sorted_list:
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
```

Precision = `tp_pred / (tp_pred + fp)`, Recall = `tp_gold / (tp_gold + fn)`.

## 3. 계산 예시

실제로 어떻게 점수가 매겨지는지 단계별로 풀어보는 가상 예시. tolerance = ±1초.

### 입력

**Gold — 타임스탬프 댓글 (user 메시지):**

```
1. 3:24 여기 진짜 웃김
2. 3:25 (다른 시청자가 같은 장면을 적음)
3. 7:10 이 부분 명장면
4. 12:05 BGM 뭔가요?
5. 18:30 마지막에 감동
```

**Pred — 모델 요약 (assistant 메시지):**

```
... 3:24에서는 ~ 그리고 3:25에서도 출연자가 ...
7:11 부근에서는 명장면이라는 평이 ...
12:05에 깔린 BGM ...
30:00 부근에서는 ...
```

### Step 1. 타임스탬프 추출 (초 단위)

- `gold = [204, 205, 430, 725, 1110]` (3:24, 3:25, 7:10, 12:05, 18:30)
- `pred = [204, 205, 431, 725, 1800]` (3:24, 3:25, 7:11, 12:05, 30:00)

### Step 2. Precision용 TP — pred 각각이 gold ±1초 안에 있는가

| pred | gold 중 ±1초 안 | 판정 |
| --- | --- | --- |
| 204 (3:24) | 204 (Δ=0) | ✅ |
| 205 (3:25) | 205 (Δ=0) | ✅ |
| 431 (7:11) | 430 (Δ=1) | ✅ |
| 725 (12:05) | 725 (Δ=0) | ✅ |
| 1800 (30:00) | 가장 가까운 1110 (Δ=690) | ❌ FP |

→ **tp_pred = 4, FP = 1**

### Step 3. Recall용 TP — gold 각각이 pred ±1초 안에 있는가

| gold | pred 중 ±1초 안 | 판정 |
| --- | --- | --- |
| 204 (3:24) | 204 (Δ=0) | ✅ |
| 205 (3:25) | 205 (Δ=0) | ✅ |
| 430 (7:10) | 431 (Δ=1) | ✅ |
| 725 (12:05) | 725 (Δ=0) | ✅ |
| 1110 (18:30) | 가장 가까운 725 (Δ=385) | ❌ FN |

→ **tp_gold = 4, FN = 1**

### Step 4. 지표

- **Precision** = tp_pred / (tp_pred + FP) = 4 / 5 = **0.80**
- **Recall** = tp_gold / (tp_gold + FN) = 4 / 5 = **0.80**
- **F1** = 2·0.80·0.80 / (0.80 + 0.80) = **0.80**

## 4. 실행 결과 (Hub 9,984 records, tolerance ±1s)

전체 `kim586w/hivideosum_training_dataset` 학습 데이터의 (gemini-생성) 어시스턴트 요약을 평가한 결과.

### Macro

| 지표 | 값 | 분모 (해당 지표가 정의된 레코드 수) |
| --- | --- | --- |
| Precision | **0.9796** | 9,910 |
| Recall | **0.7039** | 9,875 |
| F1 | **0.7745** | 9,85 |
- **Precision이 매우 높음 (0.98)**: 최종 요약본은 timestamp 관련 환각이 낮음을 보여줌
- **Macro Recall은 0.67**: 어느 정도 정답 timestamp를 반영하고 있음
- **Micro Recall이 macro보다 훨씬 낮음 (0.37 vs 0.67)**: 타임스탬프 댓글이 많은(수십~100개) 영상에서 모델이 일부만 골라 쓰기 때문. 타임스탬프 댓글이 10개 이내인 영상에서는 잘 커버, 100개 이상인 영상에서는 자연스럽게 압축. → 골라쓰는 구조이기 때문에 타임스탬프 댓글이 많을 수록 recall 값이 작아질 수도 있다고 생각함