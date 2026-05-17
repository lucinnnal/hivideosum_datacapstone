/**
 * Hi-VideoSum content script.
 *
 * YouTube /watch 페이지에 사이드바 카드를 인젝션한다. SPA 네비게이션(yt-navigate-finish)을
 * 추적해서 영상이 바뀌면 UI를 리셋한다.
 *
 * background.js와는 chrome.runtime.connect로 long-lived port를 열어 통신한다.
 */
(() => {
  const STAGE_ORDER = ['collecting', 'filtering', 'summarizing', 'done'];
  const STAGE_CAPTION = {
    queued: '🕐 잠깐만요, 곧 시작할게요!',
    collecting: '📥 자막이랑 댓글 긁어오는 중이에요',
    filtering: '🔍 쓸모 있는 댓글만 골라내고 있어요',
    summarizing: '✍️ 요약문을 열심히 쓰고 있어요',
    done: '🎉 요약이 완성됐어요!',
  };
  const STAGE_LABEL = {
    collecting: '수집',
    filtering: '필터링',
    summarizing: '요약',
    done: '완료',
  };

  let currentVideoId = null;
  let panelEl = null;
  let activePort = null;

  const esc = (s) =>
    (s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function getVideoId() {
    try {
      const u = new URL(location.href);
      if (u.hostname.includes('youtube.com') && u.pathname === '/watch') {
        return u.searchParams.get('v');
      }
    } catch { /* ignore */ }
    return null;
  }

  function buildPanel() {
    const el = document.createElement('div');
    el.id = 'hvs-panel';
    el.innerHTML = `
      <div class="hvs-header">
        <span class="hvs-logo">Hi-Video<span class="hvs-accent">Sum</span></span>
        <button class="hvs-settings" type="button" title="옵션 열기" aria-label="옵션">⚙</button>
      </div>
      <p class="hvs-tagline">🎬 이 영상을 요약해드릴게요</p>

      <button type="button" class="hvs-submit">요약 시작</button>

      <div class="hvs-error" hidden></div>

      <div class="hvs-pipeline" hidden>
        <div class="hvs-stages">
          ${STAGE_ORDER.map((s) => `
            <div class="hvs-stage" data-stage="${s}">
              <div class="hvs-dot"></div>
              <span class="hvs-stage-label">${STAGE_LABEL[s]}</span>
            </div>
          `).join('')}
        </div>
        <p class="hvs-caption"></p>
      </div>

      <div class="hvs-results" hidden>
        <div class="hvs-card" data-card="0">
          <div class="hvs-meta"><span class="hvs-num">01</span><span class="hvs-label">영상 내용</span></div>
          <p class="hvs-body" data-body="content"></p>
        </div>
        <div class="hvs-card" data-card="1">
          <div class="hvs-meta"><span class="hvs-num">02</span><span class="hvs-label">시청자 반응</span></div>
          <p class="hvs-body" data-body="reaction"></p>
        </div>
        <div class="hvs-card" data-card="2">
          <div class="hvs-meta"><span class="hvs-num">03</span><span class="hvs-label">집중 장면</span></div>
          <p class="hvs-body" data-body="highlights"></p>
        </div>
        <div class="hvs-stats">
          <div><span class="hvs-stat-label">일반 댓글 필터</span><span class="hvs-stat-value" data-stat="general"></span></div>
          <div><span class="hvs-stat-label">타임스탬프 필터</span><span class="hvs-stat-value" data-stat="timestamp"></span></div>
        </div>
      </div>
    `;

    el.querySelector('.hvs-settings').addEventListener('click', () => {
      chrome.runtime.sendMessage({ type: 'open-options' });
    });
    el.querySelector('.hvs-submit').addEventListener('click', () => startSummarize(el));

    return el;
  }

  function mountPanel() {
    if (panelEl && panelEl.isConnected) return panelEl;

    const secondary = document.querySelector('#secondary, ytd-watch-flexy #secondary');
    if (!secondary) return null;

    panelEl = buildPanel();
    secondary.insertBefore(panelEl, secondary.firstChild);
    return panelEl;
  }

  function resetPanel(el) {
    el.querySelector('.hvs-error').hidden = true;
    el.querySelector('.hvs-error').textContent = '';
    el.querySelector('.hvs-pipeline').hidden = true;
    el.querySelector('.hvs-results').hidden = true;
    el.querySelectorAll('.hvs-stage').forEach((s) => s.classList.remove('hvs-active', 'hvs-done'));
    el.querySelectorAll('.hvs-card, .hvs-stats').forEach((c) => c.classList.remove('hvs-revealed'));
    el.querySelector('.hvs-submit').disabled = false;
    el.querySelector('.hvs-submit').textContent = '요약 시작';
  }

  function updatePipeline(el, status, progress) {
    const pipe = el.querySelector('.hvs-pipeline');
    pipe.hidden = false;

    const idx = STAGE_ORDER.indexOf(status);
    el.querySelectorAll('.hvs-stage').forEach((s) => {
      const i = STAGE_ORDER.indexOf(s.dataset.stage);
      s.classList.toggle('hvs-done', i < idx);
      s.classList.toggle('hvs-active', i === idx && status !== 'done');
      if (status === 'done' && s.dataset.stage === 'done') s.classList.add('hvs-done');
    });

    const pct = Math.round((progress || 0) * 100);
    const base = STAGE_CAPTION[status] || status;
    el.querySelector('.hvs-caption').textContent =
      pct > 0 && status !== 'done' ? `${base} (${pct}%)` : base;
  }

  function showError(el, msg) {
    const box = el.querySelector('.hvs-error');
    box.textContent = `😥 ${msg}`;
    box.hidden = false;
    el.querySelector('.hvs-pipeline').hidden = true;
    el.querySelector('.hvs-submit').disabled = false;
    el.querySelector('.hvs-submit').textContent = '다시 시도';
  }

  function renderResult(el, payload) {
    updatePipeline(el, 'done', 1);

    const s = payload.summary || {};
    const stats = payload.filter_stats || {};

    el.querySelector('[data-body="content"]').textContent = s.content || '';
    el.querySelector('[data-body="reaction"]').textContent = s.reaction || '';
    el.querySelector('[data-body="highlights"]').textContent = s.highlights || '';

    const gp = stats.passed_general ?? '?';
    const gt = stats.total_general ?? '?';
    const tp = stats.passed_timestamp ?? '?';
    const tt = stats.total_timestamp ?? '?';
    el.querySelector('[data-stat="general"]').innerHTML =
      `<span class="hvs-pass">${esc(String(gp))}</span> / ${esc(String(gt))}`;
    el.querySelector('[data-stat="timestamp"]').innerHTML =
      `<span class="hvs-pass">${esc(String(tp))}</span> / ${esc(String(tt))}`;

    el.querySelector('.hvs-results').hidden = false;
    el.querySelector('.hvs-submit').disabled = false;
    el.querySelector('.hvs-submit').textContent = '다시 요약';

    const cards = el.querySelectorAll('.hvs-card');
    cards.forEach((card, i) => {
      setTimeout(() => card.classList.add('hvs-revealed'), 80 + i * 180);
    });
    setTimeout(() => el.querySelector('.hvs-stats').classList.add('hvs-revealed'), 80 + cards.length * 180);
  }

  function startSummarize(el) {
    if (activePort) {
      try { activePort.disconnect(); } catch { /* ignore */ }
      activePort = null;
    }

    resetPanel(el);
    el.querySelector('.hvs-submit').disabled = true;
    el.querySelector('.hvs-submit').textContent = '진행 중...';
    updatePipeline(el, 'queued', 0);
    el.querySelector('.hvs-caption').textContent = '🚀 요청을 보내고 있어요...';

    const port = chrome.runtime.connect({ name: 'summarize' });
    activePort = port;

    port.onMessage.addListener((msg) => {
      if (!panelEl || !panelEl.isConnected) return;
      if (msg.type === 'progress') {
        updatePipeline(panelEl, msg.status, msg.progress);
      } else if (msg.type === 'result') {
        renderResult(panelEl, msg.payload);
        activePort = null;
        try { port.disconnect(); } catch { /* ignore */ }
      } else if (msg.type === 'error') {
        showError(panelEl, msg.message);
        activePort = null;
        try { port.disconnect(); } catch { /* ignore */ }
      }
    });

    port.onDisconnect.addListener(() => {
      if (activePort === port) activePort = null;
    });

    port.postMessage({ type: 'summarize', url: location.href });
  }

  function onUrlMaybeChanged() {
    const newId = getVideoId();
    if (!newId) return;

    if (newId !== currentVideoId) {
      currentVideoId = newId;
      if (activePort) {
        try { activePort.disconnect(); } catch { /* ignore */ }
        activePort = null;
      }
      if (panelEl && panelEl.isConnected) {
        resetPanel(panelEl);
      }
    }

    if (!panelEl || !panelEl.isConnected) {
      const el = mountPanel();
      if (el) resetPanel(el);
    }
  }

  document.addEventListener('yt-navigate-finish', onUrlMaybeChanged);
  window.addEventListener('popstate', onUrlMaybeChanged);

  // 초기 진입에서 #secondary가 아직 렌더되지 않은 경우를 대비해 짧게 재시도
  let tries = 0;
  const tick = setInterval(() => {
    onUrlMaybeChanged();
    if (++tries > 40 || (panelEl && panelEl.isConnected)) clearInterval(tick);
  }, 250);
})();
