const DEFAULTS = { fmt: 'both', scale: 2 };
const msg = document.getElementById('msg');

document.getElementById('ver').textContent =
  'v' + chrome.runtime.getManifest().version + ' / STUDIO PATTI';

function apply(s) {
  document.querySelectorAll("input[name='fmt']").forEach(i => i.checked = (i.value === s.fmt));
  document.querySelectorAll("input[name='scale']").forEach(i => i.checked = (i.value === String(s.scale)));
}

let settings = Object.assign({}, DEFAULTS);
chrome.storage.local.get('pattiShot', (v) => {
  if (v && v.pattiShot) settings = Object.assign(settings, v.pattiShot);
  apply(settings);
});

document.body.addEventListener('change', (e) => {
  if (e.target.name === 'fmt') settings.fmt = e.target.value;
  if (e.target.name === 'scale') settings.scale = parseInt(e.target.value, 10);
  chrome.storage.local.set({ pattiShot: settings });
});

document.getElementById('shoot').addEventListener('click', () => {
  msg.textContent = '撮影中… ページが長いと少し時間がかかります';
  chrome.runtime.sendMessage({ type: 'capture', settings }, (res) => {
    const err = chrome.runtime.lastError;
    if (err || !res) { msg.textContent = '撮影できませんでした：' + (err ? err.message : '応答なし'); return; }
    msg.textContent = res.ok
      ? '保存しました:\n' + (res.files || []).join('\n')
      : '撮影できませんでした：\n' + (res.error || '不明なエラー');
  });
});
