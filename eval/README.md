# Evaluation

테스트셋(`kim586w/hivideosum` 의 `test` split, 202 records, train-disjoint 채널 12개)에 대해 모델이 생성한 요약본의 품질을 측정하기 위한 두 가지 지표를 정의합니다.

| 지표 | 무엇을 보는가 | 어떻게 측정 |
| --- | --- | --- |
| **Timestamp Alignment** | 예측 요약본에 적힌 시간(`3:24`)들이 입력 타임스탬프 댓글의 시간과 얼마나 일치하는가 — 환각 방지 + 커버리지 | 두 timestamp 집합의 set-based Precision / Recall / F1 (`±1s` tolerance). Gold는 [test_gold_timestamps.jsonl](https://huggingface.co/datasets/kim586w/hivideosum/blob/main/test_gold_timestamps.jsonl)에 미리 파싱됨 |
| **Content Alignment** | 예측 요약본이 정답 요약본과 **내용적으로** 얼마나 같은가 (단어 일치가 아니라 의미 일치) | 정답 요약본으로 만들어진 객관식 4지선다(MCQ, [test_mcq.jsonl](https://huggingface.co/datasets/kim586w/hivideosum/blob/main/test_mcq.jsonl))를, Gemini가 **예측 요약본만 보고** 풀게 해서 그 정답률 |

---

## 사전 준비

### 1) 의존성

```bash
pip install datasets pyyaml google-genai
```

### 2) Vertex AI 인증

두 MCQ 스크립트(`generate_mcq.py`, `evaluate_mcq.py`)는 Vertex AI를 통해 Gemini를 호출합니다. 한 번만 실행하면 됩니다:

```bash
gcloud auth application-default login
```

기본 GCP 프로젝트는 `hivideosum`, 리전은 `global`로 설정되어 있어요(`--project` / `--location`으로 override 가능).

### 3) 예측 파일(prediction file) 포맷

평가 대상 모델이 테스트셋 각 영상에 대해 만든 요약본을 JSONL 한 줄씩 저장합니다.

```jsonl
{"video_id": "abc123", "summary": "..."}
{"video_id": "def456", "summary": "..."}
```

`video_id`는 HF 데이터셋의 `video_id`와 같아야 합니다.

---

## 평가 진행 순서

```
              ┌──────────────────────────────────────────────────────┐
              │  Step 0. (1회) MCQ 생성 — 정답 요약본으로부터 4지선다 4개 ──→ test_mcq.jsonl │
              └──────────────────────────────────────────────────────┘
                                       │ (HF에 업로드되어 있으니 보통 건너뜀)
                                       ▼
              ┌──────────────────────────────────────────────────────┐
              │  Step 1. 평가할 모델로 테스트셋 202개 요약 생성       ──→ predictions.jsonl │
              └──────────────────────────────────────────────────────┘
                                       │
                                       ▼
              ┌──────────────────────────────────────────────────────┐
              │  Step 2. Timestamp Alignment 계산                                  │
              │  Step 3. Content Alignment (MCQ)  계산                              │
              └──────────────────────────────────────────────────────┘
```

### Step 0 — MCQ 생성 (보통 건너뜀)

이미 생성된 MCQ가 HF 데이터셋(`kim586w/hivideosum`)에 [`test_mcq.jsonl`](https://huggingface.co/datasets/kim586w/hivideosum/blob/main/test_mcq.jsonl)로 올라가 있어 다시 만들 필요는 없습니다. 직접 만들고 싶다면:

```bash
python eval/generate_mcq.py \
    --split test \
    --num-questions 4 \
    --output eval/data/test_mcq.jsonl
```

기본 입력은 HF의 `kim586w/hivideosum:test`의 assistant 메시지(=정답 요약본).

### Step 1 — 예측 요약본 만들기

평가할 sLLM이 `kim586w/hivideosum:test`의 202개 영상에 대해 요약을 만들어 `predictions.jsonl`로 저장합니다 (포맷은 위 참조).

### Step 2 — Timestamp Alignment

미리 파싱해둔 gold timestamps([`test_gold_timestamps.jsonl`](https://huggingface.co/datasets/kim586w/hivideosum/blob/main/test_gold_timestamps.jsonl))을 받아쓰면 매번 입력 댓글에서 정규식으로 다시 파싱할 필요가 없어요:

```bash
mkdir -p eval/data
huggingface-cli download kim586w/hivideosum test_gold_timestamps.jsonl \
    --repo-type dataset --local-dir eval/data --local-dir-use-symlinks False

python eval/timestamp_alignment.py \
    --predictions path/to/predictions.jsonl \
    --gold-file   eval/data/test_gold_timestamps.jsonl \
    --output      eval/data/timestamp_per_video.jsonl
```

`--gold-file`을 생략하면 HF 데이터셋을 직접 로드해서 파싱합니다. 표준 출력에 Macro Precision / Recall / F1이 찍히고, `--output`을 주면 영상별 metric이 JSONL로 떨어집니다.

**`test_gold_timestamps.jsonl` 포맷:**

```jsonl
{"video_id": "abc123", "channel_name": "...", "gold_timestamps": [105, 224, 430, 725]}
```

`gold_timestamps`는 입력 타임스탬프 댓글에서 정규식으로 뽑은 초 단위 정수 리스트.

### Step 3 — Content Alignment (MCQ 정확도)

먼저 HF에서 미리 생성된 MCQ ([`test_mcq.jsonl`](https://huggingface.co/datasets/kim586w/hivideosum/blob/main/test_mcq.jsonl))를 받아옵니다 (`eval/data/`는 `.gitignore`로 관리):

```bash
mkdir -p eval/data
huggingface-cli download kim586w/hivideosum test_mcq.jsonl \
    --repo-type dataset --local-dir eval/data --local-dir-use-symlinks False
```

그다음 평가:

```bash
python eval/evaluate_mcq.py \
    --mcq         eval/data/test_mcq.jsonl \
    --predictions path/to/predictions.jsonl \
    --output      eval/data/mcq_results.jsonl
```

표준 출력에 Macro / Micro accuracy가 찍히고, `--output`에는 질문별 채점 결과가 JSONL로 떨어집니다.

---

## 1. Timestamp Alignment 자세히

### 개념

- **T_gold**: 입력 *타임스탬프 댓글*에 등장한 시간 집합 (초 단위로 정규화)
- **T_pred**: *예측 요약본*에 등장한 시간 집합 (초 단위로 정규화)
- **매칭**: 한쪽 timestamp 옆 `±1초` 안에 다른 쪽 timestamp가 하나라도 있으면 정답 처리 (1:1 매칭 아님)
- **집계**: 영상별로 P/R/F1을 구한 뒤 **macro 평균** (gold나 pred가 비어있는 영상은 그 지표에서 제외)

### 무엇을 보고 싶은가

- **Precision 높음** ⇒ 모델이 적은 timestamp는 거의 다 입력 timestamp 댓글에 근거가 있음. **환각이 적음**.
- **Recall 높음**  ⇒ 입력에서 시청자들이 주목한 시점을 요약본이 **잘 커버**함.
- **Recall이 낮은 경우의 해석**: 타임스탬프 댓글이 수십~100개 이상인 영상은 모델이 일부만 골라 쓰는 게 자연스러우므로 댓글 수가 많을수록 자연 감소. 그래도 macro recall이 절망적으로 낮다면 모델이 시점을 거의 안 적는 것이라 봐야 함.

### 정규식 (요약문에서 시간 추출)

```python
TS_PATTERN = re.compile(r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?(?!\d)")
```

`M:SS`, `MM:SS`, `H:MM:SS` 형태를 모두 잡되 분/초가 60 이상이면 버립니다.

### 예시 (tolerance = ±1s)

입력 타임스탬프 댓글에서 뽑은 gold (초):

```
gold = [204, 205, 430, 725, 1110]   # 3:24, 3:25, 7:10, 12:05, 18:30
```

예측 요약본에서 뽑은 pred (초):

```
pred = [204, 205, 431, 725, 1800]   # 3:24, 3:25, 7:11, 12:05, 30:00
```

| pred | gold ±1초 안에 있나 | 판정 |
| --- | --- | --- |
| 204 | 204 (Δ=0) | ✅ TP |
| 205 | 205 (Δ=0) | ✅ TP |
| 431 | 430 (Δ=1) | ✅ TP |
| 725 | 725 (Δ=0) | ✅ TP |
| 1800 | (최근접 1110, Δ=690) | ❌ FP |

→ tp_pred = 4, fp = 1

| gold | pred ±1초 안에 있나 | 판정 |
| --- | --- | --- |
| 204 | 204 | ✅ |
| 205 | 205 | ✅ |
| 430 | 431 (Δ=1) | ✅ |
| 725 | 725 | ✅ |
| 1110 | (최근접 725, Δ=385) | ❌ FN |

→ tp_gold = 4, fn = 1

- **Precision** = 4 / (4+1) = **0.80**
- **Recall**    = 4 / (4+1) = **0.80**
- **F1**        = **0.80**

---

## 2. Content Alignment (MCQ Accuracy) 자세히

### 개념

문자 단위 일치(BLEU/ROUGE)나 임베딩 유사도는 "문체가 비슷하면 잘 한 것처럼 보이는" 문제가 있어요. 이걸 피하려고 **이 영상의 핵심 사실들을 객관식 문제로 환원**한 뒤, 모델 요약본이 그 문제를 풀 정도로 충분한 정보를 담고 있는지를 봅니다.

### 파이프라인

```
        정답 요약본 (assistant message)
                    │
                    ▼  (Gemini, 영상당 4문항)  ←── 1회만 수행, HF에 캐싱
            ┌──────────────────────┐
            │  test_mcq.jsonl       │
            │  · video_id           │
            │  · questions[ ]       │
            │     · question        │
            │     · choices A/B/C/D │
            │     · answer (gold)   │
            └──────────────────────┘
                    │
                    ▼  + 예측 요약본 (predictions.jsonl)
                    │
                    ▼  (Gemini, 정답 제외하고 보기만 제공)
            ┌──────────────────────┐
            │  Gemini 의 응답 {q0:?, q1:?, ...}      │
            └──────────────────────┘
                    │
                    ▼  gold answer 와 비교
            정답률 = 맞춘 문항 수 / 전체 문항 수
```

### 채점

- **Macro accuracy**: 영상별 정답률(맞춘 수 / 그 영상의 문항 수)을 평균
- **Micro accuracy**: 전체 맞춘 문항 / 전체 문항

### MCQ 생성 프롬프트 (요약본 → 4지선다 4문항)

```text
다음은 한 유튜브 영상에 대한 한국어 요약문입니다.

[요약문]
{summary}

위 요약문의 **내용**을 정확히 이해했는지 평가할 객관식 4지선다 문제 4개를 만들어주세요.

[문제 작성 규칙]
- 각 문제는 요약문에 명시적으로 등장하는 정보만으로 풀 수 있어야 합니다.
- 정답은 요약문에 분명히 나오는 사실, 주제, 시청자 반응, 또는 집중 장면이어야 합니다.
- 오답(distractor)은 그럴듯하지만 요약문 내용과 명확히 다른 선택지여야 합니다.
- 문제 유형은 다양화해주세요 (영상 내용 / 시청자 반응 / 집중 장면 등을 골고루).
- 사소한 문구를 글자 그대로 묻기보다 핵심 내용 중심으로.
- 한국어로 작성.

[출력 형식]
순수한 JSON 객체 하나만 출력하세요. 마크다운 코드 펜스 절대 금지.

{ "questions": [ { "question": "...", "choices": {"A":"...","B":"...","C":"...","D":"..."}, "answer": "B" }, ... ] }
```

→ `eval/data/test_mcq.jsonl` 각 줄:

```json
{
  "video_id": "abc123",
  "channel_name": "...",
  "questions": [
    {"id": "q0", "question": "...", "choices": {"A": "...", "B": "...", "C": "...", "D": "..."}, "answer": "B"},
    ...
  ]
}
```

### MCQ 풀이 프롬프트 (예측 요약본 + 보기 → 답)

```text
다음은 한 유튜브 영상에 대한 요약문입니다. **이 요약문에 담긴 정보만**을 근거로 아래 객관식 질문들에 답해주세요.

[요약문]
{prediction_summary}    ← gold가 아니라 모델 예측본

[질문 목록]
[q0] ... (질문)
  A. ...
  B. ...
  C. ...
  D. ...

[q1] ...

[답변 규칙]
- 반드시 요약문에 명시적으로 등장하는 정보를 근거로 선택지를 고르세요.
- 요약문에 명확한 단서가 없다면 가장 그럴듯한 보기를 선택. (반드시 하나 고를 것)
- 답은 "A","B","C","D" 중 하나로만.

[출력 형식]
순수한 JSON 객체 하나만 출력하세요.

{ "answers": { "q0": "A", "q1": "C", ... } }
```

채점 시에는 `q_i`별로 Gemini의 답이 `test_mcq.jsonl`의 `answer`와 같은지 확인합니다.

### 예시

`test_mcq.jsonl`의 어떤 영상에 다음과 같은 문항이 있다고 하면 (gold 정답: **B**):

```
[q1] 시청자들이 이 영상을 '최고의 다이어트 영상'이라고 평가한 주요 이유는?
  A. 곤충 요리법이 매우 간단하고 따라 하기 쉬워서
  B. 곤충을 먹는 모습에 식욕이 사라져 야식을 참을 수 있어서  ← gold
  C. 체중 감량을 위한 격투기 훈련법이 자세히 나와서
  D. 곤충 쿠키가 맛있는 다이어트 간식처럼 보여서
```

- 예측 요약본에 "시청자들은 곤충을 먹는 장면 때문에 식욕이 사라져 야식을 참게 된다는 반응이 많았다"는 문장이 있으면 → Gemini는 보통 **B**를 답함 → 정답.
- 예측 요약본에 시청자 반응 자체가 누락돼 있으면 → Gemini는 추측으로 답하므로 **틀릴 확률이 높음** → 오답으로 카운트.

즉 **요약본에 그 정보가 들어있는가**를 객관식으로 환산한 셈입니다.

---

## 파일 구성

```
eval/
├── README.md                          # 이 파일
├── timestamp_alignment.py             # Timestamp metric (prediction file 입력)
├── generate_mcq.py                    # Gemini로 MCQ 생성 (정답 요약본 입력)
├── evaluate_mcq.py                    # Gemini로 MCQ 풀이 & 채점 (예측 요약본 입력)
├── gemini.yaml                        # Gemini 생성 설정 (모델/temperature/thinking)
└── data/
    └── test_mcq.jsonl                 # 미리 생성된 MCQ (Step 0 결과)
```

## 주의

- 두 metric 모두 **테스트셋의 video_id 기준**으로 join합니다. prediction JSONL에 누락된 video_id가 있으면 그 영상은 평가에서 빠집니다.
- MCQ는 정답 요약본에 의존하므로 정답 요약본의 품질이 곧 평가의 상한입니다. 정답 요약본 자체에 잘못된 정보가 있으면 해당 문항도 잘못된 정답으로 채점될 수 있어요.
- Gemini 호출은 비용이 들기 때문에 `test_mcq.jsonl`은 한 번만 생성해서 HF에 캐싱했습니다. 새로 만들 필요가 있을 때만 `generate_mcq.py`를 돌리세요.
