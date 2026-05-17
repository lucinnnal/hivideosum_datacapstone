# Hi-VideoSum Browser Extension

YouTube `/watch` 페이지에 사이드바 카드를 인젝션해서, 보고 있는 영상을 3문단으로 요약해주는 Chrome 확장 프로그램. [Hi-VideoSum 백엔드](../backend)와 페어로 동작한다.

웹 UI 버전과 다른 점:
- 비디오 임베드 없음 (이미 YouTube에서 보고 있으니까)
- URL 입력 불필요 — 현재 페이지에서 영상 ID를 자동 추출
- SPA 네비게이션 추적 — YouTube에서 영상을 바꾸면 패널도 자동으로 리셋

## 구성

```
service/extension/
├── manifest.json       MV3 매니페스트
├── src/
│   ├── background.js   service worker — POST /jobs, 폴링, 결과 수신
│   ├── content.js      YouTube 페이지에 사이드바 패널 인젝션
│   ├── content.css     패널 스타일 (다크 + 앰버 톤)
│   ├── options.html    백엔드 URL 설정 페이지
│   └── options.js
└── icons/              16/48/128 px PNG
```

## 동작 방식

```
YouTube watch page
        │
        │  (content script)
        ▼
   #hvs-panel ─────────── chrome.runtime.connect ───────────┐
   (사이드바 카드 UI)                                       │
                                                            ▼
                                                    background.js
                                                    (service worker)
                                                            │
                                                            │ fetch
                                                            ▼
                                                  hivideosum FastAPI
                                                    POST /jobs
                                                    GET  /jobs/:id
                                                    GET  /jobs/:id/result
```

- **Content script**는 YouTube DOM(`#secondary`)에 패널을 끼워넣고, 사용자 클릭만 처리한다.
- **Background service worker**가 모든 fetch를 담당. 백그라운드 컨텍스트에서 호출하므로 CORS / mixed-content 이슈가 없다. (`host_permissions`에 등록한 백엔드 URL만 호출 가능.)
- 두 스크립트는 long-lived `port`로 통신 — 폴링이 진행되면서 `progress` → `result` 또는 `error` 이벤트가 push된다.

## 설치 (개발 모드)

1. **백엔드 먼저 띄우기**

   ```bash
   cd ../backend
   sudo docker compose up --build
   # 또는 로컬 실행 (README 참고)
   ```

   기본 포트 `http://localhost:8000`.

2. **확장 프로그램 로드**
   - Chrome / Edge / Brave에서 `chrome://extensions` 열기
   - "개발자 모드" 토글 ON
   - "압축 해제된 확장 프로그램 로드" → `service/extension` 폴더 선택

3. **백엔드 URL 확인 (필요시)**
   - 툴바의 Hi-VideoSum 아이콘 클릭 → 옵션 페이지가 열림
   - 기본값은 `http://localhost:8000`. 다른 포트나 원격 서버를 쓰면 여기서 변경.
   - 다른 호스트를 쓰려면 `manifest.json`의 `host_permissions`에 해당 origin을 추가해야 한다.

4. **YouTube 영상 페이지 방문**
   - `https://www.youtube.com/watch?v=…` 진입 시 우측 추천 영상 위에 "Hi-VideoSum" 카드가 나타남.
   - "요약 시작" 버튼 클릭 → 1~2분 후 3문단 요약 표시.

## 핫리로드

`src/`나 `manifest.json`을 수정한 뒤 `chrome://extensions`에서 새로고침(↻) 버튼을 누르면 반영된다. YouTube 탭도 새로고침해야 content script가 다시 인젝션된다.

## 백엔드 호환성

`hivideosum` API와 동일한 스펙을 사용한다:

| 메서드 | 경로 | 응답 |
|---|---|---|
| POST | `/jobs` | `{ job_id, cached, result? }` |
| GET | `/jobs/{id}` | `{ status, progress, error }` |
| GET | `/jobs/{id}/result` | `{ summary: { content, reaction, highlights }, filter_stats: {...} }` |

`status`: `queued | collecting | filtering | summarizing | done | failed`

백엔드가 캐시 hit을 반환하면 폴링 없이 즉시 결과가 렌더된다.

## 주의사항

- 백엔드는 `allow_origins=["*"]` 이지만, 확장 프로그램은 어차피 service worker에서 fetch하므로 CORS는 신경 쓰지 않아도 된다.
- HTTPS YouTube에서 HTTP localhost로 fetch하는 mixed-content 케이스도 service worker 경유라 문제 없음.
- YouTube DOM 구조가 바뀌면 `#secondary` 마운트가 실패할 수 있다. 그 경우 `content.js`의 `mountPanel()` 셀렉터를 갱신.
