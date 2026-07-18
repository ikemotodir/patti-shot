// PATTI SHOT v2 - background service worker
// 撮影方式:
//   1. ページ全体が出力16,000px以内 → CDP Page.captureScreenshot(captureBeyondViewport)一発撮り
//   2. それ以上 → スクロール+可視領域clip指定の区間分割撮影 → OffscreenCanvasでパート単位に結合
//      (固定/stickyヘッダーは2区間目以降で一時的に無効化し、重複写り込みを防ぐ)
// 画質: 常に2倍解像度。1枚のPNG/PDF1ページに収まらない長さは「複数ファイル/複数ページ分割」で画質を維持する

importScripts("lib/jspdf.min.js");

// 自動スクロール(lazy load読み込み)の下限打ち切り(CSSピクセル)
const MAX_SCROLL_PX = 60000;
// 一発撮りできる出力高さの上限(GPUテクスチャ限界16,384pxの手前)
const ONESHOT_MAX_PX = 16000;
// 1パート(PNG1枚・PDF1ページ)のCSS高さ上限。2倍時30,000pxでcanvas上限32,767pxの手前
const PART_CSS_MAX = 15000;
// 目標解像度倍率
const TARGET_SCALE = 2;

let capturing = false;

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "patti-capture") {
    startCapture(msg.tabId, msg.formats || { png: true, pdf: true })
      .then(sendResponse)
      .catch((e) => sendResponse({ ok: false, error: String((e && e.message) || e) }));
    return true; // 非同期応答
  }
});

function reportProgress(text) {
  try {
    chrome.runtime.sendMessage({ type: "patti-progress", text }).catch(() => {});
  } catch (_) {}
}

function isCapturableUrl(url) {
  if (!url) return false;
  if (!/^https?:\/\//.test(url)) return false;
  if (url.startsWith("https://chromewebstore.google.com")) return false;
  return true;
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// CDPコマンドがハングしてもcapture全体が固まらないよう、常に見張りタイムアウトを付ける
function withTimeout(promise, ms, label) {
  let to;
  const guard = new Promise((_, rej) => {
    to = setTimeout(() => rej(new Error(`処理がタイムアウトしました(${label})`)), ms);
  });
  return Promise.race([promise, guard]).finally(() => clearTimeout(to));
}

function cdp(target, method, params, timeoutMs = 30000) {
  return withTimeout(chrome.debugger.sendCommand(target, method, params), timeoutMs, method);
}

// ページ内でJS式を評価して値を返す
async function evalIn(target, expression, timeoutMs = 30000) {
  const r = await cdp(target, "Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, timeoutMs);
  if (r.exceptionDetails) throw new Error("ページ内スクリプトエラー: " + JSON.stringify(r.exceptionDetails.exception || {}).slice(0, 200));
  return r.result.value;
}

// lazy load画像を読み込ませるため、撮影前にページを1往復自動スクロールする
function autoScroll(target) {
  return evalIn(
    target,
    `(async () => {
      const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
      const el = document.scrollingElement || document.documentElement;
      const step = Math.max(300, Math.floor(window.innerHeight * 0.85));
      let y = 0;
      // scrollHeightは無限スクロールで伸び続けるため、上限 ${MAX_SCROLL_PX}px で打ち切る
      while (y < Math.min(el.scrollHeight, ${MAX_SCROLL_PX})) {
        y += step;
        window.scrollTo({ top: y, left: 0, behavior: "instant" });
        await sleep(110);
      }
      await sleep(500);
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      await sleep(500);
      return el.scrollHeight;
    })()`,
    150000
  );
}

// 表示中の領域の画像読み込みを待つ(分割撮影で下の方のlazy画像対策)
function waitViewportImages(target) {
  return evalIn(
    target,
    `(async () => {
      const vh = window.innerHeight;
      const pending = [...document.querySelectorAll("img")].filter((img) => {
        if (img.complete) return false;
        const r = img.getBoundingClientRect();
        return r.bottom > -200 && r.top < vh + 200;
      });
      if (pending.length === 0) return 0;
      await Promise.race([
        Promise.all(pending.map((img) => new Promise((res) => {
          img.addEventListener("load", res, { once: true });
          img.addEventListener("error", res, { once: true });
        }))),
        new Promise((res) => setTimeout(res, 1500)),
      ]);
      return pending.length;
    })()`,
    5000
  );
}

// 固定/sticky要素を無効化(分割撮影の2区間目以降の重複写り込み防止)。復元情報はページ側に保持
function neutralizeFixedElements(target) {
  return evalIn(
    target,
    `(() => {
      if (window.__pattiRestore) return "already";
      const restore = [];
      for (const el of document.querySelectorAll("body *")) {
        const p = getComputedStyle(el).position;
        if (p === "fixed") {
          restore.push([el, "visibility", el.style.getPropertyValue("visibility"), el.style.getPropertyPriority("visibility")]);
          el.style.setProperty("visibility", "hidden", "important");
        } else if (p === "sticky") {
          restore.push([el, "position", el.style.getPropertyValue("position"), el.style.getPropertyPriority("position")]);
          el.style.setProperty("position", "static", "important");
        }
      }
      window.__pattiRestore = restore;
      return restore.length;
    })()`
  );
}

function restoreFixedElements(target) {
  return evalIn(
    target,
    `(() => {
      const restore = window.__pattiRestore || [];
      for (const [el, prop, val, prio] of restore) {
        if (val) el.style.setProperty(prop, val, prio); else el.style.removeProperty(prop);
      }
      delete window.__pattiRestore;
      return restore.length;
    })()`
  );
}

function timestampParts(d) {
  const p = (n, w = 2) => String(n).padStart(w, "0");
  return {
    date: `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`,
    time: `${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`,
  };
}

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/[^a-zA-Z0-9.-]/g, "-");
  } catch (_) {
    return "page";
  }
}

function download(filename, dataUrl) {
  return new Promise((resolve, reject) => {
    chrome.downloads.download({ url: dataUrl, filename }, (id) => {
      if (chrome.runtime.lastError || id === undefined) {
        reject(new Error(chrome.runtime.lastError ? chrome.runtime.lastError.message : "ダウンロードを開始できません"));
        return;
      }
      const listener = (delta) => {
        if (delta.id !== id) return;
        if (delta.state && delta.state.current === "complete") {
          chrome.downloads.onChanged.removeListener(listener);
          resolve(id);
        } else if (delta.state && delta.state.current === "interrupted") {
          chrome.downloads.onChanged.removeListener(listener);
          reject(new Error("ダウンロードが中断されました"));
        }
      };
      chrome.downloads.onChanged.addListener(listener);
    });
  });
}

function base64ToBlob(b64, type) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type });
}

async function blobToDataUrl(blob) {
  const buf = new Uint8Array(await blob.arrayBuffer());
  let s = "";
  const CH = 0x8000;
  for (let i = 0; i < buf.length; i += CH) {
    s += String.fromCharCode.apply(null, buf.subarray(i, i + CH));
  }
  return "data:" + blob.type + ";base64," + btoa(s);
}

// セグメント画像(base64)群を1パートに結合。PDF用に高品質JPEGも同時生成
async function stitchPart(b64s, wantJpeg, jpegQuality) {
  const bitmaps = [];
  let w = 0;
  let h = 0;
  for (const b64 of b64s) {
    const bmp = await createImageBitmap(base64ToBlob(b64, "image/png"));
    bitmaps.push(bmp);
    w = Math.max(w, bmp.width);
    h += bmp.height;
  }
  const canvas = new OffscreenCanvas(w, h);
  const ctx = canvas.getContext("2d");
  // PDF用JPEGは透過を持てないため白で敷く(PNGでも見た目は変わらない)
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, w, h);
  let y = 0;
  for (const bmp of bitmaps) {
    ctx.drawImage(bmp, 0, y);
    y += bmp.height;
    bmp.close();
  }
  const blob = await canvas.convertToBlob({ type: "image/png" });
  const jpeg = wantJpeg ? await canvas.convertToBlob({ type: "image/jpeg", quality: jpegQuality }) : null;
  return { blob, jpeg, w, h };
}

// 一発撮り(captureBeyondViewport)。出力高さがONESHOT_MAX_PX以内のページ用
async function captureOneShot(target, scale, wantJpeg, jpegQuality) {
  await cdp(target, "Emulation.setDeviceMetricsOverride", { width: 0, height: 0, deviceScaleFactor: scale, mobile: false });
  await sleep(400);
  const shot = await cdp(target, "Page.captureScreenshot", { format: "png", captureBeyondViewport: true }, 120000);
  await cdp(target, "Emulation.clearDeviceMetricsOverride");
  const part = await stitchPart([shot.data], wantJpeg, jpegQuality);
  return { parts: [part], mode: "oneshot", segments: 1 };
}

// 区間分割撮影: スクロールしながら可視領域をclip指定で撮影し、パート単位で逐次結合してメモリを抑える
async function captureSegmented(target, scale, contentH, wantJpeg, jpegQuality) {
  await cdp(target, "Emulation.setDeviceMetricsOverride", { width: 0, height: 0, deviceScaleFactor: scale, mobile: false });
  await sleep(400);
  // DSF変更でスクロールバー幅が変わる場合があるため、clip幅は上書き後に再計測する
  const cssW = await evalIn(target, "document.documentElement.clientWidth");
  const vh = await evalIn(target, "window.innerHeight");
  const total = Math.ceil(contentH / vh);
  const segsPerPart = Math.max(1, Math.floor(PART_CSS_MAX / vh));
  const parts = [];
  let buf = [];
  let neutralized = false;
  try {
    for (let i = 0; i < total; i++) {
      const y = i * vh;
      const h = Math.min(vh, contentH - y);
      if (h <= 0) break;
      if (i === 1) {
        // 1区間目には固定ヘッダーをそのまま写し、2区間目以降は無効化して重複を防ぐ
        await neutralizeFixedElements(target);
        neutralized = true;
      }
      await evalIn(
        target,
        `(async () => {
          window.scrollTo({ top: ${y}, left: 0, behavior: "instant" });
          await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
          return window.scrollY;
        })()`
      );
      await waitViewportImages(target).catch(() => {});
      await sleep(200);
      const shot = await cdp(
        target,
        "Page.captureScreenshot",
        { format: "png", captureBeyondViewport: false, clip: { x: 0, y, width: cssW, height: h, scale: 1 } },
        60000
      );
      buf.push(shot.data);
      reportProgress(`撮影中… (${i + 1}/${total})`);
      if (buf.length >= segsPerPart || i === total - 1) {
        reportProgress(`画像を結合中… (パート${parts.length + 1})`);
        parts.push(await stitchPart(buf, wantJpeg, jpegQuality));
        buf = [];
      }
    }
  } finally {
    if (neutralized) await restoreFixedElements(target).catch(() => {});
    await cdp(target, "Emulation.clearDeviceMetricsOverride").catch(() => {});
    await evalIn(target, `window.scrollTo({ top: 0, left: 0, behavior: "instant" }); 0`).catch(() => {});
  }
  return { parts, mode: "segmented", segments: total };
}

// PDF生成: 基本は見た目そのままの縦長1ページ。パートが複数ある場合のみ複数ページに分割
async function buildPdf(parts, scale) {
  const { jsPDF } = self.jspdf;
  let doc = null;
  for (let i = 0; i < parts.length; i++) {
    reportProgress(`PDF作成中… (${i + 1}/${parts.length})`);
    const part = parts[i];
    const bytes = new Uint8Array(await (part.jpeg || part.blob).arrayBuffer());
    // 1css px = 0.75pt(=96dpi相当)でページを作り、2倍解像度画像を等倍配置 → ズームしても文字が読める
    const wPt = (part.w / scale) * 0.75;
    const hPt = (part.h / scale) * 0.75;
    const orientation = wPt > hPt ? "l" : "p";
    if (!doc) doc = new jsPDF({ unit: "pt", format: [wPt, hPt], orientation, compress: true });
    else doc.addPage([wPt, hPt], orientation);
    doc.addImage(bytes, part.jpeg ? "JPEG" : "PNG", 0, 0, wPt, hPt);
  }
  return doc.output("blob");
}

// メイン撮影処理。テストハーネスからも直接呼べるようトップレベル関数にしている
async function startCapture(tabId, formats) {
  if (capturing) {
    return { ok: false, busy: true, error: "撮影中です。完了までお待ちください。" };
  }
  capturing = true;
  const target = { tabId };
  let attached = false;
  try {
    const tab = await chrome.tabs.get(tabId);
    if (!isCapturableUrl(tab.url)) {
      return { ok: false, unsupported: true, error: "このページは撮影できません" };
    }
    const wantPng = formats.png !== false;
    const wantPdf = formats.pdf !== false;
    if (!wantPng && !wantPdf) {
      return { ok: false, error: "保存形式(PNG/PDF)を選んでください" };
    }

    await withTimeout(chrome.debugger.attach(target, "1.3"), 10000, "attach");
    attached = true;
    await cdp(target, "Page.enable");

    reportProgress("ページ読み込み中…");
    await autoScroll(target);

    reportProgress("撮影中…");
    const metrics = await cdp(target, "Page.getLayoutMetrics");
    const content = metrics.cssContentSize || metrics.contentSize;
    const contentH = Math.ceil(content.height);
    const cssW = await evalIn(target, "document.documentElement.clientWidth");

    const scale = TARGET_SCALE;
    const jpegQuality = contentH > 30000 ? 0.9 : 0.95;
    let result;
    if (contentH * scale <= ONESHOT_MAX_PX) {
      result = await captureOneShot(target, scale, wantPdf, jpegQuality);
    } else {
      result = await captureSegmented(target, scale, contentH, wantPdf, jpegQuality);
    }
    const parts = result.parts;

    const t = timestampParts(new Date());
    const base = `PATTISHOT_${hostOf(tab.url)}_${t.date}_${t.time}`;
    const files = [];
    const notes = [];

    if (wantPng) {
      reportProgress("PNGを保存中…");
      for (let i = 0; i < parts.length; i++) {
        const name = parts.length === 1 ? `${base}.png` : `${base}_${i + 1}.png`;
        await withTimeout(download(name, await blobToDataUrl(parts[i].blob)), 120000, "PNG保存");
        files.push(name);
      }
      if (parts.length > 1) notes.push(`ページが長いためPNGを${parts.length}枚に分割保存しました(画質維持のため)`);
    }

    if (wantPdf) {
      const pdfBlob = await buildPdf(parts, scale);
      reportProgress("PDFを保存中…");
      const name = `${base}.pdf`;
      await withTimeout(download(name, await blobToDataUrl(pdfBlob)), 120000, "PDF保存");
      files.push(name);
      if (parts.length > 1) notes.push(`PDFは${parts.length}ページに分割しました`);
    }

    const note = notes.join(" / ");
    reportProgress("保存完了！" + (note ? `（${note}）` : ""));
    return {
      ok: true,
      files,
      mode: result.mode,
      segments: result.segments,
      parts: parts.length,
      partDims: parts.map((p) => ({ w: p.w, h: p.h })),
      cssWidth: cssW,
      cssHeight: contentH,
      scale,
      note,
    };
  } catch (e) {
    return { ok: false, error: String((e && e.message) || e) };
  } finally {
    capturing = false;
    if (attached) {
      // 「デバッグ中」バナーを残さないよう必ずデタッチする
      try {
        await chrome.debugger.detach(target);
      } catch (_) {}
    }
  }
}
