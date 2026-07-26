// PATTI SHOT - capture orchestration.
//
// Same engine as the verified desktop version: STEP1 preprocessing, STEP2 real
// content-height measurement (never trust scrollHeight), a single shot while it
// fits Chrome's raster limit, and scroll-stitch beyond it (a clip with a high
// y-offset silently renders the wrong content past ~16384 device px).
// chrome.debugger gives us the same CDP commands the desktop app used, so the
// capture quality carries over unchanged.

const SINGLE_SHOT_MAX_DEVICE = 16000;   // measured Chrome raster limit
const DEBUGGER_VERSION = '1.3';

const state = { busy: false };

// --------------------------------------------------------------------------- //
// helpers
// --------------------------------------------------------------------------- //
function sendCmd(tabId, method, params) {
  return new Promise((resolve, reject) => {
    chrome.debugger.sendCommand({ tabId }, method, params || {}, (res) => {
      const e = chrome.runtime.lastError;
      if (e) reject(new Error(method + ': ' + e.message));
      else resolve(res);
    });
  });
}

function attach(tabId) {
  return new Promise((resolve, reject) => {
    chrome.debugger.attach({ tabId }, DEBUGGER_VERSION, () => {
      const e = chrome.runtime.lastError;
      if (e && !/already attached/i.test(e.message)) reject(new Error(e.message));
      else resolve();
    });
  });
}

function detach(tabId) {
  return new Promise((resolve) => chrome.debugger.detach({ tabId }, () => {
    void chrome.runtime.lastError; resolve();
  }));
}

async function runInPage(tabId, func, args) {
  const [res] = await chrome.scripting.executeScript({
    target: { tabId }, world: 'MAIN', func, args: args || [],
  });
  return res ? res.result : undefined;
}

async function injectPageLib(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId }, world: 'MAIN', files: ['pagelib.js'],
  });
}

function progress(tabId, done, total) {
  chrome.tabs.sendMessage(tabId, { type: 'progress', done, total }, () => void chrome.runtime.lastError);
}

// --------------------------------------------------------------------------- //
// offscreen document (canvas work: stitch / trim / blank-check / encode)
// --------------------------------------------------------------------------- //
async function ensureOffscreen() {
  const has = await chrome.offscreen.hasDocument?.();
  if (has) return;
  await chrome.offscreen.createDocument({
    url: 'offscreen.html',
    reasons: ['BLOBS'],
    justification: 'Stitch and encode the captured page image into PNG/PDF.',
  });
}

function askOffscreen(msg) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(Object.assign({ target: 'offscreen' }, msg), (res) => {
      const e = chrome.runtime.lastError;
      if (e) reject(new Error(e.message));
      else if (!res) reject(new Error('offscreen: 応答なし'));
      else if (res.error) reject(new Error(res.error));
      else resolve(res);
    });
  });
}

// --------------------------------------------------------------------------- //
// capture
// --------------------------------------------------------------------------- //
async function captureTab(tab, settings) {
  const tabId = tab.id;
  const scale = Math.max(1, Math.min(3, parseInt(settings.scale, 10) || 2));
  const fmt = settings.fmt || 'both';

  await injectPageLib(tabId);
  await runInPage(tabId, () => window.__PATTISHOT__.prepare());
  const m = await runInPage(tabId, () => window.__PATTISHOT__.measure());
  const cssW = await runInPage(tabId, () => window.innerWidth);
  const cssH = Math.max(1, Math.round(m.captureHeight));

  // hide our own UI so it can never appear in the capture
  await runInPage(tabId, () => { window.__PATTISHOT__._hideRestore = window.__PATTISHOT__._hideUI(); });

  await attach(tabId);
  await ensureOffscreen();

  const split = cssH * scale > SINGLE_SHOT_MAX_DEVICE;
  let bands = 0;
  const trace = [];
  let finalCssH = cssH;              // may change under an emulated viewport
  let contentH = m.contentHeight;
  try {
    if (!split) {
      await askOffscreen({ cmd: 'begin', width: cssW * scale, height: cssH * scale });
      progress(tabId, 0, 1);
      // clip.scale multiplies the DISPLAY's device pixel ratio, so on a 125%
      // display "2x" silently produced 2.5x (measured: 14,772 px for a 5,923 px
      // page). Divide it out so 2x means exactly 2x everywhere, which also keeps
      // very long pages from hitting the canvas limit sooner than expected.
      const dpr = await runInPage(tabId, () => window.devicePixelRatio || 1);
      const shot = await sendCmd(tabId, 'Page.captureScreenshot', {
        format: 'png', captureBeyondViewport: true, fromSurface: true,
        clip: { x: 0, y: 0, width: cssW, height: cssH, scale: scale / dpr },
      });
      await askOffscreen({ cmd: 'band', dataUrl: 'data:image/png;base64,' + shot.data, y: 0 });
      bands = 1;
      progress(tabId, 1, 1);
    } else {
      // scroll-stitch: neutralise fixed/sticky so scrolling duplicates nothing,
      // set the device scale, then screenshot each scrolled viewport (no clip,
      // so we never hit the high-offset raster limit).
      await runInPage(tabId, () => window.__PATTISHOT__.neutralizeFixed());
      // Emulate a taller viewport so a long page needs far fewer round-trips
      // (48,000 px page: ~54 captures at 900 px -> ~14 at 3,600 px). Kept well
      // under the raster limit: 3,600 x 3 = 10,800 < 16,384.
      const vp = Math.min(3600, Math.max(900, Math.round(m.viewport)) *
                          Math.max(1, Math.floor(4 / scale) + 1));
      await sendCmd(tabId, 'Emulation.setDeviceMetricsOverride',
        { width: cssW, height: vp, deviceScaleFactor: scale, mobile: false });
      try {
        // The taller viewport reflows the page, so the height measured with the
        // old viewport is stale. Stitching against a stale total misaligns the
        // bands and repeats rows -- measure again before allocating anything.
        await new Promise((r) => setTimeout(r, 400));
        const m2 = await runInPage(tabId, () => window.__PATTISHOT__.measure());
        finalCssH = Math.max(1, Math.round(m2.captureHeight));
        contentH = m2.contentHeight;
        await askOffscreen({ cmd: 'begin', width: cssW * scale, height: finalCssH * scale });

        const totalDev = Math.round(finalCssH * scale);
        const estimate = Math.max(1, Math.ceil(totalDev / Math.round(vp * scale)));

        // Scroll down with a deliberate OVERLAP and let the stitcher find the
        // true join by matching pixels. Scroll positions are only a hint here:
        // asking the page where it is (and trusting the answer) is what made
        // rows repeat, because the reported position and the pixels that come
        // back can disagree.
        const OVERLAP_CSS = Math.max(60, Math.round(vp * 0.15));
        let yCss = 0, guard = 0, stuck = 0;
        let filled = 0;
        while (guard++ < 4000) {
          progress(tabId, bands, estimate);
          await runInPage(tabId, (y) => {
            window.scrollTo({ top: y, left: 0, behavior: 'instant' });
            return new Promise((res) => {
              let last = -1, same = 0, n = 0;
              const tick = () => {
                const cy = window.scrollY;
                if (Math.abs(cy - last) < 0.5) { if (++same >= 2) return res(cy); }
                else same = 0;
                last = cy;
                if (++n > 90) return res(cy);          // hard cap ~1.5s
                requestAnimationFrame(tick);
              };
              requestAnimationFrame(tick);
            });
          }, [yCss]);

          const actual = await runInPage(tabId, () => window.scrollY);
          const shot = await sendCmd(tabId, 'Page.captureScreenshot',
            { format: 'png', captureBeyondViewport: false, fromSurface: true });
          // how much of this capture should already be assembled: the top of
          // the viewport sits at `actual`, and we have content down to `filled`
          const overlapDev = Math.max(0, filled - Math.round(actual * scale));
          const r = await askOffscreen({
            cmd: 'band', dataUrl: 'data:image/png;base64,' + shot.data,
            expectedOverlap: overlapDev,
          });

          if (r.noOverlap) {
            trace.push(`y=${Math.round(yCss)} act=${Math.round(actual)} ov=${overlapDev} NO-OVERLAP ` +
                       `rawBest=${(r.rawBest||0).toFixed(1)}@${r.rawAt} want=${r.want} n=${r.n} win=[${r.lo},${r.hi}]`);
            // The join could not be proven. Never guess a position (guessing is
            // what duplicated rows): scroll back so more of the assembled tail
            // is on screen and retake.
            if (++stuck > 8) break;
            yCss = Math.max(0, (filled / scale) - OVERLAP_CSS * (1 + stuck));
            continue;
          }
          trace.push(`y=${Math.round(yCss)} act=${Math.round(actual)} ov=${overlapDev} ` +
                     `bh=${r.bh} start=${r.start} tail=${r.tailRows} ` +
                     `rows=${r.rows || 0} filled=${r.filled || filled} q=${(r.quality || 0).toFixed(1)}`);
          stuck = 0;
          if (r.atBottom || !r.rows) break;            // nothing new: page ended
          filled = r.filled;
          bands++;
          if (filled >= totalDev) break;
          // Drive the next scroll from what is ACTUALLY assembled, not from a
          // fixed step: advancing blindly outruns the capture and leaves gaps
          // (measured: half the page missing).
          yCss = Math.max(0, (filled / scale) - OVERLAP_CSS);
        }
      } finally {
        await sendCmd(tabId, 'Emulation.clearDeviceMetricsOverride').catch(() => {});
        await runInPage(tabId, () => window.scrollTo(0, 0));
      }
    }
  } finally {
    await detach(tabId);
    await runInPage(tabId, () => {
      if (window.__PATTISHOT__._hideRestore) window.__PATTISHOT__._hideRestore();
      window.__PATTISHOT__.restoreAll();
    });
  }

  // finish: trailing trim + blank check + encode + save
  const maxTrim = Math.max(0, Math.round((finalCssH - contentH) * scale) + 4 * scale);
  const out = await askOffscreen({
    cmd: 'finish', fmt, scale, maxTrim,
    base: basename(tab.url), contentHeight: contentH,
  });

  const files = [];
  for (const f of out.files) {
    await new Promise((resolve, reject) => {
      chrome.downloads.download({ url: f.url, filename: f.name, saveAs: false }, (id) => {
        const e = chrome.runtime.lastError;
        if (e) reject(new Error(e.message)); else { files.push(f.name); resolve(id); }
      });
    });
  }
  await askOffscreen({ cmd: 'cleanup' });
  return {
    ok: true, files, bands, split, blankRuns: out.blankRuns, trace,
    diag: { cssW, cssH, finalCssH, contentH, scale, outW: out.width, outH: out.height, trimmed: out.trimmed },
    // be explicit when a very long page forced a compromise on the PNG
    note: (out.pngParts > 1)
      ? `※とても長いページのため、PNGは${out.pngParts}枚に分けて保存しました（PDFは1つです）`
      : (out.pngScale && out.pngScale < scale
         ? `※とても長いページのため、PNGは1枚に収まるよう${out.pngScale}倍で保存しました（PDFは${scale}倍のままです）`
         : ''),
  };
}

function basename(url) {
  let host = 'page';
  try { host = new URL(url).hostname.replace(/^www\./, '') || 'page'; } catch (e) {}
  host = host.replace(/[^a-zA-Z0-9.-]/g, '-');
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return 'PATTI SHOT/PATTISHOT_' + host + '_' + d.getFullYear() + p(d.getMonth() + 1) +
         p(d.getDate()) + '_' + p(d.getHours()) + p(d.getMinutes()) + p(d.getSeconds());
}

// --------------------------------------------------------------------------- //
// entry points
// --------------------------------------------------------------------------- //
async function handleCapture(tab, settings) {
  if (state.busy) return { ok: false, error: 'いま撮影中です。少し待ってからもう一度どうぞ。' };
  if (!tab || !tab.id || !/^https?:/i.test(tab.url || '')) {
    return { ok: false, error: 'このページは撮影できません（通常のWebページで使ってください）' };
  }
  state.busy = true;
  try {
    return await captureTab(tab, settings || { fmt: 'both', scale: 2 });
  } catch (e) {
    try { await detach(tab.id); } catch (_) {}
    return { ok: false, error: String((e && e.message) || e) };
  } finally {
    state.busy = false;
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.target === 'offscreen') return;      // not ours
  if (msg.type === 'capture') {
    const tab = sender.tab;
    if (tab) {
      handleCapture(tab, msg.settings).then(sendResponse);
    } else {
      chrome.tabs.query({ active: true, currentWindow: true },
        (tabs) => handleCapture(tabs[0], msg.settings).then(sendResponse));
    }
    return true;                                        // async response
  }
});

// toolbar icon / keyboard shortcut -> ask the page's UI to run the same flow
chrome.commands.onCommand.addListener((cmd) => {
  if (cmd !== 'capture-page') return;
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];
    if (!tab) return;
    chrome.tabs.sendMessage(tab.id, { type: 'shoot' }, () => {
      if (chrome.runtime.lastError) handleCapture(tab, undefined);   // no content script
    });
  });
});
