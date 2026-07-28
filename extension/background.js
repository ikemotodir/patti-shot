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
  const trace = [];

  await injectPageLib(tabId);
  await runInPage(tabId, () => window.__PATTISHOT__.prepare());
  const cssW = await runInPage(tabId, () => window.innerWidth);

  // hide our own UI so it can never appear in the capture
  await runInPage(tabId, () => { window.__PATTISHOT__._hideRestore = window.__PATTISHOT__._hideUI(); });

  await attach(tabId);
  await ensureOffscreen();

  let r = null;
  try {
    // A page can be TALLER than it says it is: lists that render only as you
    // reach them, content that appears a moment late. Measuring once and
    // trusting it produces a page cut off in the middle - the worst failure of
    // all, because it still looks like a perfectly good screenshot. So the
    // page is asked again after the capture, and if it grew, it is captured
    // again. Only a height that holds still is accepted.
    for (let attempt = 1; attempt <= 4; attempt++) {
      r = await captureOnce(tabId, cssW, scale, trace, attempt);
      // Re-measuring on its own cannot see a list that renders only when you
      // reach it, so go back to the bottom and give it a moment first.
      const now = await runInPage(tabId, async () => {
        const P = window.__PATTISHOT__;
        const wait = (ms) => new Promise((r) => setTimeout(r, ms));
        const ext = () => P.measure().scrollHeight;
        const before = ext();
        if (before > window.innerHeight + 8) {      // a page that cannot scroll
          P.scrollTo(before);                       // cannot have more to load
          for (let i = 0; i < 8; i++) { await wait(120); if (ext() > before) break; }
          P.scrollTo(0);
          await wait(60);
        }
        return P.measure();
      });
      const nowH = Math.max(1, Math.round(now.captureHeight));
      if (nowH <= r.finalCssH + 8) break;
      trace.push(`ページが伸びた: ${r.finalCssH} -> ${nowH} css px (${attempt}回目・撮り直し)`);
      r.contentH = Math.max(r.contentH, now.contentHeight);
      r.grew = true;
    }
  } finally {
    await detach(tabId);
    await runInPage(tabId, () => {
      if (window.__PATTISHOT__._hideRestore) window.__PATTISHOT__._hideRestore();
      window.__PATTISHOT__.restoreAll();
    });
  }
  const { cssH, finalCssH, contentH, split, bands, degradedBands, shifted, suspect } = r;

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

  // A capture that stops in the middle of the page still looks like a good
  // screenshot, so it must never pass quietly: say it out loud.
  const savedCssH = Math.round(out.height / scale);
  const shortBy = Math.round(contentH - savedCssH);
  const truncated = shortBy > Math.max(120, contentH * 0.02);
  if (truncated) trace.push(`※途中までしか撮れていない: ${savedCssH} / ${contentH} css px`);

  const notes = [];
  if (suspect) {
    notes.push(`※${suspect}箇所で貼り合わせ位置を確定できませんでした。` +
               `画像を一度ご確認ください`);
  }
  if (truncated) {
    notes.push(`※ページの途中（約${Math.round(savedCssH / contentH * 100)}%）までしか撮れませんでした。` +
               `もう一度お試しください`);
  }
  if (out.pngParts > 1) {
    notes.push(`※とても長いページのため、PNGは${out.pngParts}枚に分けて保存しました（PDFは1つです）`);
  } else if (out.pngScale && out.pngScale < scale) {
    notes.push(`※とても長いページのため、PNGは1枚に収まるよう${out.pngScale}倍で保存しました（PDFは${scale}倍のままです）`);
  }
  return {
    ok: true, files, bands, split, blankRuns: out.blankRuns, trace, truncated,
    diag: { cssW, cssH, finalCssH, contentH, scale, degradedBands, shifted, suspect, savedCssH,
            outW: out.width, outH: out.height, trimmed: out.trimmed },
    note: notes.join('\n'),
  };
}

// One pass over the page. Returns what it managed to assemble; the caller
// decides whether the page has stopped changing.
async function captureOnce(tabId, cssW, scale, trace, attempt) {
  const m = await runInPage(tabId, () => window.__PATTISHOT__.measure());
  const cssH = Math.max(1, Math.round(m.captureHeight));
  const split = cssH * scale > SINGLE_SHOT_MAX_DEVICE;
  let bands = 0;
  let degradedBands = 0;
  let shifted = 0;
  let suspect = 0;
  let finalCssH = cssH;              // may change under an emulated viewport
  let contentH = m.contentHeight;
  trace.push(`--- ${attempt}回目: ${cssW}x${cssH} css px / ${scale}倍 / ` +
             (split ? '分割撮影' : '一発撮り'));

  if (!split) {
    await askOffscreen({ cmd: 'begin', width: cssW * scale, height: cssH * scale });
    progress(tabId, 0, 1);
    // clip.scale multiplies the DISPLAY's device pixel ratio, so on a 125%
    // display "2x" silently produced 2.5x (measured: 14,772 px for a 5,923 px
    // page). Divide it out so 2x means exactly 2x everywhere.
    // Then CHECK what actually came back rather than trusting that arithmetic:
    // it depends on the display, and a capture that is silently half size
    // would otherwise be saved as if nothing were wrong.
    const dpr = await runInPage(tabId, () => window.devicePixelRatio || 1);
    const want = Math.round(cssW * scale);
    let k = scale / dpr;
    for (let tries = 0; tries < 3; tries++) {
      const shot = await sendCmd(tabId, 'Page.captureScreenshot', {
        format: 'png', captureBeyondViewport: true, fromSurface: true,
        clip: { x: 0, y: 0, width: cssW, height: cssH, scale: k },
      });
      const res = await askOffscreen({
        cmd: 'place', dataUrl: 'data:image/png;base64,' + shot.data, absY: 0 });
      trace.push(`一発撮り dpr=${dpr} k=${k.toFixed(3)} -> ${res.w}x${res.rows} (期待幅 ${want})`);
      if (!res.w || Math.abs(res.w - want) <= 2) break;
      k = k * (want / res.w);          // correct by what actually came back
      await askOffscreen({ cmd: 'begin', width: cssW * scale, height: cssH * scale });
    }
    bands = 1;
    progress(tabId, 1, 1);
    return { cssH, finalCssH, contentH, split, bands, degradedBands };
  }

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

    let totalDev = Math.round(finalCssH * scale);
    const estimate = Math.max(1, Math.ceil(totalDev / Math.round(vp * scale)));

    // Each viewport is placed at the page coordinate it was taken at, so
    // overlaps overwrite the same pixels and nothing can accumulate. Then
    // whatever is still uncovered is captured explicitly, which is what
    // guarantees "no gaps" instead of hoping for it.
    const OVERLAP_CSS = Math.max(40, Math.round(vp * 0.08));
    const stepCss = Math.max(100, vp - OVERLAP_CSS);

    // scroll through the page's OWN scroller (an app that scrolls an inner
    // div does not move at all under window.scrollTo) and wait until it has
    // actually stopped before the shutter opens.
    const settleScroll = (y) => runInPage(tabId, (yy) => {
      const P = window.__PATTISHOT__;
      P.scrollTo(yy);
      return new Promise((res) => {
        let last = -1, same = 0, n = 0;
        const tick = () => {
          const cy = P.scrollY();
          if (Math.abs(cy - last) < 0.5) { if (++same >= 2) return res(cy); }
          else same = 0;
          last = cy;
          if (++n > 90) return res(cy);            // hard cap ~1.5s
          requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      });
    }, [y]);

    // The scroll position is a claim, not a fact: Chrome scrolls on the
    // compositor and the screenshot can come back rendered at an offset the
    // page has not reported yet. Measured in the wild: bands landed 546 CSS px
    // out, which drew content on top of its neighbour and made the same rows
    // appear twice. So every band is checked against what is already assembled,
    // and a band that does not line up is simply re-taken.
    const shootAt = async (yCss, verify) => {
      await settleScroll(yCss);
      const before = await runInPage(tabId, () => window.__PATTISHOT__.scrollY());
      const shot = await sendCmd(tabId, 'Page.captureScreenshot',
        { format: 'png', captureBeyondViewport: false, fromSurface: true });
      const after = await runInPage(tabId, () => window.__PATTISHOT__.scrollY());
      if (Math.abs(after - before) > 0.5) return null;   // moved mid-shot
      const res = await askOffscreen({
        cmd: 'place', dataUrl: 'data:image/png;base64,' + shot.data,
        absY: Math.round(before * scale), limitH: totalDev,
        verify: verify !== false,
      });
      trace.push(`y=${Math.round(yCss)} act=${Math.round(before)} ` +
                 `-> @${res.y} ${res.w}x${res.rows} filled=${res.filled}` +
                 (res.shift ? ` ★ずれ${res.shift}を補正 (err ${(res.err || 0).toFixed(1)}` +
                              ` vs ${(res.at0 || 0).toFixed(1)})` : '') +
                 (res.bad ? ` ★位置が合わない (err ${(res.at0 || 0).toFixed(1)})` : ''));
      if (res.shift) shifted++;
      bands++;
      return res;
    };

    // Take a band; if the pixels disagree with the scroll position, take it
    // again - a compositor that was momentarily behind will have caught up. A
    // band whose position the pixels corrected is already right, so it is kept.
    const shootChecked = async (yCss) => {
      let last = null;
      for (let t = 0; t < 4; t++) {
        const res = await shootAt(yCss);
        if (res) {
          last = res;
          if (!res.bad) return res;          // agreed, or corrected on evidence
        }
        await new Promise((r) => setTimeout(r, 200 + t * 200));
      }
      if (last && last.bad) suspect++;       // never resolved: say so at the end
      return last;
    };

    // walk down, then keep walking for as long as the page gets taller
    let from = 0;
    for (let round = 0; round < 6; round++) {
      for (let y = from; y < finalCssH; y += stepCss) {
        progress(tabId, bands, estimate);
        const res = await shootChecked(y);
        if (res && res.filled >= totalDev) break;
      }
      const m3 = await runInPage(tabId, () => window.__PATTISHOT__.measure());
      const grown = Math.max(1, Math.round(m3.captureHeight));
      if (grown <= finalCssH + 8) break;
      // a list that renders only as it is reached: carry on from where we
      // stopped instead of saving a page that ends in the middle
      trace.push(`撮影中に伸びた: ${finalCssH} -> ${grown} css px`);
      from = Math.max(0, finalCssH - stepCss);
      finalCssH = grown;
      contentH = Math.max(contentH, m3.contentHeight);
      totalDev = Math.round(finalCssH * scale);
    }

    // Anything still uncovered gets captured on purpose (bottom clamping,
    // a scroll that did not land, a page that grew while we walked it).
    for (let pass = 0; pass < 6; pass++) {
      const g = await askOffscreen({ cmd: 'gaps', total: totalDev });
      const gaps = (g.gaps || []).filter(([s, e]) => e - s > 4);
      if (!gaps.length) break;
      trace.push(`未撮影 ${gaps.length}箇所 ${JSON.stringify(gaps.slice(0, 3))} を追撮`);
      for (const [s] of gaps) {
        progress(tabId, bands, estimate);
        await shootChecked(Math.max(0, s / scale - 8));
      }
    }
    const g2 = await askOffscreen({ cmd: 'gaps', total: totalDev });
    degradedBands = (g2.gaps || []).length;         // 0 = fully covered
    trace.push(`${bands}枚 / 位置を補正した帯 ${shifted} / 合わないままの帯 ${suspect} / 未撮影の残り ${degradedBands}箇所`);
  } finally {
    await sendCmd(tabId, 'Emulation.clearDeviceMetricsOverride').catch(() => {});
    await runInPage(tabId, () => window.__PATTISHOT__.scrollTo(0));
  }
  return { cssH, finalCssH, contentH, split, bands, degradedBands, shifted, suspect };
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
