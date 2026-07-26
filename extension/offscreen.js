// PATTI SHOT - image assembly (port of the verified imaging.py / output.py).
//
// Very long pages are the whole point of this tool, so nothing here may assume
// the finished image fits in one canvas. Measured: J-PlatPat 商品･役務名検索 is
// 48,469 CSS px tall, i.e. 96,938 px at 2x -- past Chrome's 65,535 px canvas
// limit, where OffscreenCanvas silently comes back zero-sized ("The size of
// OffscreenCanvas is zero").
//
// So captured bands are kept as compressed PNG blobs and only the piece being
// written out is ever decoded onto a canvas:
//   * PDF - one page per <=14,400pt slice, composed and encoded page by page
//   * PNG - a single file when it fits, otherwise numbered parts
// Memory stays bounded however long the page is.

const BAND_PX = 100;            // scan band height, CSS px
const BLANK_RATIO = 0.995;
const BLANK_RUN_PX = 300;       // CSS px
const PDF_PAGE_MAX_CSS = 19000; // 14,400pt limit with margin

// measured on this engine: 2560x65535 encodes fine (167 Mpx), 2560x70000 and
// 1280x96938 fail -- the binding limit is the 65,535 px side, not the area.
const MAX_DIM = 65000;          // small margin under 65,535
const MAX_AREA = 200e6;

let W = 0, H = 0;
let bands = [];                 // {blob, y, h} in device px
let urls = [];
let cleanupTimer = null;
let filled = 0;                 // rows assembled so far
let covered = [];               // [start,end) device rows already placed

function begin(width, height) {
  if (cleanupTimer) { clearTimeout(cleanupTimer); cleanupTimer = null; }
  W = width; H = height;
  bands = [];
  urls = [];
  filled = 0;
  covered = [];
}

/**
 * Place a capture at an ABSOLUTE position in the page.
 *
 * `absY` is round(scrollY * scale): the row of the full image where this
 * viewport begins. Overlaps simply overwrite the same content, so a row can
 * never appear twice however the scroll behaves, and nothing accumulates - an
 * odd capture cannot shift everything after it.
 *
 * Matching pixels was tried instead and does not survive real pages: a table of
 * hundreds of near-identical rows (J-PlatPat) matches at the wrong row, which
 * skipped rows 21..62, and flat colour bands match anywhere, which duplicated
 * 130 rows per join. Absolute placement has neither failure mode.
 */
async function placeBand(dataUrl, absY, limitH) {
  const blob = await (await fetch(dataUrl)).blob();
  const bmp = await createImageBitmap(blob);
  const bw = bmp.width;
  let bh = bmp.height;
  let srcY = 0;
  let y = Math.max(0, Math.round(absY || 0));
  if (absY < 0) { srcY = -Math.round(absY); bh -= srcY; y = 0; }
  if (limitH && y + bh > limitH) bh = limitH - y;
  if (bh <= 0) { bmp.close(); return { rows: 0 }; }

  let outBlob;
  if (srcY === 0 && bh === bmp.height) {
    outBlob = blob;
    bmp.close();
  } else {
    const c = new OffscreenCanvas(bw, bh);
    c.getContext('2d').drawImage(bmp, 0, srcY, bw, bh, 0, 0, bw, bh);
    bmp.close();
    outBlob = await c.convertToBlob({ type: 'image/png' });
  }
  bands.push({ blob: outBlob, y, h: bh });
  W = bw;
  covered.push([y, y + bh]);
  filled = Math.max(filled, y + bh);
  // `w` lets the caller check the capture really came back at the scale it
  // asked for instead of assuming it did
  return { rows: bh, y, w: bw, filled, gaps: gapList(limitH || filled) };
}

// merged coverage gaps inside [0, total)
function gapList(total) {
  const iv = covered.slice().sort((a, b) => a[0] - b[0]);
  const gaps = [];
  let at = 0;
  for (const [s, e] of iv) {
    if (s > at) gaps.push([at, Math.min(s, total)]);
    at = Math.max(at, e);
    if (at >= total) break;
  }
  if (at < total) gaps.push([at, total]);
  return gaps.filter(([s, e]) => e - s > 2);
}

// compose [y0, y1) of the full image onto a canvas, optionally scaled by `k`
// (used to fit a very long page into one image instead of splitting it)
async function compose(y0, y1, k) {
  k = k || 1;
  const h = Math.max(1, Math.round((y1 - y0) * k));
  const w = Math.max(1, Math.round(W * k));
  const c = new OffscreenCanvas(w, h);
  const cx = c.getContext('2d', { willReadFrequently: true });
  cx.imageSmoothingQuality = 'high';
  cx.fillStyle = '#ffffff';
  cx.fillRect(0, 0, w, h);
  for (const b of bands) {
    if (b.y + b.h <= y0 || b.y >= y1) continue;
    const bmp = await createImageBitmap(b.blob);
    const srcY = Math.max(0, y0 - b.y);
    const dstY = Math.max(0, b.y - y0);
    const rows = Math.min(b.h - srcY, y1 - (b.y + srcY));
    if (rows > 0) {
      cx.drawImage(bmp, 0, srcY, bmp.width, rows,
                   0, Math.round(dstY * k), w, Math.round(rows * k));
    }
    bmp.close();
  }
  return { canvas: c, ctx: cx };
}

function release(canvas) { canvas.width = 1; canvas.height = 1; }

function rowUniform(data, w, row) {
  const o = row * w * 4;
  const r = data[o], g = data[o + 1], b = data[o + 2];
  for (let x = 1; x < w; x++) {
    const i = o + x * 4;
    if (data[i] !== r || data[i + 1] !== g || data[i + 2] !== b) return false;
  }
  return true;
}

// how many trailing uniform rows to cut (insurance for measurement overrun)
async function trailingTrim(maxTrim) {
  if (!maxTrim || maxTrim <= 0) return 0;
  const look = Math.min(H, maxTrim + 64);
  const { canvas, ctx } = await compose(H - look, H);
  const img = ctx.getImageData(0, 0, W, look).data;
  let uniform = 0;
  for (let y = look - 1; y >= 0; y--) {
    if (!rowUniform(img, W, y)) break;
    uniform++;
  }
  release(canvas);
  return Math.max(0, Math.min(uniform - 8, maxTrim));
}

// blank runs, measured in CSS px so the threshold is resolution independent
async function blankRuns(height, scale) {
  const bandDev = Math.max(1, Math.round(BAND_PX * scale));
  const runThreshold = BLANK_RUN_PX * scale;
  const CHUNK = Math.max(bandDev * 4, Math.min(MAX_DIM, Math.floor(MAX_AREA / Math.max(1, W))));
  const runs = [];
  let runStart = null, runEnd = 0;

  for (let base = 0; base < height; base += CHUNK) {
    const top = base, bottom = Math.min(base + CHUNK, height);
    const { canvas, ctx } = await compose(top, bottom);
    for (let y = 0; y < bottom - top; y += bandDev) {
      const hh = Math.min(bandDev, (bottom - top) - y);
      if (hh <= 0) break;
      const img = ctx.getImageData(0, y, W, hh).data;
      const counts = new Map();
      let best = 0, seen = 0;
      const total = W * hh;
      const step = Math.max(1, Math.floor(total / 20000));
      for (let p = 0; p < total; p += step) {
        const i = p * 4;
        const key = (img[i] << 16) | (img[i + 1] << 8) | img[i + 2];
        const c = (counts.get(key) || 0) + 1;
        counts.set(key, c);
        if (c > best) best = c;
        seen++;
      }
      const isBlank = seen > 0 && best / seen >= BLANK_RATIO;
      const absY = top + y;
      if (isBlank) {
        if (runStart === null) runStart = absY;
        runEnd = absY + hh;
      } else {
        if (runStart !== null && runEnd - runStart >= runThreshold) runs.push([runStart, runEnd]);
        runStart = null;
      }
    }
    release(canvas);
  }
  if (runStart !== null && runEnd - runStart >= runThreshold) runs.push([runStart, runEnd]);
  return runs;
}

// a whitespace row near `target`, so a page break never cuts through text
async function findSplitRow(target, search) {
  const top = Math.max(0, target - search);
  const bottom = Math.min(H, target + 1);
  if (bottom <= top) return target;
  const { canvas, ctx } = await compose(top, bottom);
  const img = ctx.getImageData(0, 0, W, bottom - top).data;
  let found = target;
  for (let y = (bottom - top) - 1; y >= 0; y--) {
    if (rowUniform(img, W, y)) { found = top + y; break; }
  }
  release(canvas);
  return found;
}

function chunkHeight() {
  return Math.max(2000, Math.min(MAX_DIM, Math.floor(MAX_AREA / Math.max(1, W))));
}

async function sliceRanges(limit, searchPx) {
  const ranges = [];
  let y = 0;
  while (y < H) {
    let end = Math.min(y + limit, H);
    if (end < H) {
      const sr = await findSplitRow(end, searchPx);
      if (sr > y + limit * 0.5) end = sr;
    }
    ranges.push([y, end]);
    y = end;
  }
  return ranges;
}

async function finish(fmt, scale, maxTrim, base) {
  // the assembled height is what actually got stitched, not what was predicted
  if (filled > 0) H = filled;
  const trim = await trailingTrim(maxTrim);
  H = Math.max(1, H - trim);

  const runs = await blankRuns(H, scale);
  const files = [];
  const limit = chunkHeight();
  let pngParts = 1;

  let pngScaleUsed = scale;
  if (fmt === 'png' || fmt === 'both') {
    // Spec order for a page too tall for one image: keep one file by scaling it
    // down, and only split when even 1x would not fit.
    const fitK = Math.min(1, limit / H, Math.sqrt(MAX_AREA / Math.max(1, W * H)));
    const canFitOne = H <= limit && W * H <= MAX_AREA;
    const downscaleOk = fitK * scale >= 1;      // never go below 1x of the page

    if (canFitOne || downscaleOk) {
      const k = canFitOne ? 1 : fitK;
      const { canvas } = await compose(0, H, k);
      const url = URL.createObjectURL(await canvas.convertToBlob({ type: 'image/png' }));
      release(canvas);
      urls.push(url);
      files.push({ url, name: base + '.png' });
      pngScaleUsed = scale * k;
    } else {
      const ranges = await sliceRanges(limit, Math.round(300 * scale));
      pngParts = ranges.length;
      let i = 1;
      for (const [a, b] of ranges) {
        const { canvas } = await compose(a, b);
        const url = URL.createObjectURL(await canvas.convertToBlob({ type: 'image/png' }));
        release(canvas);
        urls.push(url);
        files.push({ url, name: `${base}_${i}.png` });
        i++;
      }
    }
  }

  if (fmt === 'pdf' || fmt === 'both') {
    const { jsPDF } = self.jspdf;
    const pageMax = Math.min(Math.round(PDF_PAGE_MAX_CSS * scale), limit);
    const ranges = await sliceRanges(pageMax, Math.round(200 * scale));
    let pdf = null;
    for (const [a, b] of ranges) {
      const hCss = (b - a) / scale, wCss = W / scale;
      const ptW = wCss * 0.75, ptH = hCss * 0.75;   // css px -> pt
      if (!pdf) pdf = new jsPDF({ unit: 'pt', format: [ptW, ptH], orientation: ptW > ptH ? 'l' : 'p' });
      else pdf.addPage([ptW, ptH], ptW > ptH ? 'l' : 'p');
      const { canvas } = await compose(a, b);
      const blob = await canvas.convertToBlob({ type: 'image/png' });
      release(canvas);
      const dataUrl = await new Promise((res) => {
        const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(blob);
      });
      pdf.addImage(dataUrl, 'PNG', 0, 0, ptW, ptH, undefined, 'FAST');
    }
    const url = URL.createObjectURL(pdf.output('blob'));
    urls.push(url);
    files.push({ url, name: base + '.pdf' });
  }

  return {
    files, blankRuns: runs, width: W, height: H, trimmed: trim, pngParts,
    pngScale: Math.round(pngScaleUsed * 100) / 100,
  };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.target !== 'offscreen') return;
  (async () => {
    try {
      if (msg.cmd === 'begin') { begin(msg.width, msg.height); sendResponse({ ok: true }); }
      else if (msg.cmd === 'place') sendResponse(await placeBand(msg.dataUrl, msg.absY, msg.limitH));
      else if (msg.cmd === 'gaps') sendResponse({ gaps: gapList(msg.total || filled), filled });
      else if (msg.cmd === 'finish') sendResponse(await finish(msg.fmt, msg.scale, msg.maxTrim, msg.base));
      else if (msg.cmd === 'cleanup') {
        // release the blobs a little later: the downloads still read them
        if (cleanupTimer) clearTimeout(cleanupTimer);
        const mine = urls.slice();
        urls = [];
        bands = [];
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
