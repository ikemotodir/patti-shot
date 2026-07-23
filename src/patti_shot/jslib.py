"""Browser-side logic injected into every page.

Exposes ``window.__PATTISHOT__`` with the STEP 1-2 primitives plus a reversible
mutation registry so the page's DOM/style is fully restored after capture
(spec section 4 STEP1-2, section 6 "後始末").
"""

# One self-contained, idempotent installer. Safe to run many times.
BROWSER_JS = r"""
(() => {
  if (window.__PATTISHOT__ && window.__PATTISHOT__.__v === 4) return;
  const S = {
    __v: 4,
    scroller: null,
    scrollerIsDoc: true,
    restores: [],
  };

  const isDoc = (el) => el === document.scrollingElement ||
                        el === document.documentElement || el === document.body;

  function pushRestore(fn) { S.restores.push(fn); }

  // ---- scroller detection (spec STEP1.1) ----
  function findScroller() {
    const de = document.scrollingElement || document.documentElement;
    const docScrolls = (de.scrollHeight - window.innerHeight) > 200;
    let best = null, bestArea = 0;
    const all = document.getElementsByTagName('*');
    for (let i = 0; i < all.length; i++) {
      const el = all[i];
      if (el.scrollHeight - el.clientHeight <= 200) continue;
      const cs = getComputedStyle(el);
      const oy = cs.overflowY;
      if (oy !== 'auto' && oy !== 'scroll' && oy !== 'overlay') continue;
      const r = el.getBoundingClientRect();
      const area = r.width * r.height;
      if (area > bestArea) { best = el; bestArea = area; }
    }
    const viewportArea = window.innerWidth * window.innerHeight;
    // prefer an inner container only when the document itself barely scrolls
    // and the container is large and scrolls more than the document.
    if (best && !docScrolls && bestArea > viewportArea * 0.4) {
      S.scroller = best; S.scrollerIsDoc = false;
    } else {
      S.scroller = de; S.scrollerIsDoc = true;
    }
    return { isDoc: S.scrollerIsDoc, tag: (S.scroller.tagName || 'DOC') };
  }

  function scrollTo(pos) {
    if (S.scrollerIsDoc) window.scrollTo(0, pos);
    else S.scroller.scrollTop = pos;
  }
  function currentScroll() {
    return S.scrollerIsDoc ? window.scrollY : S.scroller.scrollTop;
  }
  const raf = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const wait = (ms) => new Promise(r => setTimeout(r, ms));

  // ---- expand an inner scroll container so its content lays out fully ----
  function expandInnerScroller() {
    if (S.scrollerIsDoc || !S.scroller) return;
    const el = S.scroller;
    const prev = {
      height: el.style.height, maxHeight: el.style.maxHeight,
      overflow: el.style.overflow, overflowY: el.style.overflowY,
      overflowX: el.style.overflowX,
    };
    el.style.height = 'auto';
    el.style.maxHeight = 'none';
    el.style.overflow = 'visible';
    el.style.overflowY = 'visible';
    el.setAttribute('data-patti-shot-touched', '1');
    pushRestore(() => {
      el.style.height = prev.height; el.style.maxHeight = prev.maxHeight;
      el.style.overflow = prev.overflow; el.style.overflowY = prev.overflowY;
      el.style.overflowX = prev.overflowX;
      el.removeAttribute('data-patti-shot-touched');
    });
  }

  // ---- force rendering of lazy / content-visibility content (STEP1.3) ----
  function forceRender() {
    try {
      const st = document.createElement('style');
      st.setAttribute('data-patti-shot', '1');
      st.textContent = '*{content-visibility:visible !important;' +
                       'contain-intrinsic-size:auto !important;}';
      document.documentElement.appendChild(st);
      pushRestore(() => { if (st.parentNode) st.parentNode.removeChild(st); });
    } catch (e) {}
    try {
      const lazy = document.querySelectorAll('[loading="lazy"]');
      const changed = [];
      lazy.forEach(el => {
        el.setAttribute('loading', 'eager');
        el.setAttribute('data-patti-shot-touched', '1');
        changed.push(el);
      });
      pushRestore(() => changed.forEach(el => {
        el.setAttribute('loading', 'lazy');
        el.removeAttribute('data-patti-shot-touched');
      }));
    } catch (e) {}
  }

  async function decodeImages() {
    const imgs = Array.from(document.images).filter(i => i.src);
    await Promise.allSettled(imgs.slice(0, 400).map(i => i.decode ? i.decode() : Promise.resolve()));
  }

  // ---- lazy-load firing: round-trip scroll (STEP1.2) ----
  async function triggerLazyLoad() {
    const step = Math.max(200, Math.floor(window.innerHeight * 0.85));
    let travelled = 0;
    const CAP = 100000;
    // downward
    let pos = 0, guard = 0;
    while (guard++ < 2000) {
      scrollTo(pos);
      await raf(); await wait(80);
      travelled += step;
      const max = (S.scrollerIsDoc ? document.scrollingElement.scrollHeight
                                   : S.scroller.scrollHeight) - window.innerHeight;
      if (pos >= max || travelled >= CAP) break;
      pos = Math.min(pos + step, max);
    }
    // upward
    while (pos > 0 && travelled < CAP * 2) {
      pos = Math.max(0, pos - step * 2);
      scrollTo(pos);
      await raf(); await wait(30);
      travelled += step * 2;
    }
    scrollTo(0);
    await raf();
  }

  async function prepare() {
    findScroller();
    expandInnerScroller();
    forceRender();
    await triggerLazyLoad();
    await decodeImages();
    scrollTo(0);
    await raf();
    return { isDoc: S.scrollerIsDoc };
  }

  // ---- real content-height measurement (STEP2, the core fix) ----
  function measure() {
    const de = document.scrollingElement || document.documentElement;
    let maxBottom = 0;
    const all = document.body ? document.body.getElementsByTagName('*') : [];
    for (let i = 0; i < all.length; i++) {
      const el = all[i];
      if (el.hasAttribute('data-patti-shot-ui')) continue;  // our own UI
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden') continue;
      if (cs.position === 'fixed') continue;  // fixed elements add no content length
      const r = el.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) continue;
      const b = r.bottom + window.scrollY;
      if (b > maxBottom) maxBottom = b;
    }
    const scrollH = Math.max(de.scrollHeight, (document.body || de).scrollHeight);
    const width = Math.max(de.scrollWidth, (document.body || de).scrollWidth, de.clientWidth);
    const content = Math.ceil(maxBottom) || scrollH;
    const captureHeight = Math.min(scrollH, content + 100);
    return {
      contentHeight: content,
      scrollHeight: scrollH,
      width: width,
      captureHeight: captureHeight,
      viewport: window.innerHeight,
    };
  }

  // ---- fixed / sticky neutralisation (STEP3, split only) ----
  function neutralizeFixed() {
    const all = document.getElementsByTagName('*');
    const touched = [];
    for (let i = 0; i < all.length; i++) {
      const el = all[i];
      const cs = getComputedStyle(el);
      if (cs.position === 'fixed' || cs.position === 'sticky') {
        const prev = el.style.position;
        const prevPri = el.style.getPropertyPriority('position');
        el.style.setProperty('position', 'static', 'important');
        el.setAttribute('data-patti-shot-touched', '1');
        touched.push([el, prev, prevPri]);
      }
    }
    pushRestore(() => touched.forEach(([el, prev, prevPri]) => {
      el.style.removeProperty('position');
      if (prev) el.style.setProperty('position', prev, prevPri);
      el.removeAttribute('data-patti-shot-touched');
    }));
  }

  // ---- our own injected UI: hide during capture ----
  function hideUI() {
    const els = document.querySelectorAll('[data-patti-shot-ui]');
    const touched = [];
    els.forEach(el => { touched.push([el, el.style.visibility]); el.style.visibility = 'hidden'; });
    return () => touched.forEach(([el, v]) => { el.style.visibility = v; });
  }

  function restoreAll() {
    while (S.restores.length) {
      const fn = S.restores.pop();
      try { fn(); } catch (e) {}
    }
    scrollTo(0);
  }

  // ---- 後始末 verification (spec section 6 "後始末") ----
  // A robust fingerprint of OUR mutation surface only, so a page mutating
  // itself during scroll (lazy reveal, infinite-scroll appends) does not read
  // as an incomplete restore. Catches: leftover injected style tags, leftover
  // touch-marked elements, and any fixed/sticky element we failed to restore
  // (count would drift from baseline).
  function styleSignature() {
    const all = document.getElementsByTagName('*');
    let fixed = 0, sticky = 0;
    for (let i = 0; i < all.length; i++) {
      const pos = getComputedStyle(all[i]).position;
      if (pos === 'fixed') fixed++;
      else if (pos === 'sticky') sticky++;
    }
    const tags = document.querySelectorAll('style[data-patti-shot]').length;
    const touched = document.querySelectorAll('[data-patti-shot-touched]').length;
    return 'f' + fixed + ':s' + sticky + ':tag' + tags + ':m' + touched;
  }

  // ---- keyword boxes for missing-content check (absolute CSS px) ----
  function keywordBoxes(n, maxY) {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        const t = (node.nodeValue || '').trim();
        if (t.length < 6) return NodeFilter.FILTER_REJECT;
        const p = node.parentElement;
        if (!p) return NodeFilter.FILTER_REJECT;
        const cs = getComputedStyle(p);
        if (cs.display === 'none' || cs.visibility === 'hidden') return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    // A text node can keep a layout rect while being visually clipped by an
    // overflow-hidden/collapsed ancestor (e.g. Wikipedia navboxes): present in
    // the DOM but never painted. Exclude those so the check measures only what
    // is actually rendered.
    function isClipped(el, r) {
      let p = el;
      while (p && p !== document.body && p !== document.documentElement) {
        const cs = getComputedStyle(p);
        if (cs.overflow !== 'visible' || cs.overflowY !== 'visible' || cs.overflowX !== 'visible') {
          const er = p.getBoundingClientRect();
          const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
          if (cx < er.left - 1 || cx > er.right + 1 || cy < er.top - 1 || cy > er.bottom + 1)
            return true;
        }
        p = p.parentElement;
      }
      return false;
    }
    const cands = [];
    let node;
    while ((node = walker.nextNode())) {
      if (cands.length >= 500) break;
      // tight box of the FIRST rendered line of the text node. Using the
      // union bounding box would, for wrapped multi-line text, cover mostly
      // whitespace and falsely read as blank.
      const range = document.createRange();
      range.selectNodeContents(node);
      const rects = range.getClientRects();
      if (!rects.length) continue;
      const r = rects[0];
      if (r.width <= 4 || r.height <= 4 || r.width > 900) continue;
      if (isClipped(node.parentElement, r)) continue;
      const top = r.top + window.scrollY, left = r.left + window.scrollX;
      if (maxY && top + r.height > maxY - 4) continue;
      if (top < 0) continue;
      cands.push({ text: node.nodeValue.trim().slice(0, 30),
                   x: left, y: top, w: r.width, h: Math.min(r.height, 120) });
    }
    // sample spread across the page
    const out = [];
    if (cands.length <= n) return cands;
    const stepSel = cands.length / n;
    for (let i = 0; i < n; i++) out.push(cands[Math.floor(i * stepSel)]);
    return out;
  }

  window.__PATTISHOT__ = {
    __v: 4,
    prepare, measure, neutralizeFixed, restoreAll, styleSignature,
    keywordBoxes, findScroller,
    _hideUI: hideUI, _state: S,
  };
})();
"""


def install_expr() -> str:
    """JS to (re)install the API in the current page context."""
    return BROWSER_JS
