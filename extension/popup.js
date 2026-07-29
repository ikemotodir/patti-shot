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

// ---- update notice ---------------------------------------------------------
// Chrome only auto-updates extensions installed from the Web Store; a zip
// install cannot replace itself. The honest equivalent: check GitHub for a
// newer release and hand the user a one-click link. Fails silently offline.
(async () => {
  try {
    const r = await fetch(
      'https://api.github.com/repos/ikemotodir/patti-shot/releases?per_page=15');
    if (!r.ok) return;
    const rels = await r.json();
    const latest = (rels || []).find((x) =>
      x && x.tag_name && x.tag_name.indexOf('ext-v') === 0 && !x.draft && !x.prerelease);
    if (!latest) return;
    const cur = chrome.runtime.getManifest().version;
    const remote = latest.tag_name.slice(5);
    if (remote.localeCompare(cur, undefined, { numeric: true }) <= 0) return;
    const el = document.getElementById('update');
    el.textContent = '新しい版 v' + remote + ' が出ています。';
    const a = document.createElement('a');
    a.href = latest.html_url;
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = 'ダウンロードページを開く';
    el.appendChild(a);
    el.appendChild(document.createTextNode(
      '（zipを展開して、今のフォルダの中身と入れ替え → 拡張機能の「更新」ボタン）'));
    el.style.display = 'block';
  } catch (e) {}
})();

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
