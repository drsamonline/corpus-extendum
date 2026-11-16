/* Corpus Extendum — the library page.
 *
 * Reads three static files and nothing else:
 *   data/catalog.json   every book
 *   data/shards.json    which vault repo serves it, and its CDN base
 *   data/categories.json the rail
 *
 * Books are fetched from the vault repos through jsDelivr, never from this
 * repo. One renderer per format; a renderer is only fetched when a reader
 * opens that format, so a text reader downloads no PDF engine.
 */
'use strict';

const state = {
  catalog: [], shards: {}, cats: [], searchIndex: [],
  cat: 'All', query: '', sort: 'curated',
  open: null, fmt: null,
  pdf: null, pdfPage: 1, pdfDoc: null, epubBook: null, epubRendition: null,
};

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/* ------------------------------------------------------------------ data */
async function boot() {
  try {
    // A unique query per load defeats every layer of caching at once: the
    // HTTP cache, a proxy, and any service worker that keys on the URL. The
    // catalogue is 15 KB; correctness is worth more than saving that.
    const FRESH = { cache: 'no-store' };
    const stamp = '?t=' + Date.now();
    const [catalog, shards, cats] = await Promise.all([
      fetch('data/catalog.json' + stamp, FRESH).then(r => r.json()),
      fetch('data/shards.json' + stamp, FRESH).then(r => r.json()),
      fetch('data/categories.json' + stamp, FRESH).then(r => r.json()),
    ]);
    state.catalog = catalog;
    state.cats = cats;
    shards.forEach(s => { state.shards[s.name] = s; });

    const vault = Object.values(state.shards)[0] || { books: 0, mb: 0, cap_books: 600, cap_mb: 2500, name: 'vault-01', state: 'open' };
    $('statBooks').textContent = catalog.length;
    $('statVaults').textContent = Object.keys(state.shards).length;
    $('statCats').textContent = cats.length;
    $('shardName').textContent = vault.name;
    const built = vault.built ? new Date(vault.built).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
    $('shardMeta').innerHTML = `<b>${vault.books}</b> / ${vault.cap_books} books · ${vault.mb} MB / ${vault.cap_mb} MB · <span style="color:var(--teal);font-weight:600">${vault.state}</span>${built ? ` · catalogue built ${built}` : ''}`;
    $('meterFill').style.width = Math.max(2, (vault.books / vault.cap_books) * 100).toFixed(1) + '%';
    $('vaultList').innerHTML = Object.values(state.shards)
      .map(s => `<a href="https://github.com/${s.repo}">${s.name}</a> · ${s.books} books`).join('<br>');

    try {
      state.searchIndex = await fetch('data/search-index.json' + stamp, FRESH).then(r => r.json());
    } catch (e) { state.searchIndex = []; }

    renderCats();
    render();
  } catch (err) {
    $('grid').innerHTML = `<div class="empty" style="grid-column:1/-1">The catalogue did not load: ${esc(err.message)}</div>`;
  }
}

function cdn(book, fmt) {
  const s = state.shards[book.vault];
  const base = s ? s.cdn : '';
  return `${base}/books/${book.slug}/${book.slug}.${fmt}`;
}
function raw(book, file) {
  const s = state.shards[book.vault];
  return `${s ? s.raw : ''}/${file}`;
}

/* ------------------------------------------------------------- the shelf */
function renderCats() {
  const counts = {};
  state.catalog.forEach(b => counts[b.category] = (counts[b.category] || 0) + 1);
  const items = [['All', state.catalog.length], ...state.cats.map(([c, n]) => [c, n])];
  $('catrow').innerHTML = items.map(([c, n]) =>
    `<button class="chip${c === state.cat ? ' on' : ''}" data-cat="${esc(c)}">${esc(c)}<span class="c">${n}</span></button>`
  ).join('');
  $('catrow').querySelectorAll('.chip').forEach(ch => ch.onclick = () => {
    state.cat = ch.dataset.cat; renderCats(); render();
  });
}

function tokenMatch(book, words) {
  if (!words.length) return true;
  const row = state.searchIndex.find(r => r.slug === book.slug);
  const hay = row ? row.t.join(' ') : [book.title, book.author.name, book.category].join(' ').toLowerCase();
  return words.every(w => hay.includes(w));
}

function render() {
  const words = state.query.toLowerCase().split(/\s+/).filter(Boolean);
  let list = state.catalog.filter(b =>
    (state.cat === 'All' || b.category === state.cat) && tokenMatch(b, words));

  if (state.sort === 'title') list = [...list].sort((a, b) => a.title.localeCompare(b.title));
  if (state.sort === 'author') list = [...list].sort((a, b) => a.author.name.localeCompare(b.author.name));
  if (state.sort === 'year') list = [...list].sort((a, b) => parseInt(a.year) - parseInt(b.year));
  if (state.sort === 'new') list = [...list].reverse();

  $('count').textContent = `${list.length} ${list.length === 1 ? 'book' : 'books'}`;
  $('shelfTitle').textContent = state.cat === 'All' ? 'The shelf' : state.cat;

  if (!list.length) {
    $('grid').innerHTML = `<div class="empty" style="grid-column:1/-1">No book matches “${esc(state.query)}”. The shelf grows in batches — try a broader word.</div>`;
    return;
  }

  $('grid').innerHTML = list.map(b => {
    const cover = raw(b, `books/${b.slug}/cover.jpg`);
    return `<a class="card" href="#" data-slug="${b.slug}">
      <div class="cover">
        <div class="fallback"><div class="ft">${esc(b.title)}</div><div class="fa">${esc(b.author.name)}</div></div>
        <span class="badge">Public domain</span>
        <img src="${cover}" alt="Cover of ${esc(b.title)}" loading="lazy" onerror="this.style.display='none'">
      </div>
      <div class="ctitle">${esc(b.title)}</div>
      <div class="cauthor">${esc(b.author.name)}</div>
      <div class="cfoot"><span class="tag">${esc(b.category)}</span><span>·</span><span>${b.year}</span></div>
      <div class="cfmt">${b.formats.map(f => `<span>${f}</span>`).join('')}</div>
    </a>`;
  }).join('');

  $('grid').querySelectorAll('.card').forEach(c =>
    c.onclick = (e) => { e.preventDefault(); openBook(c.dataset.slug); });
}

/* ---------------------------------------------------------------- reader */
const reader = $('reader');
let lastFocus = null;

const FORMAT_LABEL = { pdf: 'PDF', epub: 'EPUB', txt: 'TXT', json: 'JSON' };

function openBook(slug) {
  const b = state.catalog.find(x => x.slug === slug);
  if (!b) return;
  state.open = b;
  lastFocus = document.activeElement;

  $('rTitle').textContent = b.title;
  $('rAuthor').textContent = b.author.name;
  $('sTitle').textContent = b.title;
  $('sAuthor').textContent = b.author.name;
  $('sYear').textContent = b.year;
  $('sCat').textContent = b.category;
  $('sLang').textContent = b.language || 'English';
  $('sSrc').textContent = b.source ? b.source.name : '—';
  $('sShard').textContent = `${b.vault}/books/${b.slug}`;
  $('sBlurb').textContent = b.blurb || '';
  $('sRights').textContent = b.rights ? b.rights.basis : '';
  $('sFiles').innerHTML = ['pdf', 'epub', 'txt'].filter(f => b.formats.includes(f)).map(f =>
    `<a href="${cdn(b, f)}" target="_blank" rel="noopener"><span>Download ${f.toUpperCase()}</span><span style="color:#7E7568">↗</span></a>`
  ).join('') + `<a href="${raw(b, `books/${b.slug}/meta.json`)}" target="_blank" rel="noopener"><span>Record (JSON)</span><span style="color:#7E7568">↗</span></a>`;

  const fmts = [...b.formats, 'json'];
  $('fmtbar').innerHTML = fmts.map(f =>
    `<button class="fp" data-f="${f}">${FORMAT_LABEL[f] || f.toUpperCase()}</button>`).join('');
  $('fmtbar').querySelectorAll('.fp').forEach(p => p.onclick = () => setFormat(p.dataset.f));

  reader.classList.add('open');
  document.body.classList.add('locked');
  $('rClose').focus();

  setFormat(b.formats.includes('pdf') ? 'pdf' : b.formats[0]);
}

function closeReader() {
  reader.classList.remove('open');
  document.body.classList.remove('locked');
  if (state.epubRendition) { try { state.epubRendition.destroy(); } catch (e) {} state.epubRendition = null; }
  state.pdfDoc = null; state.epubBook = null;
  if (lastFocus) lastFocus.focus();
}

function setFormat(fmt) {
  state.fmt = fmt;
  const b = state.open;
  $('fmtbar').querySelectorAll('.fp').forEach(p => p.classList.toggle('on', p.dataset.f === fmt));
  $('rDownload').href = fmt === 'json' ? raw(b, `books/${b.slug}/meta.json`) : cdn(b, fmt);
  $('page').style.display = 'none';
  $('pdfCanvas').style.display = 'none';
  $('epubBox').style.display = 'none';
  const canTurn = !(fmt === 'pdf' && window.innerWidth <= 820);
  $('rPrev').style.display = canTurn ? '' : 'none';
  $('rNext').style.display = canTurn ? '' : 'none';
  $('rPage').textContent = '—';

  if (fmt === 'pdf') renderPdf(b);
  else if (fmt === 'epub') renderEpub(b);
  else if (fmt === 'txt') renderTxt(b);
  else renderJson(b);
}

/* A stalled fetch must surface as an error, never as an empty pane. */
function withTimeout(promise, ms, what) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error(what + ' within ' + Math.round(ms / 1000) + 's')), ms)),
  ]);
}

/* Fit the page to the stage on both axes. Sizing on width alone is what cut
 * the bottom off a page on a phone; sizing on height alone wasted a wide
 * screen. Take the smaller ratio and the whole page always fits. */
function fitScale(vp1) {
  const stage = $('stage');
  const small = window.innerWidth <= 820;
  const availW = Math.max(200, stage.clientWidth - (small ? 12 : 56));
  const availH = Math.max(200, stage.clientHeight - (small ? 16 : 56));
  return Math.max(0.15, Math.min(availW / vp1.width, availH / vp1.height));
}

/* Rotating a phone or resizing a window must re-fit, not re-open. */
let refitTimer = null;
window.addEventListener('resize', () => {
  if (state.fmt === 'epub' && state.epubRendition) {
    try { state.epubRendition.resize(); } catch (e) {}
    return;
  }
  if (state.fmt !== 'pdf' || !state.pdfDoc) return;
  clearTimeout(refitTimer);
  refitTimer = setTimeout(() => renderPdf(state.open), 180);
});

function showNativePdf(b, why) {
  // A slow PDF failure must not hijack the reader after the reader has moved
  // on to another format. Without this guard, a late error tore down the EPUB.
  if (state.fmt !== 'pdf') return;
  const frame = $('pdfFrame');
  $('pdfCanvas').style.display = 'none';
  frame.style.display = 'block';
  frame.src = cdn(b, 'pdf') + '#view=FitH';
  $('rPrev').style.display = 'none';
  $('rNext').style.display = 'none';
  $('rPage').textContent = 'Scroll';
  $('rNote').textContent = why || 'Native PDF viewer — it fits the width, and pinching zooms.';
}

async function renderPdf(b) {
  // A phone gets the browser's own PDF viewer: it fits the width by default,
  // it pinches, and it scrolls without me re-drawing a canvas per page.
  if (window.innerWidth <= 820) { showNativePdf(b); return; }
  $('pdfFrame').style.display = 'none';
  const canvas = $('pdfCanvas');
  canvas.style.display = 'block';
  $('rNote').textContent = 'Rendering the PDF in the page — pdf.js, no plugin, no download.';
  try {
    if (!window.pdfjsLib) throw new Error('pdf.js did not load');
    pdfjsLib.GlobalWorkerOptions.workerSrc = 'assets/vendor/pdf.worker.min.js';
    if (!state.pdfDoc) {
      // No disableAutoFetch: that switches pdf.js to range requests, which
      // hangs against any server that does not answer them — and a stall here
      // looked exactly like a blank page. One whole-file fetch works anywhere.
      const doc = await withTimeout(
        pdfjsLib.getDocument({ url: cdn(b, 'pdf') }).promise, 30000,
        'the PDF did not finish loading');
      if (state.fmt !== 'pdf') return;   // the reader changed format while loading
      state.pdfDoc = doc;
      state.pdfPage = 1;
    }
    const page = await state.pdfDoc.getPage(state.pdfPage);
    const vp1 = page.getViewport({ scale: 1 });
    const scale = fitScale(vp1);
    const vp = page.getViewport({ scale });
    canvas.width = vp.width; canvas.height = vp.height;
    await page.render({ canvasContext: canvas.getContext('2d'), viewport: vp }).promise;
    $('rPage').textContent = `Page ${state.pdfPage} / ${state.pdfDoc.numPages}`;
    $('rNote').textContent = `${b.title} — typeset for this library, ${state.pdfDoc.numPages} pages. ← → turn pages, Home and End jump, Esc closes.`;
  } catch (err) {
    // Never leave a blank pane — but only if the reader is still on the PDF.
    if (state.fmt !== 'pdf') return;
    showNativePdf(b, `The in-page renderer could not draw this (${err.message}), so the browser's own viewer is showing it instead.`);
  }
}

async function renderEpub(b) {
  const box = $('epubBox');
  box.style.display = 'block';
  $('rNote').textContent = 'Reflowable EPUB — epub.js. This is the best view on a phone.';
  try {
    if (!window.ePub) throw new Error('epub.js did not load');
    if (state.epubRendition) { try { state.epubRendition.destroy(); } catch (e) {} }
    state.epubBook = ePub(cdn(b, 'epub'));
    // renderTo() before the archive has opened produces an empty box and no
    // error — the reader looks broken rather than failing. Wait for it.
    await state.epubBook.ready;
    // scrolled-continuous scrolls the whole book in one column. 'scrolled'
    // alone gave one section at a time with no way to reach the next, which is
    // why the EPUB felt dead: no scroll, and the page buttons were hidden.
    state.epubRendition = state.epubBook.renderTo(box, {
      width: '100%', height: '100%', flow: 'scrolled-continuous',
    });
    state.epubRendition.on('relocated', (loc) => {
      if (state.fmt !== 'epub' || !loc || !loc.start) return;
      const pct = Math.round((loc.start.percentage || 0) * 100);
      $('rPage').textContent = pct ? pct + '%' : 'Scroll';
    });
    $('rPage').textContent = 'Scroll';
    await state.epubRendition.display();
    // epub.js measures its container when it attaches. If that happens before
    // layout settles the iframe comes out shorter than the box, so ask it to
    // measure again once the frame is on screen.
    setTimeout(() => {
      if (state.fmt === 'epub' && state.epubRendition) {
        try { state.epubRendition.resize(); } catch (e) {}
      }
    }, 120);
  } catch (err) {
    box.style.display = 'none';
    $('rNote').innerHTML = `This EPUB could not be opened here (${esc(err.message)}). <a href="${cdn(b, 'epub')}" target="_blank" rel="noopener" style="color:#A8C4BB">Download it</a>.`;
  }
}

async function renderTxt(b) {
  const page = $('page');
  page.className = 'txtpage';
  page.style.display = 'block';
  $('rNote').textContent = 'Plain text, paginated in the browser — nothing to download to start reading.';
  try {
    const text = await fetch(cdn(b, 'txt')).then(r => r.text());
    // Wrapped by the browser, not by a fixed column count: 72 columns is
    // unreadable on a 360px screen and was being clipped, not wrapped.
    page.innerHTML = `<div class="monoh"><span>${b.slug}.txt</span><span>plain text</span></div>`
      + `<pre>${esc(text)}</pre>`;
  } catch (err) {
    page.textContent = `Could not load the text (${err.message}).`;
  }
}

async function renderJson(b) {
  const page = $('page');
  page.className = 'codepage';
  page.style.display = 'block';
  $('rNote').textContent = 'The catalogue record itself — the same JSON the site reads.';
  try {
    const rec = await fetch(raw(b, `books/${b.slug}/meta.json`)).then(r => r.json());
    page.innerHTML = `<div class="monoh"><span>meta.json</span><span>the record</span></div>` + highlight(rec);
  } catch (err) {
    page.textContent = `Could not load the record (${err.message}).`;
  }
}

function highlight(o) {
  let s = esc(JSON.stringify(o, null, 2));
  s = s.replace(/&quot;(.*?)&quot;(\s*:)/g, '<span class="kk">&quot;$1&quot;</span>$2');
  s = s.replace(/:(&nbsp;|\s)*&quot;(.*?)&quot;/g, ': <span class="ss">&quot;$2&quot;</span>');
  s = s.replace(/^(\s*)&quot;(.*?)&quot;(,?)$/gm, '$1<span class="ss">&quot;$2&quot;</span>$3');
  s = s.replace(/:\s*(-?\d+\.?\d*)/g, ': <span class="nn">$1</span>');
  s = s.replace(/\b(true|false|null)\b/g, '<span class="pp">$1</span>');
  return s;
}

/* -------------------------------------------------------------- controls */
$('rClose').onclick = closeReader;
/* One turn, four formats. A page is only meaningful for a PDF; for everything
 * else "turn" means the next section (EPUB) or the next screenful (text, JSON).
 */
function turn(dir) {
  if (state.fmt === 'pdf') {
    if (!state.pdfDoc) return;
    const next = state.pdfPage + dir;
    if (next < 1 || next > state.pdfDoc.numPages) return;
    state.pdfPage = next;
    renderPdf(state.open);
    return;
  }
  if (state.fmt === 'epub' && state.epubRendition) {
    if (dir > 0) state.epubRendition.next();
    else state.epubRendition.prev();
    return;
  }
  // 'auto', not 'smooth': a whole-screen jump animated over 300ms reads as lag
  // when you are turning pages, and an instant jump is what a page turn is.
  const stage = $('stage');
  stage.scrollBy({ top: dir * Math.round(stage.clientHeight * 0.85), behavior: 'auto' });
}

$('rPrev').onclick = () => turn(-1);
$('rNext').onclick = () => turn(1);
document.addEventListener('keydown', (e) => {
  if (!reader.classList.contains('open')) {
    if (e.key === '/') { e.preventDefault(); $('q').focus(); }
    return;
  }
  const k = e.key;
  if (k === 'Escape') { closeReader(); return; }
  if (k === 'ArrowRight' || k === 'PageDown' || k === ' ') { e.preventDefault(); turn(1); return; }
  if (k === 'ArrowLeft' || k === 'PageUp') { e.preventDefault(); turn(-1); return; }
  if (k === 'Home') { e.preventDefault(); $('stage').scrollTo({ top: 0, behavior: 'smooth' }); return; }
  if (k === 'End') { e.preventDefault(); const st = $('stage'); st.scrollTo({ top: st.scrollHeight, behavior: 'smooth' }); return; }
  if (k === 'ArrowDown') { e.preventDefault(); $('stage').scrollBy({ top: 80, behavior: 'smooth' }); return; }
  if (k === 'ArrowUp') { e.preventDefault(); $('stage').scrollBy({ top: -80, behavior: 'smooth' }); return; }
  if (k === '1') setFormat('pdf');
  if (k === '2' && state.open.formats.includes('epub')) setFormat('epub');
  if (k === '3') setFormat('txt');
  if (k === '4') setFormat('json');
});

/* Text and JSON have no page count, so report position as a percentage. */
$('stage').addEventListener('scroll', () => {
  if (state.fmt === 'pdf' || state.fmt === 'epub') return;
  const st = $('stage');
  const max = st.scrollHeight - st.clientHeight;
  if (max <= 0) return;
  $('rPage').textContent = Math.round((st.scrollTop / max) * 100) + '%';
}, { passive: true });

function setQuery(v) { $('q').value = v; $('q2').value = v; state.query = v.trim(); render(); }
$('q').addEventListener('input', e => setQuery(e.target.value));
$('q2').addEventListener('input', e => setQuery(e.target.value));
$('sort').onchange = e => { state.sort = e.target.value; render(); };
$('randomBtn').onclick = () => {
  if (!state.catalog.length) return;
  openBook(state.catalog[Math.floor(Math.random() * state.catalog.length)].slug);
};
$('theme').onclick = () => {
  const cur = document.documentElement.getAttribute('data-theme');
  document.documentElement.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
};

boot();
