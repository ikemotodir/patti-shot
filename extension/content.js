// PATTI SHOT - floating capture button injected into the page the user is
// already looking at. Same look and behaviour as the app version: a pink round
// button bottom-right, a gear for settings, progress and result toasts, and
// Ctrl+Shift+S / Alt+S. Everything carries data-patti-shot-ui so the capture
// engine hides it and the harness can prove it never appears in the output.
(() => {
  if (window.top !== window.self) return;          // top frame only
  if (window.__PATTISHOT_UI__) return;
  window.__PATTISHOT_UI__ = true;

  const PINK = '#D6336C';
  let settings = { fmt: 'both', scale: 2 };
  let busy = false;

  const el = (tag, css, attrs) => {
    const e = document.createElement(tag);
    e.setAttribute('data-patti-shot-ui', '1');
    if (css) Object.assign(e.style, css);
    if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  };

  function build() {
    if (!document.body || document.getElementById('patti-shot-fab')) return;

    const panel = el('div', {
      position: 'fixed', right: '20px', bottom: '116px', zIndex: '2147483647',
      width: '236px', background: '#fff', color: '#222', borderRadius: '14px',
      boxShadow: '0 8px 30px rgba(0,0,0,.25)', padding: '14px 16px',
      font: '13px/1.6 sans-serif', display: 'none',
    }, { id: 'patti-shot-panel' });
    const ver = (chrome.runtime.getManifest && chrome.runtime.getManifest().version) || '';
    panel.innerHTML =
      "<div style='font-weight:700;margin-bottom:8px;color:" + PINK + "'>PATTI SHOT 設定" +
      (ver ? " <span style='font-weight:400;color:#888'>v" + ver + "</span>" : "") + "</div>" +
      "<div style='margin-bottom:6px'>保存形式</div>" +
      "<label style='margin-right:10px'><input type='radio' name='ps-fmt' value='png'> PNG</label>" +
      "<label style='margin-right:10px'><input type='radio' name='ps-fmt' value='pdf'> PDF</label>" +
      "<label><input type='radio' name='ps-fmt' value='both'> 両方</label>" +
      "<div style='margin:10px 0 6px'>画質(倍率)</div>" +
      "<label style='margin-right:10px'><input type='radio' name='ps-scale' value='1'> 1x</label>" +
      "<label style='margin-right:10px'><input type='radio' name='ps-scale' value='2'> 2x</label>" +
      "<label><input type='radio' name='ps-scale' value='3'> 3x</label>" +
      "<div style='margin-top:10px;color:#888;font-size:11px'>Ctrl+Shift+S でも撮影できます</div>";
    panel.querySelectorAll('*').forEach(n => n.setAttribute('data-patti-shot-ui', '1'));
    document.body.appendChild(panel);

    const fab = el('div', {
      position: 'fixed', right: '20px', bottom: '20px', zIndex: '2147483647',
      width: '84px', height: '84px', borderRadius: '50%', background: PINK,
      color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
      textAlign: 'center', font: '700 11px/1.2 sans-serif',
      boxShadow: '0 4px 16px rgba(0,0,0,.3)', cursor: 'pointer', userSelect: 'none',
    }, { id: 'patti-shot-fab',
         title: 'クリックでこのページを丸ごと撮影（Ctrl+Shift+S）／長押しで設定' });
    fab.textContent = 'PATTI SHOT';

    const gear = el('div', {
      position: 'fixed', right: '20px', bottom: '92px', zIndex: '2147483647',
      width: '30px', height: '30px', borderRadius: '50%', background: '#fff',
      color: PINK, display: 'flex', alignItems: 'center', justifyContent: 'center',
      boxShadow: '0 2px 8px rgba(0,0,0,.25)', cursor: 'pointer', fontSize: '16px',
    }, { id: 'patti-shot-gear', title: '設定' });
    gear.textContent = '⚙';

    const toast = el('div', {
      position: 'fixed', right: '20px', bottom: '116px', zIndex: '2147483647',
      maxWidth: '320px', background: '#222', color: '#fff', borderRadius: '10px',
      padding: '10px 14px', font: '13px/1.6 sans-serif', whiteSpace: 'pre-line',
      boxShadow: '0 6px 20px rgba(0,0,0,.3)', display: 'none',
    }, { id: 'patti-shot-toast' });

    document.body.appendChild(fab);
    document.body.appendChild(gear);
    document.body.appendChild(toast);

    const applySettings = () => {
      panel.querySelectorAll("input[name='ps-fmt']").forEach(i => i.checked = (i.value === settings.fmt));
      panel.querySelectorAll("input[name='ps-scale']").forEach(i => i.checked = (i.value === String(settings.scale)));
    };
    const showToast = (msg, err) => {
      toast.textContent = msg;
      toast.style.background = err ? '#a11' : '#222';
      toast.style.display = 'block';
      panel.style.display = 'none';
      clearTimeout(toast._t);
      toast._t = setTimeout(() => { toast.style.display = 'none'; }, 7000);
    };
    const togglePanel = () => {
      panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
      toast.style.display = 'none';
    };

    gear.addEventListener('click', togglePanel);
    panel.addEventListener('change', (e) => {
      if (e.target.name === 'ps-fmt') settings.fmt = e.target.value;
      if (e.target.name === 'ps-scale') settings.scale = parseInt(e.target.value, 10);
      chrome.storage.local.set({ pattiShot: settings });
    });

    let pressT = null;
    fab.addEventListener('mousedown', () => {
      pressT = setTimeout(() => { pressT = 'long'; togglePanel(); }, 550);
    });
    fab.addEventListener('mouseup', () => { if (pressT && pressT !== 'long') clearTimeout(pressT); });

    function shoot() {
      if (busy) return;
      if (pressT === 'long') { pressT = null; return; }
      busy = true;
      fab.textContent = '撮影中…';
      fab.style.opacity = '.7';
      chrome.runtime.sendMessage({ type: 'capture', settings }, (res) => {
        busy = false;
        fab.textContent = 'PATTI SHOT';
        fab.style.opacity = '1';
        const err = chrome.runtime.lastError;
        if (err || !res) { showToast('撮影できませんでした：' + (err ? err.message : '応答なし'), true); return; }
        if (res.ok) showToast('保存しました:\n' + (res.files || []).join('\n')
                              + (res.note ? '\n' + res.note : ''));
        else showToast('撮影できませんでした：\n' + (res.error || '不明なエラー'), true);
      });
    }
    fab.addEventListener('click', shoot);
    window.__PATTISHOT_SHOOT__ = shoot;

    const onKey = (e) => {
      const k = (e.key || '').toLowerCase();
      if ((e.ctrlKey && e.shiftKey && k === 's') || (e.altKey && k === 's')) {
        e.preventDefault(); e.stopPropagation(); shoot();
      }
    };
    window.addEventListener('keydown', onKey, true);
    document.addEventListener('keydown', onKey, true);

    // keep the control usable at any window size
    const fit = () => {
      const short = window.innerHeight < 560, small = window.innerWidth < 480;
      const size = (short || small) ? 58 : 84;
      fab.style.width = fab.style.height = size + 'px';
      fab.style.font = (short || small) ? '700 9px/1.2 sans-serif' : '700 11px/1.2 sans-serif';
      fab.style.bottom = (short ? 8 : 20) + 'px';
      fab.style.right = (short ? 8 : 20) + 'px';
      gear.style.bottom = (short ? 8 + size + 4 : 92) + 'px';
      gear.style.right = (short ? 8 : 20) + 'px';
      panel.style.bottom = toast.style.bottom = (short ? 8 + size + 40 : 116) + 'px';
    };
    fit();
    window.addEventListener('resize', fit);

    // SPAs can rebuild the DOM and drop our nodes -- put them back
    clearInterval(window.__PATTISHOT_KEEPALIVE__);
    window.__PATTISHOT_KEEPALIVE__ = setInterval(() => {
      if (document.body && !document.getElementById('patti-shot-fab')) build();
    }, 1500);

    applySettings();
    window.__PATTISHOT_UI_API__ = {
      progress(done, total) {
        if (!busy) return;
        fab.textContent = total > 1 ? ('撮影中\n' + done + '/' + total) : '撮影中…';
      },
      toast: showToast,
    };
  }

  // progress / messages pushed from the background worker
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg && msg.type === 'progress' && window.__PATTISHOT_UI_API__)
      window.__PATTISHOT_UI_API__.progress(msg.done, msg.total);
    if (msg && msg.type === 'shoot' && window.__PATTISHOT_SHOOT__)
      window.__PATTISHOT_SHOOT__();
  });

  chrome.storage.local.get('pattiShot', (v) => {
    if (v && v.pattiShot) settings = Object.assign(settings, v.pattiShot);
    if (document.readyState === 'loading')
      document.addEventListener('DOMContentLoaded', build);
    else build();
  });
})();
