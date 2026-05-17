/**
 * Hi-VideoSum service worker.
 *
 * Content script와 메시지로 통신해서 백엔드 호출과 폴링을 담당한다.
 * fetch를 background 컨텍스트에서 실행하므로 CORS / mixed-content 이슈가 없다.
 *
 * 메시지 프로토콜
 *   { type: 'summarize', url }
 *     → 백그라운드가 POST /jobs 후, port를 통해 진행상황·결과·에러를 push
 *
 * port.name === 'summarize' 인 long-lived connection을 가정한다.
 *   content가 disconnect하면 폴링도 중단.
 */
const DEFAULT_BACKEND = 'http://localhost:8000';
const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

async function getBackendUrl() {
  const { backendUrl } = await chrome.storage.sync.get(['backendUrl']);
  return (backendUrl || DEFAULT_BACKEND).replace(/\/+$/, '');
}

chrome.runtime.onInstalled.addListener(async () => {
  const { backendUrl } = await chrome.storage.sync.get(['backendUrl']);
  if (!backendUrl) {
    await chrome.storage.sync.set({ backendUrl: DEFAULT_BACKEND });
  }
});

chrome.action.onClicked.addListener(() => {
  chrome.runtime.openOptionsPage();
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === 'open-options') chrome.runtime.openOptionsPage();
});

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== 'summarize') return;

  let cancelled = false;
  port.onDisconnect.addListener(() => {
    cancelled = true;
  });

  port.onMessage.addListener(async (msg) => {
    if (msg?.type !== 'summarize' || !msg.url) return;

    try {
      const backend = await getBackendUrl();

      const createRes = await fetch(`${backend}/jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: msg.url }),
      });

      if (!createRes.ok) {
        const body = await safeJson(createRes);
        throw new Error(`서버 ${createRes.status}: ${body?.detail || createRes.statusText}`);
      }

      const created = await createRes.json();

      if (cancelled) return;

      if (created.cached && created.result) {
        safePost(port, { type: 'progress', status: 'done', progress: 1 });
        safePost(port, { type: 'result', cached: true, payload: created.result });
        return;
      }

      await pollJob({
        backend,
        jobId: created.job_id,
        port,
        isCancelled: () => cancelled,
      });
    } catch (err) {
      safePost(port, { type: 'error', message: err?.message || String(err) });
    }
  });
});

async function pollJob({ backend, jobId, port, isCancelled }) {
  const started = Date.now();

  while (!isCancelled()) {
    if (Date.now() - started > POLL_TIMEOUT_MS) {
      safePost(port, { type: 'error', message: '⏰ 5분이 지나도 결과가 없어 폴링을 중단했어요.' });
      return;
    }

    let meta;
    try {
      const res = await fetch(`${backend}/jobs/${jobId}`);
      if (!res.ok) {
        const body = await safeJson(res);
        safePost(port, {
          type: 'error',
          message: `상태 조회 실패 (${res.status}): ${body?.detail || res.statusText}`,
        });
        return;
      }
      meta = await res.json();
    } catch (err) {
      safePost(port, { type: 'error', message: `네트워크 오류: ${err.message}` });
      return;
    }

    safePost(port, {
      type: 'progress',
      status: meta.status,
      progress: meta.progress,
    });

    if (meta.status === 'done') {
      try {
        const r = await fetch(`${backend}/jobs/${jobId}/result`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const payload = await r.json();
        safePost(port, { type: 'result', cached: false, payload });
      } catch (err) {
        safePost(port, { type: 'error', message: `결과 수신 실패: ${err.message}` });
      }
      return;
    }

    if (meta.status === 'failed') {
      const m = meta.error ? `${meta.error.code || ''}: ${meta.error.message || ''}` : '알 수 없는 오류';
      safePost(port, { type: 'error', message: m });
      return;
    }

    await sleep(POLL_INTERVAL_MS);
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function safeJson(res) {
  try { return await res.json(); } catch { return null; }
}

function safePost(port, msg) {
  try { port.postMessage(msg); } catch { /* port closed */ }
}
