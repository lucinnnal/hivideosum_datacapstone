# crawl_raw_data

YouTube 채널 리스트를 입력받아 각 채널의 영상에서 **transcript(자막)**, **timestamp 댓글**, **일반 댓글**을 자동 수집하는 파이프라인입니다. 후속 단계(필터링·요약)는 별도 모듈(`data/filter_kexaone/`, `data/summarize/`)에서 처리합니다.

## 파이프라인 개요

```text
inputs/channels.jsonl ─► scripts/crowl_comments.sh ─► comment_results/combined_data.jsonl
                        (채널별 영상 수집)            (transcript + 댓글 원시 데이터)
```

## 요구사항

- Python 3.10
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
| `python-dotenv` | 환경 변수 관리 (`.env`) |

## 설정 (Environment Variables)

자막(transcript) API 는 IP 차단·429 가 빈번하므로 **Webshare 로테이션 프록시 경유를 권장**합니다.

### Webshare 자격 증명 발급

1. [Webshare](https://www.webshare.io) 가입 (무료 플랜 1GB/월 — 스모크 테스트엔 충분)
2. 대시보드 **Proxy → User & Password** 메뉴에서 username/password 확인
3. 아래 단계로 `.env` 작성

```bash
cp .env.example .env
# .env 편집
#   WEBSHARE_PROXY_USERNAME=your_webshare_username
#   WEBSHARE_PROXY_PASSWORD=your_webshare_password
```

| 변수 | 필수 | 용도 |
|------|------|------|
| `WEBSHARE_PROXY_USERNAME` | **권장** | Webshare rotating residential 프록시 사용자명 |
| `WEBSHARE_PROXY_PASSWORD` | **권장** | Webshare rotating residential 프록시 비밀번호 |
| `TRANSCRIPT_HTTP_PROXY` / `TRANSCRIPT_HTTPS_PROXY` | 선택 | Webshare 대신 일반 HTTP/HTTPS 프록시를 쓸 때 |

### 동작 우선순위

`youtube_collector.py:_build_transcript_api()` 가 다음 순서로 프록시를 선택합니다:

1. `WEBSHARE_PROXY_USERNAME` + `WEBSHARE_PROXY_PASSWORD` → **Webshare 로테이션 프록시** (권장)
2. 위가 없고 `TRANSCRIPT_HTTP_PROXY`/`TRANSCRIPT_HTTPS_PROXY` 있음 → **일반 HTTP/HTTPS 프록시**
3. 아무것도 없음 → **직접 호출** (대량 수집 시 차단 위험)

활성 여부는 실행 로그에서 확인 가능합니다:

```text
  [Proxy] Using Webshare rotating residential proxy
```

> 프록시는 **자막(transcript) API 호출에만** 적용됩니다. yt-dlp(채널 영상 목록·메타데이터)와 youtube-comment-downloader(댓글)는 프록시 미적용입니다.

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
- `fetch_limit` — 채널당 후보로 가져올 최대 영상 수 (기본값: `300`)

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

## 프로젝트 구조

```
crawl_raw_data/
├── channel_collector.py              # 메인 수집기: 채널 → 영상 URL 추출 → 데이터 수집
├── youtube_collector.py              # 단일 영상 수집 모듈 (transcript + 댓글, 프록시 지원)
├── batch_collector.py                # URL 리스트 기반 배치 수집 (레거시)
├── parse_comments.py                 # combined_data.jsonl → 댓글/자막 분리 저장 (유틸리티)
├── analyze_comments.py               # 수집된 댓글 분석 유틸리티
├── check_timestamps.py               # 타임스탬프 유효성 검사 유틸리티
├── comment_stats.py                  # 댓글 통계 생성 유틸리티
├── requirements.txt                  # Python 패키지 목록
├── .env                              # 환경 변수 (프록시 등 - Git 제외)
├── .env.example                      # .env 템플릿
├── inputs/
│   └── channels.jsonl                # 채널 리스트 입력 파일
├── comment_results/                  # 데이터 수집 결과 저장 폴더
└── scripts/
    └── crowl_comments.sh             # 데이터 수집 통합 실행 스크립트
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

## 다음 단계

수집이 끝나면 결과 파일을 후속 모듈로 넘겨 필터링·요약을 진행합니다.

```bash
# 필터링 (gemini-3-flash-preview, Vertex AI)
cp comment_results/combined_data.jsonl ../filter_kexaone/data/combined_data_merged.jsonl
cd ../filter_kexaone && bash scripts/run_filter_gemini.sh

# 요약 (gemini-3-flash-preview, Vertex AI)
cd ../summarize && bash scripts/run_summarize_gemini.sh
```
