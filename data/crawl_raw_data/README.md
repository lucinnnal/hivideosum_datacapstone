# YouTube Data Capstone Project

YouTube 채널 리스트를 입력받아 각 채널의 최신 영상에서 **transcript(자막)**, **timestamp 댓글**, **일반 댓글**을 자동 수집하고, Gemini 2.5 또는 로컬 sLLM을 활용하여 유의미한 댓글 필터링 및 sLLM 학습용 요약 데이터를 생성하는 파이프라인입니다.

## 파이프라인 개요

```text
inputs/channels.jsonl ─► scripts/crowl_comments.sh ─► comment_results/combined_data.jsonl
                        (채널별 최신 영상 수집)      (transcript + 댓글 원시 데이터)

[댓글 필터링 — 택 1]
combined_data.jsonl ─► scripts/run_filter_gemini.sh  ─► filtered_comments.jsonl          (Gemini 2.5 API)
                    ─► scripts/run_filter_exaone.sh  ─► filtered_comments_exaone.jsonl   (EXAONE 4.0 32B, vLLM)
                    ─► filter_comments_with_kormo.py ─► filtered_comments_kormo.jsonl    (KORMo 10B SFT, vLLM)
                    ─► filter_comments_with_midm.py  ─► filtered_comments_midm.jsonl     (Midm 2.0 Base, vLLM)
                    ─► filter_comments_with_qwen.py  ─► filtered_comments_qwen.jsonl     (Qwen3.5-35B, vLLM)

[영상 요약]
combined_data.jsonl ─► scripts/run_gemini.sh ─► gemini_results_for_training.jsonl        (Gemini 2.5 요약)
```

## 요구사항

- Python 3.10 (for vllm version)
- Conda 환경 (`datacapstone`)

```bash
conda create -n datacapstone python=3.10
conda activate datacapstone
pip install -r requirements.txt
```

### 패키지 목록
| 패키지 | 용도 |
|--------|------|
| `yt-dlp` | 채널 영상 목록 추출, 영상 길이 조회 |
| `youtube-transcript-api` | 자막(transcript) 수집 |
| `youtube-comment-downloader` | 댓글 수집 |
| `google-genai` | Gemini API 호출 |
| `openai` | vLLM 서버와의 OpenAI 호환 API 통신 |
| `python-dotenv` | 환경 변수 관리 (`.env`) |
| `vllm` | 모델 서빙 패키지 (0.10.0 버전 통일) |
| `matplotlib`, `numpy` | 필터링 결과 시각화 |

## 설정 (Environment Variables)

프로젝트 루트 디렉토리에 `.env` 파일을 생성합니다. `.env.example` 파일을 참고하세요.

```bash
cp .env.example .env
# .env 파일을 열어 각 값을 입력하세요.
```

| 변수 | 필수 | 용도 |
|------|------|------|
| `GEMINI_API_KEY` | 필터링·요약 사용 시 필수 | Gemini API 키 |
| `WEBSHARE_PROXY_USERNAME` | 선택 | Webshare rotating residential 프록시 사용자명 |
| `WEBSHARE_PROXY_PASSWORD` | 선택 | Webshare rotating residential 프록시 비밀번호 |

> `WEBSHARE_*` 변수가 `.env`에 설정되어 있으면 자막 수집 시 자동으로 프록시를 경유합니다.

## 사용법

### 1. 채널 리스트 준비

`inputs/channels.jsonl` 파일에 수집할 채널을 한 줄에 하나씩 JSON 형식으로 작성합니다.

```jsonl
{"channel_url": "https://www.youtube.com/@channel_handle", "channel_name": "채널이름1"}
{"channel_url": "https://www.youtube.com/channel/UC...", "channel_name": "채널이름2"}
```

### 2. 데이터 수집 실행

```bash
./scripts/crowl_comments.sh inputs/channels.jsonl [output_directory] [fetch_limit]
```

- `inputs/channels.jsonl` — 채널 리스트 파일 (기본 위치)
- `output_directory` — 출력 디렉토리 (기본값: `comment_results`)
- `fetch_limit` — 채널당 fetch할 최대 영상 수 (기본값: `300`)

#### 수집 조건
| 조건 | 내용 |
|------|------|
| 영상 길이 | 5분 ~ 30분만 수집 |
| 영상 정렬 | 댓글수 내림차순 (불가 시 조회수 내림차순) |
| 채널당 목표 | 최대 300개 영상 수집 후 중단 (미달 시 있는 대로 수집) |
| 대댓글 | 수집 제외 |
| 영상 스킵 조건 | 일반 댓글 또는 timestamp 댓글이 각각 5개 미만인 영상 제외 |
| 자막 비활성 영상 | `Subtitles are disabled` 오류 발생 시 재시도 없이 즉시 스킵 (`skipped` 로그 기록) |

#### 수집 결과 (`comment_results/`)
| 파일 | 내용 |
|------|------|
| `urls.jsonl` | 수집 대상 영상 URL 목록 |
| `combined_data.jsonl` | 영상별 transcript + 댓글 원시 데이터 |
| `collection_log.json` | 수집 실행 로그 |
| `video_log.json` | 영상별 수집 상태 로그 (`collected` / `skipped` / `error`) |

### 3. Gemini 댓글 필터링

수집된 댓글에서 정보성, 의견성, 연관성 기준(각 1~3점)을 평가하여 총점 6점 이상인 유의미한 댓글만 선별합니다. `.env` 파일에 `GEMINI_API_KEY`가 설정되어 있어야 합니다.

```bash
./scripts/run_filter_gemini.sh --input comment_results/combined_data.jsonl --output comment_results/filtered_comments.jsonl
```

출력: `comment_results/filtered_comments.jsonl` — 영상별 평가된 댓글 (총점 및 통과 여부 포함)

### 4. EXAONE 댓글 필터링 (vLLM)

로컬 GPU를 활용하여 EXAONE 4.0 32B 모델을 vLLM으로 서빙하고 댓글을 필터링합니다. 스크립트가 서빙과 추론을 순차 진행하고 완료 시 서버를 종료합니다.

```bash
./scripts/run_filter_exaone.sh comment_results/combined_data.jsonl comment_results/filtered_comments_exaone.jsonl [tensor_parallel_size]
```

- 세 번째 인자: 텐서 병렬화(Tensor Parallel) 사이즈 (기본값: `1`)

### 5. KORMo 댓글 필터링 (vLLM)

KORMo 10B SFT 모델로 댓글을 필터링합니다. vLLM 서버가 별도로 실행 중이어야 합니다.

```bash
python filter_comments_with_kormo.py \
  --input comment_results/combined_data.jsonl \
  --output comment_results/filtered_comments_kormo.jsonl \
  --host http://localhost:8000/v1 \
  --model KORMo-Team/KORMo-10B-sft
```

### 6. Midm 댓글 필터링 (vLLM)

Midm 2.0 Base Instruct 모델로 댓글을 필터링합니다.

```bash
python filter_comments_with_midm.py \
  --input comment_results/combined_data.jsonl \
  --output comment_results/filtered_comments_midm.jsonl \
  --host http://localhost:8000/v1 \
  --model K-intelligence/Midm-2.0-Base-Instruct
```

### 7. Qwen 댓글 필터링 (vLLM)

Qwen3.5-35B-A3B-Base 모델로 댓글을 필터링합니다.

```bash
python filter_comments_with_qwen.py \
  --input comment_results/combined_data.jsonl \
  --output comment_results/filtered_comments_qwen.jsonl \
  --host http://localhost:8000/v1 \
  --model Qwen/Qwen3.5-35B-A3B-Base
```

### 8. Gemini 요약 생성

`.env` 파일에 `GEMINI_API_KEY`가 설정되어 있어야 합니다.

```bash
./scripts/run_gemini.sh comment_results/combined_data.jsonl [output.jsonl]
```

출력: `comment_results/gemini_results_for_training.jsonl` — 영상별 요약 (sLLM 학습 데이터)

### 9. 필터링 결과 시각화

여러 모델의 필터링 결과를 비교 시각화합니다. `visualize_filtering_results.py` 내 `DATA_DIR` 및 `FILES` 변수를 수정하여 사용합니다.

```bash
python visualize_filtering_results.py
```

## 프로젝트 구조

```
datacaptstone/
├── channel_collector.py              # 메인 수집기: 채널 → 영상 URL 추출 → 데이터 수집
├── youtube_collector.py              # 단일 영상 수집 모듈 (transcript + 댓글, 프록시 지원)
├── batch_collector.py                # URL 리스트 기반 배치 수집 (레거시)
├── parse_comments.py                 # combined_data.jsonl → 댓글/자막 분리 저장 (유틸리티)
├── summarize_with_gemini.py          # Gemini 2.5 요약 생성 (sLLM 학습용)
├── filter_comments_with_gemini.py    # Gemini 2.5 댓글 필터링
├── filter_comments_with_exaone.py    # EXAONE 4.0 32B 댓글 필터링 (vLLM)
├── filter_comments_with_kormo.py     # KORMo 10B SFT 댓글 필터링 (vLLM)
├── filter_comments_with_midm.py      # Midm 2.0 Base Instruct 댓글 필터링 (vLLM)
├── filter_comments_with_qwen.py      # Qwen3.5-35B-A3B-Base 댓글 필터링 (vLLM)
├── visualize_filtering_results.py    # 모델별 필터링 결과 비교 시각화
├── analyze_comments.py               # 수집된 댓글 분석 유틸리티
├── check_timestamps.py               # 타임스탬프 유효성 검사 유틸리티
├── comment_stats.py                  # 댓글 통계 생성 유틸리티
├── requirements.txt                  # Python 패키지 목록
├── .env                              # 환경 변수 (API 키 등 - Git 제외)
├── .env.example                      # .env 템플릿
├── generation_configs/
│   └── gemini.json                   # Gemini 모델 설정 (model, temperature 등)
├── inputs/
│   └── channels.jsonl                # 채널 리스트 입력 파일
├── comment_results/                  # 데이터 수집 결과 저장 폴더
└── scripts/
    ├── crowl_comments.sh             # 데이터 수집 통합 실행 스크립트
    ├── run_filter_gemini.sh          # Gemini 댓글 필터링 실행 스크립트
    ├── run_filter_exaone.sh          # EXAONE 댓글 필터링 서빙 및 추론 실행 스크립트
    └── run_gemini.sh                 # Gemini 요약 실행 스크립트
```

## 데이터 형식

### combined_data.jsonl (한 줄 = 한 영상)
```json
{
  "video_url": "https://www.youtube.com/watch?v=...",
  "video_id": "...",
  "success": true,
  "video_length": 600,
  "channel_name": "채널이름",
  "channel_url": "https://www.youtube.com/@channel_handle",
  "title": "영상제목",
  "transcript": [{"text": "...", "start": 0.0, "duration": 3.5}, ...],
  "timestamp_comments": [{"text": "1:23 이 부분 좋아요", "timestamps_found": [...], ...}, ...],
  "regular_comments": [{"text": "좋은 영상이네요", ...}, ...]
}
```

### video_log.json (영상별 수집 상태)
```json
{
  "VIDEO_ID": {
    "video_url": "...",
    "title": "영상제목",
    "channel_name": "채널이름",
    "channel_url": "...",
    "status": "collected",
    "timestamp": "2025-01-01T00:00:00",
    "detail": "regular=50, timestamp=12, transcript=320"
  }
}
```
`status` 값: `collected` / `skipped` / `error`
