const STAGE_ORDER = ['collecting', 'filtering', 'summarizing', 'done'];

const STAGE_CAPTION = {
  queued:      '🕐 잠깐만요, 곧 시작할게요!',
  collecting:  '📥 자막이랑 댓글 긁어오는 중이에요',
  filtering:   '🔍 쓸모 있는 댓글만 골라내고 있어요',
  summarizing: '✍️ 요약문을 열심히 쓰고 있어요',
  done:        '🎉 요약이 완성됐어요!',
};

const $form       = document.getElementById('form');
const $url        = document.getElementById('url');
const $submitBtn  = document.getElementById('submit-btn');
const $errorBox   = document.getElementById('error-box');
const $videoWrap  = document.getElementById('video-wrap');
const $videoFrame = document.getElementById('video-frame');
const $pipeline   = document.getElementById('pipeline');
const $caption    = document.getElementById('progress-caption');
const $results    = document.getElementById('results');
const TS_RE = /\b(?:(\d+):)?([0-5]?\d):([0-5]\d)\b/g;
let currentVideoId = null;

function extractVideoId(url) {
  try {
    const u = new URL(url);
    if (u.hostname === 'youtu.be') return u.pathname.slice(1).split('?')[0];
    if (u.hostname.includes('youtube.com')) return u.searchParams.get('v');
  } catch { /* ignore */ }
  return null;
}

function showVideo(url) {
  const id = extractVideoId(url);
  if (!id) return;
  currentVideoId = id;
  $videoFrame.src = `https://www.youtube.com/embed/${id}`;
  $videoWrap.classList.add('visible');
}

function esc(s) {
  return (s || '').replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])
  );
}

function resetUI() {
  $errorBox.textContent = '';
  $errorBox.classList.remove('visible');
  $videoFrame.src = '';
  currentVideoId = null;
  $videoWrap.classList.remove('visible');
  $pipeline.classList.remove('visible');
  $results.classList.remove('visible');

  STAGE_ORDER.forEach(s => {
    const el = document.getElementById(`stage-${s}`);
    if (el) el.className = 'stage';
  });

  ['card-0', 'card-1', 'card-2', 'filter-stats'].forEach(id => {
    document.getElementById(id)?.classList.remove('revealed');
  });
}

function updatePipeline(status, progress) {
  $pipeline.classList.add('visible');

  const idx = STAGE_ORDER.indexOf(status);
  STAGE_ORDER.forEach((s, i) => {
    const el = document.getElementById(`stage-${s}`);
    if (!el) return;
    if (i < idx)       el.className = 'stage done';
    else if (i === idx) el.className = 'stage active';
    else                el.className = 'stage';
  });

  const pct = Math.round((progress || 0) * 100);
  const base = STAGE_CAPTION[status] || status;
  $caption.textContent = pct > 0 && status !== 'done' ? `${base} (${pct}%)` : base;
}

function showError(msg) {
  $errorBox.textContent = msg;
  $errorBox.classList.add('visible');
  $pipeline.classList.remove('visible');
}

function renderResult(payload) {
  updatePipeline('done', 1);

  const s     = payload.summary      || {};
  const stats = payload.filter_stats || {};

  setTimestampRichText(document.getElementById('body-content'), s.content || '');
  setTimestampRichText(document.getElementById('body-reaction'), s.reaction || '');
  setTimestampRichText(document.getElementById('body-highlights'), s.highlights || '');

  const gp = stats.passed_general   ?? '?';
  const gt = stats.total_general    ?? '?';
  const tp = stats.passed_timestamp ?? '?';
  const tt = stats.total_timestamp  ?? '?';

  document.getElementById('stat-general').innerHTML   = `<span class="pass">${esc(String(gp))}</span> / ${esc(String(gt))}`;
  document.getElementById('stat-timestamp').innerHTML = `<span class="pass">${esc(String(tp))}</span> / ${esc(String(tt))}`;

  $results.classList.add('visible');
  $submitBtn.disabled = false;

  // Staggered card reveal
  setTimeout(() => document.getElementById('card-0').classList.add('revealed'), 80);
  setTimeout(() => document.getElementById('card-1').classList.add('revealed'), 260);
  setTimeout(() => document.getElementById('card-2').classList.add('revealed'), 440);
  setTimeout(() => document.getElementById('filter-stats').classList.add('revealed'), 600);
}

function parseTimestampToSeconds(token) {
  const parts = token.split(':').map((v) => Number(v));
  if (parts.some((v) => Number.isNaN(v))) return null;
  if (parts.length === 2) {
    const [m, s] = parts;
    return m * 60 + s;
  }
  if (parts.length === 3) {
    const [h, m, s] = parts;
    return h * 3600 + m * 60 + s;
  }
  return null;
}

function seekEmbedVideo(seconds) {
  if (!currentVideoId) return;
  const start = Math.max(0, Math.floor(seconds));
  $videoFrame.src = `https://www.youtube.com/embed/${currentVideoId}?start=${start}&autoplay=1`;
}

function setTimestampRichText(targetEl, text) {
  targetEl.textContent = '';
  if (!text) return;

  TS_RE.lastIndex = 0;
  let last = 0;
  let match;

  while ((match = TS_RE.exec(text)) !== null) {
    if (match.index > last) {
      targetEl.appendChild(document.createTextNode(text.slice(last, match.index)));
    }

    const token = match[0];
    const seconds = parseTimestampToSeconds(token);
    if (seconds == null) {
      targetEl.appendChild(document.createTextNode(token));
    } else {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'timestamp-link';
      btn.textContent = token;
      btn.addEventListener('click', () => seekEmbedVideo(seconds));
      targetEl.appendChild(btn);
    }
    last = match.index + token.length;
  }

  if (last < text.length) {
    targetEl.appendChild(document.createTextNode(text.slice(last)));
  }
}

async function pollJob(jobId) {
  while (true) {
    let meta;
    try {
      const res = await fetch(`/jobs/${jobId}`);
      if (!res.ok) {
        showError(`😥 상태 조회에 실패했어요 (${res.status})`);
        $submitBtn.disabled = false;
        return;
      }
      meta = await res.json();
    } catch (err) {
      showError(`😥 네트워크 연결에 문제가 생겼어요: ${err.message}`);
      $submitBtn.disabled = false;
      return;
    }

    updatePipeline(meta.status, meta.progress);

    if (meta.status === 'done') {
      try {
        const r = await fetch(`/jobs/${jobId}/result`);
        renderResult(await r.json());
      } catch (err) {
        showError(`😥 결과를 받아오지 못했어요: ${err.message}`);
        $submitBtn.disabled = false;
      }
      return;
    }

    if (meta.status === 'failed') {
      const msg = meta.error
        ? `${meta.error.code}: ${meta.error.message}`
        : '알 수 없는 오류';
      showError(`😢 요약하다가 문제가 생겼어요 — ${msg}`);
      $submitBtn.disabled = false;
      return;
    }

    await new Promise(r => setTimeout(r, 2000));
  }
}

$form.addEventListener('submit', async (e) => {
  e.preventDefault();
  resetUI();
  $submitBtn.disabled = true;
  showVideo($url.value);
  updatePipeline('queued', 0);
  $caption.textContent = '🚀 요청을 보내고 있어요...';

  try {
    const res = await fetch('/jobs', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ url: $url.value }),
    });
    if (!res.ok) throw new Error(`서버 오류 ${res.status}`);
    const body = await res.json();

    if (body.cached && body.result) {
      renderResult(body.result);
      return;
    }
    pollJob(body.job_id);
  } catch (err) {
    showError(`😥 요청을 보내지 못했어요: ${err.message}`);
    $submitBtn.disabled = false;
  }
});
