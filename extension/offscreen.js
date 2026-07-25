// PATTI SHOT - image assembly (port of the verified imaging.py / output.py).
//
//   * stitch the captured bands into one tall canvas
//   * trim the trailing uniform-colour band (measurement-overrun insurance)
//   * blank-band detection (a single colour covering >=99.5% of a 100 CSS px
//     band, for >=300 CSS px in a row) so a broken capture is reported
//   * PNG, and PDF split at the 14,400pt page limit on whitespace rows

const BAND_PX = 100;          // scan band height, CSS px
const BLANK_RATIO = 0.995;
const BLANK_RUN_PX = 300;     // CSS px
const PDF_PAGE_MAX_CSS = 19000;

let canvas = null, ctx = null, scaleUsed = 2, urls = [];
let cleanupTimer = null;

function begin(width, height) {
  // a cleanup scheduled by the previous capture must not wipe this one's canvas
  if (cleanupTimer) { clearTimeout(cleanupTimer); cleanupTimer = null; }
  canvas = new OffscreenCanvas(width, height);
  ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, width, height);
  urls.forEach((u) => URL.revokeObjectURL(u));
  urls = [];
}

async function band(dataUrl, y, topCrop, maxRows) {
  const blob = await (await fetch(dataUrl)).blob();
  const bmp = await createImageBitmap(blob);
  const crop = Math.max(0, topCrop || 0);
  let rows = bmp.height - crop;
  if (maxRows != null) rows = Math.min(rows, maxRows);
  if (rows <= 0) { bmp.close(); return { rows: 0 }; }
  ctx.drawImage(bmp, 0, crop, bmp.width, rows, 0, y, bmp.width, rows);
  bmp.close();
  return { rows };
}

function rowIsUniform(data, w, row) {
  const o = row * w * 4;
  const r = data[o], g = data[o + 1], b = data[o + 2];
  for (let x = 1; x < w; x++) {
    const i = o + x * 4;
    if (data[i] !== r || data[i + 1] !== g || data[i + 2] !== b) return false;
  }
  return true;
}

// trailing uniform rows -> how many to cut (never more than maxTrim)
function trailingTrim(h, w, maxTrim) {
  const keep = 8;
  let uniform = 0;
  for (let y = h - 1; y >= 0; y--) {
    const row = ctx.getImageData(0, y, w, 1).data;
    let same = true;
    const r = row[0], g = row[1], b = row[2];
    for (let x = 1; x < w; x++) {
      const i = x * 4;
      if (row[i] !== r || row[i + 1] !== g || row[i + 2] !== b) { same = false; break; }
    }
    if (!same) break;
    uniform++;
    if (uniform > maxTrim + keep) break;
  }
  return Math.max(0, Math.min(uniform - keep, maxTrim));
}

// blank runs, measured in CSS px so the threshold is resolution independent
function blankRuns(h, w, scale) {
  const bandDev = Math.max(1, Math.round(BAND_PX * scale));
  const runThreshold = BLANK_RUN_PX * scale;
  const runs = [];
  let runStart = null, runEnd = 0;
  for (let y = 0; y < h; y += bandDev) {
    const hh = Math.min(bandDev, h - y);
    const img = ctx.getImageData(0, y, w, hh).data;
    const counts = new Map();
    let best = 0;
    const total = w * hh;
    const step = Math.max(1, Math.floor(total / 20000));     // sample big bands
    let seen = 0;
    for (let p = 0; p < total; p += step) {
      const i = p * 4;
      const key = (img[i] << 16) | (img[i + 1] << 8) | img[i + 2];
      const c = (counts.get(key) || 0) + 1;
      counts.set(key, c);
      if (c > best) best = c;
      seen++;
    }
    const isBlank = seen > 0 && best / seen >= BLANK_RATIO;
    if (isBlank) {
      if (runStart === null) runStart = y;
      runEnd = y + hh;
    } else {
      if (runStart !== null && runEnd - runStart >= runThreshold) runs.push([runStart, runEnd]);
      runStart = null;
    }
  }
  if (runStart !== null && runEnd - runStart >= runThreshold) runs.push([runStart, runEnd]);
  return runs;
}

function findSplitRow(target, w, search) {
  for (let y = target; y > Math.max(1, target - search); y--) {
    const row = ctx.getImageData(0, y, w, 1).data;
    let same = true;
    const r = row[0], g = row[1], b = row[2];
    for (let x = 1; x < w; x++) {
      const i = x * 4;
      if (row[i] !== r || row[i + 1] !== g || row[i + 2] !== b) { same = false; break; }
    }
    if (same) return y;
  }
  return target;
}

async function sliceBlob(y0, y1) {
  const w = canvas.width;
  const c = new OffscreenCanvas(w, y1 - y0);
  c.getContext('2d').drawImage(canvas, 0, y0, w, y1 - y0, 0, 0, w, y1 - y0);
  return await c.convertToBlob({ type: 'image/png' });
}

async function finish(fmt, scale, maxTrim, base) {
  scaleUsed = scale;
  const w = canvas.width;
  const trim = trailingTrim(canvas.height, w, maxTrim || 0);
  if (trim > 0) {
    const c = new OffscreenCanvas(w, canvas.height - trim);
    c.getContext('2d').drawImage(canvas, 0, 0);
    canvas = c;
    ctx = canvas.getContext('2d', { willReadFrequently: true });
  }
  const runs = blankRuns(canvas.height, w, scale);
  const files = [];

  if (fmt === 'png' || fmt === 'both') {
    const blob = await canvas.convertToBlob({ type: 'image/png' });
    const url = URL.createObjectURL(blob);
    urls.push(url);
    files.push({ url, name: base + '.png' });
  }

  if (fmt === 'pdf' || fmt === 'both') {
    const { jsPDF } = self.jspdf;
    const pageMaxDev = Math.round(PDF_PAGE_MAX_CSS * scale);
    const pages = [];
    let y = 0;
    while (y < canvas.height) {
      let target = Math.min(y + pageMaxDev, canvas.height);
      if (target < canvas.height) {
        target = findSplitRow(target, w, Math.round(200 * scale));
        if (target <= y) target = Math.min(y + pageMaxDev, canvas.height);
      }
      pages.push([y, target]);
      y = target;
    }
    let pdf = null;
    for (const [a, b] of pages) {
      const hCss = (b - a) / scale, wCss = w / scale;
      const ptW = wCss * 0.75, ptH = hCss * 0.75;      // css px -> pt
      if (!pdf) pdf = new jsPDF({ unit: 'pt', format: [ptW, ptH],
                                  orientation: ptW > ptH ? 'l' : 'p' });
      else pdf.addPage([ptW, ptH], ptW > ptH ? 'l' : 'p');
      const blob = await sliceBlob(a, b);
      const dataUrl = await new Promise((res) => {
        const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(blob);
      });
      pdf.addImage(dataUrl, 'PNG', 0, 0, ptW, ptH, undefined, 'FAST');
    }
    const url = URL.createObjectURL(pdf.output('blob'));
    urls.push(url);
    files.push({ url, name: base + '.pdf' });
  }

  return { files, blankRuns: runs, width: w, height: canvas.height, trimmed: trim };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.target !== 'offscreen') return;
  (async () => {
    try {
      if (msg.cmd === 'begin') { begin(msg.width, msg.height); sendResponse({ ok: true }); }
      else if (msg.cmd === 'band') sendResponse(await band(msg.dataUrl, msg.y, msg.topCrop, msg.maxRows));
      else if (msg.cmd === 'finish') sendResponse(await finish(msg.fmt, msg.scale, msg.maxTrim, msg.base));
      else if (msg.cmd === 'cleanup') {
        // give the downloads time to read the blobs, then release them. The
        // canvas is left alone: the next capture replaces it in begin().
        if (cleanupTimer) clearTimeout(cleanupTimer);
        const mine = urls.slice();
        urls = [];
        cleanupTimer = setTimeout(() => {
          mine.forEach((u) => URL.revokeObjectURL(u));
          cleanupTimer = null;
        }, 20000);
        sendResponse({ ok: true });
      } else sendResponse({ error: 'unknown cmd' });
    } catch (e) {
      sendResponse({ error: String((e && e.message) || e) });
    }
  })();
  return true;
});
