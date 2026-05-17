const DEFAULT_BACKEND = 'http://localhost:8000';

const $input = document.getElementById('backend');
const $save = document.getElementById('save');
const $status = document.getElementById('status');

function setStatus(msg, kind) {
  $status.textContent = msg;
  $status.className = `status ${kind || ''}`.trim();
  if (msg) setTimeout(() => { if ($status.textContent === msg) $status.textContent = ''; }, 2500);
}

function normalize(url) {
  return (url || '').trim().replace(/\/+$/, '');
}

chrome.storage.sync.get(['backendUrl']).then(({ backendUrl }) => {
  $input.value = backendUrl || DEFAULT_BACKEND;
});

$save.addEventListener('click', async () => {
  const value = normalize($input.value) || DEFAULT_BACKEND;
  try {
    new URL(value);
  } catch {
    setStatus('올바른 URL 형식이 아니에요.', 'err');
    return;
  }
  await chrome.storage.sync.set({ backendUrl: value });
  $input.value = value;
  setStatus('저장됐어요 ✓', 'ok');
});

$input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') $save.click();
});
