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
// --- placement verification -------------------------------------------------
// The first version of this check sampled ONE pixel every ~60 px and averaged
// the differences. That is mathematically blind to rows whose only difference
// is something small: a wrong No. cell moves the mean by ~1.5 against a
// threshold of 14. J-PlatPat's rows are exactly that, so a misplaced band
// sailed straight through "verification" - no correction, no warning, and the
// duplicated numbers stayed. This version samples densely and counts the
// clearly-different samples instead of averaging, so one wrong number in an
// otherwise identical row is enough to reject a position.
const VERIFY_RANGE = 1600;      // device px searched either way
const V_THRESH = 28;            // per-sample "different ink" threshold
const V_EDGE_L = 4;             // skip the anti-aliased left edge
const V_EDGE_R = 44;            // skip the scrollbar: its thumb moves per shot

function greyStrip(data, w, h, colStep) {
  const x0 = Math.min(V_EDGE_L, Math.max(0, w - 2));
  const x1 = Math.max(x0 + 1, w - V_EDGE_R);
  const cols = Math.max(1, Math.floor((x1 - x0) / colStep));
  const g = new Uint8Array(h * cols);
  const ink = new Uint8Array(h);          // row carries any contrast at all
  for (let y = 0; y < h; y++) {
    const o = y * w * 4;
    let mn = 255, mx = 0;
    for (let c = 0; c < cols; c++) {
      const i = o + (x0 + c * colStep) * 4;
      const v = (data[i] * 77 + data[i + 1] * 151 + data[i + 2] * 28) >> 8;
      g[y * cols + c] = v;
      if (v < mn) mn = v;
      if (v > mx) mx = v;
    }
    ink[y] = (mx - mn) > 24 ? 1 : 0;
  }
  return { g, cols, rows: h, ink };
}

// fraction of ROWS that clearly disagree when the band is placed at y+s.
// A is the assembled image from winTop down; B is the band.
//
// Counted per row, not per sample: a wrong 3-digit number is ~10 samples out
// of ~1000 in its row, which any whole-image average buries. But those 10
// samples make that ROW unmistakably wrong, and a misplaced band turns every
// number row into a wrong row - a signal no averaging can hide. At the correct
// position both images come off the same device pixel grid, so a healthy row
// has zero clearly-different samples.
const ROW_BAD = 5;             // samples over V_THRESH that condemn a row
function fracAt(A, winTop, B, y, s, rowStride) {
  const cols = Math.min(A.cols, B.cols);
  const lo = Math.max(winTop, y + s);
  const hi = Math.min(winTop + A.rows, y + s + B.rows);
  if (hi - lo < 200) return 1;
  let badRows = 0, rows = 0;
  for (let ar = lo; ar < hi; ar += rowStride) {
    const ra = ar - winTop, rb = ar - y - s;
    rows++;
    // two blank rows can never disagree - and most of a page is blank rows,
    // so this one skip is what makes trying every offset affordable
    if (!A.ink[ra] && !B.ink[rb]) continue;
    const oa = ra * A.cols;
    const ob = rb * B.cols;
    let bad = 0;
    for (let c = 0; c < cols; c++) {
      const d = A.g[oa + c] - B.g[ob + c];
      if (d > V_THRESH || d < -V_THRESH) { if (++bad >= ROW_BAD) break; }
    }
    if (bad >= ROW_BAD) badRows++;
  }
  return rows ? badRows / rows : 1;
}

async function bandStrip(bmp, rows) {
  const h = Math.max(1, Math.min(bmp.height, Math.round(rows)));
  const c = new OffscreenCanvas(bmp.width, h);
  const cx = c.getContext('2d', { willReadFrequently: true });
  cx.drawImage(bmp, 0, 0);
  const s = greyStrip(cx.getImageData(0, 0, bmp.width, h).data, bmp.width, h, 4);
  release(c);
  return s;
}

async function assembledStrip(top, bottom) {
  const { canvas, ctx } = await compose(top, bottom);
  const s = greyStrip(ctx.getImageData(0, 0, W, bottom - top).data, W, bottom - top, 4);
  release(canvas);
  return s;
}

/**
 * Where does this capture ACTUALLY belong?
 *
 * The scroll position says where it should be, but the screenshot comes from
 * the compositor and the scroll offset it rendered at can differ from the one
 * the page reports - Chrome scrolls off the main thread. Measured in the wild:
 * whole bands landed 546 CSS px off, which drew content over its own neighbour
 * and printed the same row numbers twice.
 *
 * So the pixels get a veto. The scroll-derived position is kept unless the
 * picture clearly rejects it AND clearly prefers exactly one other position -
 * on a page of near-identical rows a wrong row can also look plausible, and
 * moving a band on weak evidence is how the old matcher skipped rows 21..62.
 */
async function verifyShift(bmp, y) {
  const avail = filled - y;
  if (avail < 240) return { shift: 0, checked: false };
  // The window must cover every candidate: a shift of +s compares assembled
  // rows around y+s, so capping the window at y+900 made every position
  // beyond that "unprovable" - the check then SAW an 82% mismatch but could
  // not say where the band belonged, and the wrong placement stood.
  const winTop = Math.max(0, y - VERIFY_RANGE);
  const winBot = Math.min(filled, y + VERIFY_RANGE + 900);
  const A = await assembledStrip(winTop, winBot);
  const B = await bandStrip(bmp, (winBot - y) + VERIFY_RANGE + 8);

  const f0 = fracAt(A, winTop, B, y, 0, 1);
  if (f0 < 0.004) return { shift: 0, f0, err: f0, checked: true };

  // The valley at the true position is 1-2 px wide - both images sit on the
  // same device pixel grid, so being off by even 1 px lights up every ink
  // edge. A strided search steps clean over it (measured: step 6 missed the
  // real +1092 every time). So EVERY offset is tried, but on a thin sample of
  // rows first; only the promising few get the full comparison.
  const est = new Float32Array(2 * VERIFY_RANGE + 1);
  const order = [];
  for (let s = -VERIFY_RANGE; s <= VERIFY_RANGE; s++) {
    est[s + VERIFY_RANGE] = fracAt(A, winTop, B, y, s, 24);
    order.push(s);
  }
  order.sort((a, b) => est[a + VERIFY_RANGE] - est[b + VERIFY_RANGE]);
  let sBest = 0, fBest = f0;
  for (const s of order.slice(0, 32)) {
    const f = fracAt(A, winTop, B, y, s, 4);
    if (f < fBest) { fBest = f; sBest = s; }
  }
  let s2 = sBest, f2 = 1;
  for (let s = sBest - 3; s <= sBest + 3; s++) {
    const f = fracAt(A, winTop, B, y, s, 1);
    if (f < f2) { f2 = f; s2 = s; }
  }
  sBest = s2; fBest = f2;
  let second = 1;
  for (const s of order) {
    if (Math.abs(s - sBest) <= 12) continue;
    if (est[s + VERIFY_RANGE] < second) second = est[s + VERIFY_RANGE];
  }
  for (const s of order.filter((v) => Math.abs(v - sBest) > 12).slice(0, 8)) {
    const f = fracAt(A, winTop, B, y, s, 8);
    if (f < second) second = f;
  }
  const decided = Math.abs(sBest) > 2 && fBest < 0.003 &&
                  f0 > Math.max(0.02, fBest * 6) && fBest < second * 0.35;
  return {
    shift: decided ? sBest : 0, f0, err: decided ? fBest : f0,
    sBest, fBest, second,
    checked: true, decided,
    // provably wrong but with no provable home: the caller must retake
    bad: !decided && f0 >= 0.02,
  };
}

// Are two back-to-back captures of the same viewport the same picture?
// If they differ, the surface was still changing when the shutter opened -
// that frame cannot be trusted no matter where it would be placed.
async function sameShot(urlA, urlB) {
  const [bmpA, bmpB] = await Promise.all([
    (async () => createImageBitmap(await (await fetch(urlA)).blob()))(),
    (async () => createImageBitmap(await (await fetch(urlB)).blob()))(),
  ]);
  if (bmpA.width !== bmpB.width || bmpA.height !== bmpB.height) {
    bmpA.close(); bmpB.close();
    return { same: false, why: 'size' };
  }
  const A = await bandStrip(bmpA, bmpA.height);
  const B = await bandStrip(bmpB, bmpB.height);
  bmpA.close(); bmpB.close();
  const frac = fracAt(A, 0, B, 0, 0, 4);
  return { same: frac < 0.002, frac };
}

// The final self-check: a FRESH capture is compared against what was assembled
// at that position. If every checked spot matches a fresh photograph of the
// page, the saved image is the page.
async function qaCompare(dataUrl, absY) {
  const blob = await (await fetch(dataUrl)).blob();
  const bmp = await createImageBitmap(blob);
  const y = Math.max(0, Math.round(absY || 0));
  const cmp = Math.min(bmp.height, filled - y, 1600);
  if (cmp < 400) { bmp.close(); return { ok: true, skipped: true, frac: -1 }; }
  const A = await assembledStrip(y, y + cmp);
  const B = await bandStrip(bmp, cmp);
  bmp.close();
  const frac = fracAt(A, y, B, y, 0, 2);
  return { ok: frac < 0.006, frac };
}

async function placeBand(dataUrl, absY, limitH, verify, force) {
  const blob = await (await fetch(dataUrl)).blob();
  const bmp = await createImageBitmap(blob);
  const bw = bmp.width;
  let bh = bmp.height;
  let srcY = 0;
  let y = Math.max(0, Math.round(absY || 0));
  let check = { shift: 0, err: -1, checked: false };
  if (verify && covered.length && y < filled) {
    check = await verifyShift(bmp, y);
    // A band the pixels reject with no provable home is retaken, not placed:
    // placing it can poison later comparisons. But only while retakes remain -
    // on the FINAL attempt it goes in at the scroll position regardless,
    // because a white hole in the middle of the page is strictly worse than
    // an imperfect band, and the QA pass still gets to inspect the result.
    if (check.bad && !force) {
      bmp.close();
      return { rows: 0, y, w: bw, rejected: true, bad: true,
               err: check.err, at0: check.f0, sBest: check.sBest,
               fBest: check.fBest, second: check.second,
               filled, gaps: gapList(limitH || filled) };
    }
    y = Math.max(0, y + check.shift);
  }
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
  // asked for instead of assuming it did; `shift` says whether the scroll
  // position had to be overruled by the pixels
  return { rows: bh, y, w: bw, filled, shift: check.shift, err: check.err,
           at0: check.f0, bad: !!check.bad, gaps: gapList(limitH || filled) };
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
      else if (msg.cmd === 'place') sendResponse(await placeBand(msg.dataUrl, msg.absY, msg.limitH, msg.verify, msg.force));
      else if (msg.cmd === 'gaps') sendResponse({ gaps: gapList(msg.total || filled), filled });
      else if (msg.cmd === 'qa') sendResponse(await qaCompare(msg.dataUrl, msg.absY));
      else if (msg.cmd === 'same') sendResponse(await sameShot(msg.a, msg.b));
      else if (msg.cmd === 'logurl') {
        // Chrome ignores the filename for data: downloads, so the log becomes
        // an anonymous download.txt - a blob URL keeps the proper name
        const u = URL.createObjectURL(new Blob([msg.text || ''], { type: 'text/plain' }));
        urls.push(u);
        sendResponse({ url: u });
      }
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
