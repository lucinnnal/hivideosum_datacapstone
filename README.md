# Hi-VideoSum

> A User-Centric YouTube Video Summarization & Highlight Service for Korean
>
> Sungkyunkwan University · AI Convergence · Data Science Capstone (2026)

Hi-VideoSum은 **영상 프레임을 보지 않고** 두 가지 텍스트 신호—**자막(transcript)** 과 **시청자 댓글(comments)** —만으로 한국어 유튜브 영상을 3문단 산문으로 요약하는 sLLM 기반 서비스입니다.

- 📄 **Dataset:** [`kim586w/hivideosum_training_dataset`](https://huggingface.co/datasets/kim586w/hivideosum_training_dataset)
- 🌐 **Project page:** [`docs/page/index.html`](docs/page/index.html)
- 📝 **Mid-term report:** [`docs/report/main.tex`](docs/report/main.tex)

---

## Repository layout

```
hivideosum/
├── data/                              # Dataset construction pipeline
│   ├── crawl_raw_data/                # Step 1–2 — channel curation, transcript & comment scrape
│   ├── filter_kexaone/                # Step 3–4 — 3-axis comment filtering (Gemini / K-EXAONE)
│   └── summarize/                     # Step 5–6 — label generation + HF fine-tuning dataset build
├── training/
│   └── gemma_lora/                    # Step 6    — gemma-4-E4B-it LoRA fine-tuning
├── service/
│   ├── backend/                       # FastAPI + arq worker + vLLM serving
│   └── extension/                     # Chrome MV3 extension (YouTube watch-page sidebar)
└── docs/
    ├── page/                          # Static project landing page (index.html)
    └── report/                        # LaTeX mid-term report (XeLaTeX)
```

Each leaf directory keeps its own `README.md` with run instructions; the per-module READMEs are authoritative for execution.

---

## End-to-end pipeline

```
┌────────────────────────── data/ ──────────────────────────┐    ┌── training/ ──┐    ┌────── service/ ──────┐
│                                                            │    │                │    │                       │
│  crawl_raw_data ──► filter_kexaone ──► summarize           │ ─► │  gemma_lora    │ ─► │  backend (vLLM+API)   │
│  (yt-dlp,            (Elice K-EXAONE     (Gemini / EXAONE   │    │  LoRA r=32,    │    │  + extension (Chrome) │
│   yt-transcript-api,  3-axis 1–3)         3-paragraph       │    │  α=64,         │    │                       │
│   yt-comment-dl)                          prose labels)     │    │  bf16, seq 20k)│    │                       │
└────────────────────────────────────────────────────────────┘    └────────────────┘    └───────────────────────┘
```

| # | Stage | Where | Output |
|---|-------|-------|--------|
| 1 | Channel curation                       | `data/crawl_raw_data/inputs/channels.jsonl` | ≈80 Korean channels, 7 top-level + 16 sub-categories |
| 2 | Raw collection (transcript + comments) | `data/crawl_raw_data/`                       | `combined_data.jsonl` per channel                       |
| 3 | Rule-based filter (regex, ratio)       | `data/crawl_raw_data/`                       | timestamped vs general comments split                   |
| 4 | 3-axis LLM filter (info / opinion / relevance ≥ 6) | `data/filter_kexaone/`           | `filtered_comments_gemini.jsonl` (or `_kexaone.jsonl`)  |
| 5 | 3-paragraph prose label generation     | `data/summarize/`                            | `summarized_data_gemini.jsonl` (training labels)        |
| 5b | HF fine-tuning dataset build (+ push) | `data/summarize/`                            | `finetune_dataset.jsonl` → HF Hub                       |
| 6 | sLLM LoRA fine-tune                    | `training/gemma_lora/`                       | `output/adapter_model.safetensors`                      |
| 7 | Web service (FastAPI + arq + vLLM)     | `service/backend/`                           | `POST /jobs` → 30–120s → 3-paragraph summary            |
| 8 | Chrome extension (sidebar on YouTube)  | `service/extension/`                         | DOM-injected `#hvs-panel` calling the backend           |

---

## Component smoke tests

각 컴포넌트(① 수집, ② 필터링, ③ 요약, ④ 데이터셋 생성)가 정상 동작하는지 빠르게 확인하기 위한 가이드입니다. 모든 명령은 해당 모듈 디렉토리에서 실행하며, 각 모듈의 README에 더 상세한 옵션이 있습니다.

### 사전 준비 (공통)

```bash
# 저장소 클론 후 최상위에서
cd data/<module>            # crawl_raw_data | filter_kexaone | summarize
conda activate <env>        # 각 모듈별 권장 conda env (아래 표 참고)
pip install -r requirements.txt
```

| 컴포넌트 | 권장 conda env | 인증 / 키 |
|---|---|---|
| ① 수집 | `datacapstone` (Python 3.10) | (선택) `WEBSHARE_PROXY_*` 프록시 |
| ② 필터링 (Gemini) | `gemini_api` (Python 3.11) | `gcloud auth application-default login` |
| ② 필터링 (K-EXAONE) | `kexaone_filter` (Python 3.11) | `K_EXAONE_API_KEY` |
| ③ 요약 (Gemini) | `gemini_api` (Python 3.11) | `gcloud auth application-default login` |
| ④ 데이터셋 생성 | `gemini_api` 재사용 가능 | (push 시) `huggingface-cli login` |

---

### 1) 댓글 및 자막 크롤링 테스트

**위치**: `data/crawl_raw_data/`

```bash
cd data/crawl_raw_data
conda activate datacapstone
pip install -r requirements.txt

# 1-1. 채널 1~2개만 담은 테스트 입력 준비
mkdir -p inputs
cat > inputs/channels.test.jsonl <<'EOF'
{"channel_url": "https://www.youtube.com/@channel_handle", "channel_name": "테스트채널"}
EOF

# 1-2. fetch_limit를 작게 잡고 실행
# (수집 조건 — 길이 5~30분 / 댓글 5개 미만 영상 자동 스킵 — 때문에
#  fetch_limit=3 이면 최종 0~3 라인이 나올 수 있어 채널당 10~20 권장)
./scripts/crowl_comments.sh inputs/channels.test.jsonl comment_results_test 15
```

**확인 포인트**

- `comment_results_test/combined_data.jsonl` 가 생성되고 최소 1라인 이상 기록되었는지
- 각 레코드에 `transcript`, `regular_comments`, `timestamp_comments` 필드가 비어있지 않은지
- `video_log.json` 의 상태 분포 (`collected` / `skipped` / `error`) — 전부 skipped 라면 채널·`fetch_limit` 조정 필요

```bash
# 빠른 검증
wc -l comment_results_test/combined_data.jsonl
python -c "import json; r=[json.loads(l) for l in open('comment_results_test/combined_data.jsonl')]; \
print('videos:', len(r), 'avg_regular:', sum(len(x.get('regular_comments',[])) for x in r)/max(len(r),1))"
```

---

### 2) 댓글 필터링 테스트 (Gemini 3 Flash Preview · Vertex AI)

**위치**: `data/filter_kexaone/`  
**모델**: `gemini-3-flash-preview` (gcloud ADC + Vertex AI; 요약 모듈과 동일한 인증 방식)

```bash
cd data/filter_kexaone
conda create -n gemini_api python=3.11 -y          # 최초 1회
conda activate gemini_api
pip install -r requirements.txt                    # google-genai, google-cloud-aiplatform 포함

# 최초 1회 ADC 로그인 (요약과 공용 — 이미 했으면 생략)
gcloud auth application-default login

# 2-1. 크롤링 결과를 입력으로 복사 (5~10 라인만 잘라서 테스트 권장)
mkdir -p data
head -n 5 ../crawl_raw_data/comment_results_test/combined_data.jsonl \
  > data/combined_data_merged.jsonl

# 2-2. 실행
bash scripts/run_filter_gemini.sh
```

**환경 변수 (override)**

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `GEMINI_CONFIG` | `configs/gemini.yaml` | generation config 경로 |
| `INPUT_FILE` | `data/combined_data_merged.jsonl` | 입력 JSONL |
| `OUTPUT_FILE` | `data/filtered_comments_gemini.jsonl` | 출력 JSONL |
| `GCP_PROJECT` | `hivideosum` | Vertex AI 프로젝트 |
| `GCP_LOCATION` | `global` | Vertex AI 리전 |
| `TEMPERATURE` / `TOP_P` / `MAX_OUTPUT_TOKENS` | YAML 값 | 샘플링 파라미터 |
| `THINKING_LEVEL` | YAML 값 | `none` \| `low` \| `medium` \| `high` |

**확인 포인트**

- `data/filtered_comments_gemini.jsonl` 가 생성되고 입력과 동일한 영상 수만큼 출력되었는지
- 각 레코드의 `evaluation_result.general_comments[*]` 에 `scores`, `total_score`, `is_pass` 키가 있는지
- 통과율이 비정상적으로 0% / 100%가 아닌지 (보통 일반 60% / 타임스탬프 60% 내외)

```bash
python -c "import json; \
r=[json.loads(l) for l in open('data/filtered_comments_gemini.jsonl')]; \
g=[c for x in r for c in x['evaluation_result']['general_comments']]; \
print('general n:', len(g), 'pass%:', round(100*sum(c['is_pass'] for c in g)/max(len(g),1),1))"
```

> K-EXAONE 기반 필터를 동시에 비교하고 싶다면 `bash scripts/run_filter_kexaone.sh` 도 같은 방식으로 실행 가능합니다 (`K_EXAONE_API_KEY` 필요).

---

### 3) 요약 생성 테스트 (Gemini 3 Flash Preview · Vertex AI)

**위치**: `data/summarize/`

```bash
cd data/summarize
conda activate gemini_api          # 필터링과 동일한 env 재사용 가능
pip install -r requirements.txt

# 3-1. 필터링 결과를 입력으로 복사 (소량 권장)
#  요약 스크립트는 입력 레코드에 transcript + regular_comments + timestamp_comments + evaluation_result
#  네 필드가 모두 있어야 합니다. 필터링 출력에는 evaluation_result만 있으므로 크롤링 원본과 video_id 기준으로 합쳐서 넣어야 합니다.
mkdir -p data
python -c "
import json
raw = {json.loads(l)['video_id']: json.loads(l) for l in open('../crawl_raw_data/comment_results_test/combined_data.jsonl')}
ev  = {json.loads(l)['video_id']: json.loads(l) for l in open('../filter_kexaone/data/filtered_comments_gemini.jsonl')}
with open('data/filtered_combined_data.jsonl','w') as f:
    for vid, r in raw.items():
        if vid in ev: f.write(json.dumps({**r, 'evaluation_result': ev[vid]['evaluation_result']}, ensure_ascii=False)+'\n')
"

# 3-2. 실행 (스크립트 기본 INPUT_FILE 은 프로젝트별 파일명이므로 env 로 명시)
INPUT_FILE=data/filtered_combined_data.jsonl \
OUTPUT_FILE=data/summarized_data_gemini.jsonl \
  bash scripts/run_summarize_gemini.sh
```

**확인 포인트**

- `data/summarized_data_gemini.jsonl` 가 생성되고 각 레코드에 `summary` 필드가 존재
- `summary` 가 3문단 산문(불릿/번호 없음)으로 작성되고 500~1000자 내외인지
- 3번째 문단에만 시간 정보(예: `3:24`)가 포함되었는지

```bash
python -c "import json; \
r=[json.loads(l) for l in open('data/summarized_data_gemini.jsonl')]; \
print('summaries:', len(r), 'avg_len:', sum(len(x['summary']) for x in r)//max(len(r),1)); \
print('--- sample ---'); print(r[0]['summary'][:300] if r else '(empty)')"
```

---

### 4) 학습 데이터셋 생성 테스트 (HuggingFace 포맷)

**위치**: `data/summarize/`  
요약 결과(`summarized_data_gemini.jsonl`)와 필터링 결과(`filtered_comments_gemini.jsonl`)를 합쳐 LoRA 파인튜닝용 messages 포맷(`system / user / assistant`) JSONL을 만들고, 선택적으로 HuggingFace Hub에 업로드합니다.

```bash
cd data/summarize
conda activate gemini_api        # 동일 env 재사용 가능
pip install -r requirements.txt  # datasets 패키지가 push_to_hub 시 필요할 수 있음

# 4-1. messages 포맷 JSONL 생성 (로컬 출력)
#  --input 은 ③단계에서 만든 "transcript + 댓글 + evaluation_result" 가 모두 들어있는 merged 파일이어야 합니다.
python build_finetune_dataset.py \
  --input     data/filtered_combined_data.jsonl \
  --summaries data/summarized_data_gemini.jsonl \
  --output    data/finetune_dataset.jsonl

# 4-2. (선택) HuggingFace Hub 업로드 dry-run 격 확인
#      먼저 huggingface-cli login 으로 토큰 등록
python -c "
import json
r=[json.loads(l) for l in open('data/finetune_dataset.jsonl')]
print('records:', len(r))
print('roles per sample:', [m['role'] for m in r[0]['messages']])
print('--- user preview ---'); print(r[0]['messages'][1]['content'][:300])
print('--- assistant preview ---'); print(r[0]['messages'][2]['content'][:300])
"

# 4-3. (실제 업로드) — 본인 repo 로 바꾸어 사용
# python push_to_hub.py \
#   --input data/finetune_dataset.jsonl \
#   --repo  <username>/<dataset-name> \
#   --private
```

**확인 포인트**

- `data/finetune_dataset.jsonl` 생성, 라인 수는 (요약 ∩ 필터 결과의 video_id 교집합) 수와 일치
- 각 라인의 `messages` 가 정확히 `system → user → assistant` 3턴
- `user.content` 에 자막·일반 댓글·타임스탬프 댓글 세 입력이 포함
- `assistant.content` 가 3문단 산문 요약

---

### 흐름 정리 (한 줄 요약)

```
① 수집 (crawl_raw_data)   → combined_data.jsonl
② 필터 (filter_kexaone)   → filtered_comments_gemini.jsonl
③ 요약 (summarize)        → summarized_data_gemini.jsonl
④ 데이터셋 (summarize)    → finetune_dataset.jsonl  ─► (push_to_hub.py) HF Hub
```

네 단계 모두 5~10개 영상 정도의 소량 입력만으로 정상 동작 여부를 30분 안에 확인할 수 있도록 설계되어 있습니다.

---

## Authors

Yeon-hu Jung · Kyeong-jun Oh · Yong-ha Lee · Kipyo Kim

Advisor: Mina Jung — Sungkyunkwan University, AI Convergence

---

## Citation

```bibtex
@misc{hivideosum2026,
  title       = {Hi-VideoSum: A User-Centric YouTube Video Summarization and Highlight Service for Korean},
  author      = {Jung, Yeon-hu and Oh, Kyeong-jun and Lee, Yong-ha and Kim, Kipyo},
  institution = {Sungkyunkwan University, AI Convergence},
  advisor     = {Jung, Mina},
  course      = {Data Science Capstone Project},
  year        = {2026},
  note        = {Mid-term report, v0.2},
  url         = {https://huggingface.co/datasets/kim586w/hivideosum_training_dataset}
}
```
