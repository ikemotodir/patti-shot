"""Injected floating UI (spec section 3).

A pink round PATTI SHOT button (bottom-right), a settings panel (output format
PNG/PDF/both, resolution 1x/2x/3x), and a completion toast. Every element
carries ``data-patti-shot-ui`` so the engine hides it during capture and the
harness verifies it never appears in the output. Live progress is shown via the
tab title (never part of the screenshot), driven from Python.

Communication is via <html> attributes polled by the Python main loop (a
binding cannot make the long, nested Playwright calls a capture needs):
    request : documentElement[data-patti-shot-request] = {fmt,scale,id}
    result  : documentElement[data-patti-shot-result]  = {ok,files,error,id}
    settings: documentElement[data-patti-shot-settings] = {fmt,scale}
Initial settings arrive as window.__PATTISHOT_SETTINGS__.
"""

PINK = "#ff2d78"

FLOATING_UI_JS = r"""
(() => {
  if (window.top !== window.self) return;         // top frame only
  if (window.__PATTISHOT_UI__) return;
  window.__PATTISHOT_UI__ = true;
  const PINK = '__PINK__';
  let settings = Object.assign({ fmt: 'both', scale: 2 }, window.__PATTISHOT_SETTINGS__ || {});
  let busy = false, reqId = 0;

  const el = (tag, css, attrs) => {
    const e = document.createElement(tag);
    e.setAttribute('data-patti-shot-ui', '1');
    if (css) Object.assign(e.style, css);
    if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  };

  function build() {
    if (!document.body || document.getElementById('patti-shot-fab')) return;
    const de = document.documentElement;

    const panel = el('div', {
      position: 'fixed', right: '20px', bottom: '116px', zIndex: '2147483647',
      width: '232px', background: '#fff', color: '#222', borderRadius: '14px',
      boxShadow: '0 8px 30px rgba(0,0,0,.25)', padding: '14px 16px',
      font: '13px/1.5 sans-serif', display: 'none',
    }, { id: 'patti-shot-panel' });
    panel.innerHTML =
      "<div style='font-weight:700;margin-bottom:8px;color:" + PINK + "'>PATTI SHOT 設定</div>" +
      "<div style='margin-bottom:6px'>保存形式</div>" +
      "<label style='margin-right:10px'><input type='radio' name='ps-fmt' value='png'> PNG</label>" +
      "<label style='margin-right:10px'><input type='radio' name='ps-fmt' value='pdf'> PDF</label>" +
      "<label><input type='radio' name='ps-fmt' value='both'> 両方</label>" +
      "<div style='margin:10px 0 6px'>画質(倍率)</div>" +
      "<label style='margin-right:10px'><input type='radio' name='ps-scale' value='1'> 1x</label>" +
      "<label style='margin-right:10px'><input type='radio' name='ps-scale' value='2'> 2x</label>" +
      "<label><input type='radio' name='ps-scale' value='3'> 3x</label>";
    panel.querySelectorAll('*').forEach(n => n.setAttribute('data-patti-shot-ui', '1'));
    document.body.appendChild(panel);

    const fab = el('div', {
      position: 'fixed', right: '20px', bottom: '20px', zIndex: '2147483647',
      width: '84px', height: '84px', borderRadius: '50%', background: PINK,
      color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
      textAlign: 'center', font: '700 11px/1.2 sans-serif',
      boxShadow: '0 4px 16px rgba(0,0,0,.3)', cursor: 'pointer', userSelect: 'none',
    }, { id: 'patti-shot-fab', title: 'クリックで撮影 / 長押しで設定' });
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
      maxWidth: '300px', background: '#222', color: '#fff', borderRadius: '10px',
      padding: '10px 14px', font: '13px/1.5 sans-serif', whiteSpace: 'pre-line',
      boxShadow: '0 6px 20px rgba(0,0,0,.3)', display: 'none',
    }, { id: 'patti-shot-toast' });

    // update pill (hidden until the app reports a newer release)
    const upd = el('div', {
      position: 'fixed', right: '112px', bottom: '38px', zIndex: '2147483647',
      background: '#fff', color: PINK, border: '2px solid ' + PINK,
      borderRadius: '999px', padding: '8px 16px', font: '700 12px/1.4 sans-serif',
      boxShadow: '0 4px 14px rgba(0,0,0,.25)', cursor: 'pointer', display: 'none',
      userSelect: 'none',
    }, { id: 'patti-shot-update', title: '新しいバージョンに更新します' });

    document.body.appendChild(fab);
    document.body.appendChild(gear);
    document.body.appendChild(toast);
    document.body.appendChild(upd);

    upd.addEventListener('click', () => {
      upd.textContent = '更新中… ダウンロードしています';
      upd.style.pointerEvents = 'none';
      de.setAttribute('data-patti-shot-update', '1');
    });
    window.__PATTISHOT_UI_API__ = {
      showUpdate(tag) {
        if (upd.style.display === 'none') {
          upd.textContent = '⬆ 新しいバージョン ' + tag + ' があります／更新する';
          upd.style.display = 'block';
        }
      }
    };

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
      toast._t = setTimeout(() => { toast.style.display = 'none'; }, 6000);
    };
    const togglePanel = () => {
      panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
      toast.style.display = 'none';
    };

    gear.addEventListener('click', togglePanel);
    panel.addEventListener('change', (e) => {
      if (e.target.name === 'ps-fmt') settings.fmt = e.target.value;
      if (e.target.name === 'ps-scale') settings.scale = parseInt(e.target.value, 10);
      de.setAttribute('data-patti-shot-settings', JSON.stringify(settings));
    });

    let pressT = null;
    fab.addEventListener('mousedown', () => { pressT = setTimeout(() => { pressT = 'long'; togglePanel(); }, 550); });
    fab.addEventListener('mouseup', () => { if (pressT && pressT !== 'long') clearTimeout(pressT); });

    const shoot = () => {
      if (busy) return;
      if (pressT === 'long') { pressT = null; return; }
      busy = true;
      const id = ++reqId;
      fab.textContent = '撮影中…'; fab.style.opacity = '.7';
      de.setAttribute('data-patti-shot-request', JSON.stringify({ fmt: settings.fmt, scale: settings.scale, id }));
      const poll = setInterval(() => {
        const raw = de.getAttribute('data-patti-shot-result');
        if (!raw) return;
        let res; try { res = JSON.parse(raw); } catch (e) { return; }
        if (res.id !== id) return;
        clearInterval(poll);
        de.removeAttribute('data-patti-shot-result');
        fab.textContent = 'PATTI SHOT'; fab.style.opacity = '1'; busy = false;
        if (res.ok) showToast('保存しました:\n' + (res.files || []).join('\n') + '\n(フォルダを開きました)');
        else showToast('撮影できませんでした:\n' + (res.error || '不明なエラー'), true);
      }, 200);
    };
    fab.addEventListener('click', shoot);
    applySettings();
  }

  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', build);
  else build();
})();
""".replace("__PINK__", PINK)
