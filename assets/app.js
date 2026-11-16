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

/* The footer stamp is read from this script's own ?v=, so it can never say
 * something different from the code that is running. It said 20261116d for six
 * releases while the assets moved on, which made it useless for the one job it
 * had: telling a reader whether they were on a stale build. */
const BUILD = (() => {
  const tag = document.querySelector('script[src*="app.js"]');
  const m = tag && tag.src.match(/[?&]v=([0-9a-z]+)/i);
  return m ? m[1] : 'dev';
})();

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

    if ($('buildStamp')) $('buildStamp').textContent = 'site build ' + BUILD;
    renderCats();
    render();
    renderResume();
  } catch (err) {
    $('grid').innerHTML = `<div class="empty" style="grid-column:1/-1">The catalogue did not load: ${esc(err.message)}</div>`;
  }
}

function cdn(book, fmt) {
  const s = state.shards[book.vault];
  const base = s ? s.cdn : '';
  return `${base}/books/${book.slug}/${book.slug}.${fmt}`;
}

function rawFile(book, fmt) {
  const s = state.shards[book.vault];
  return `${s ? s.raw : ''}/books/${book.slug}/${book.slug}.${fmt}`;
}

/* jsDelivr refuses text files from a repository over 50 MB — its package
 * limit — while still serving the PDFs and covers from the same repo. Raw has
 * no such limit, so text goes there and binary tries the CDN first with raw as
 * a fallback. Measured, not assumed: the .txt returned 403 with "Package size
 * exceeded the configured limit of 50 MB" while the .pdf beside it returned
 * 200 from the same vault.
 */
function fileUrl(book, fmt) {
  // raw is the primary for every format. jsDelivr refuses text files from a
  // repository over 50 MB and, measured on this vault at 212 MB, also returns
  // 404 for some EPUBs and hangs on others — while raw returned 200 for every
  // file tested. The CDN is a fallback, not the route.
  return rawFile(book, fmt);
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



/* --------------------------------------------------------------- progress */
const PROGRESS_KEY = 'corpus-extendum:progress';

function readProgress() {
  try { return JSON.parse(localStorage.getItem(PROGRESS_KEY) || '{}'); }
  catch (e) { return {}; }
}
function writeProgress(all) {
  try { localStorage.setItem(PROGRESS_KEY, JSON.stringify(all)); } catch (e) {}
}

/* Where the reader is, in a form the same format can restore. A PDF has a page;
 * everything else has a fraction. Both are stored so a format switch keeps
 * roughly the same place. */
function currentPosition() {
  const st = $('stage');
  const pct = st.scrollHeight > st.clientHeight
    ? st.scrollTop / (st.scrollHeight - st.clientHeight) : 0;
  const pos = { fmt: state.fmt, page: state.pdfPage || 1, pct: Math.max(0, Math.min(1, pct)) };
  if (state.fmt === 'epub' && state.epubCfi) pos.cfi = state.epubCfi;
  return pos;
}

function saveProgress() {
  if (!state.open) return;
  const all = readProgress();
  all[state.open.slug] = Object.assign(currentPosition(), {
    at: Date.now(), title: state.open.title, author: state.open.author.name,
  });
  writeProgress(all);
}

let progressTimer = null;
function saveProgressSoon() {
  clearTimeout(progressTimer);
  progressTimer = setTimeout(saveProgress, 700);
}

function renderResume() {
  const all = readProgress();
  const entries = Object.entries(all)
    .sort((a, b) => (b[1].at || 0) - (a[1].at || 0))
    .slice(0, 8)
    .map(([slug, p]) => ({ slug, ...p }))
    .filter(e => state.catalog.some(b => b.slug === e.slug));

  $('resume').hidden = entries.length === 0;
  $('resumeRow').innerHTML = entries.map(e => {
    const b = state.catalog.find(x => x.slug === e.slug);
    const pct = e.fmt === 'pdf' ? Math.round(((e.page || 1) / 400) * 100) : Math.round((e.pct || 0) * 100);
    return `<button class="rcard" data-slug="${e.slug}">
      <div class="rcover">
        <img src="${raw(b, `books/${b.slug}/cover.jpg`)}" alt="" loading="lazy" onerror="this.style.display='none'">
        <div class="rbar-progress"><i style="width:${Math.min(100, Math.max(2, pct))}%"></i></div>
      </div>
      <div class="rtitle">${esc(e.title || b.title)}</div>
      <div class="rmeta">${e.fmt === 'pdf' ? 'page ' + (e.page || 1) : pct + '%'} · ${e.fmt.toUpperCase()}</div>
    </button>`;
  }).join('');
  $('resumeRow').querySelectorAll('.rcard').forEach(c =>
    c.onclick = () => openBook(c.dataset.slug));
}

function restorePosition(b) {
  const saved = readProgress()[b.slug];
  if (!saved) return;
  const fmt = saved.fmt || 'pdf';

  // Restore the format as well as the place. The reader always opens as PDF, so
  // a book last read as text would otherwise restore into the wrong view.
  const available = ['pdf', ...(b.formats || [])];
  if (fmt !== state.fmt && available.includes(fmt)) setFormat(fmt);

  if (state.fmt === 'pdf') {
    if (saved.page > 1) {
      state.pendingPage = saved.page;
      if (state.pdfDoc) { state.pdfPage = saved.page; renderPdf(b); }
    }
    return;
  }

  if (state.fmt === 'epub') {
    // A CFI is epub.js's own locator and needs nothing precomputed.
    if (!saved.cfi) return;
    waitFor(() => (state.epubRendition ? state.epubRendition : null), 8000)
      .then((rendition) => {
        try { if (rendition) rendition.display(saved.cfi); } catch (e) {}
      });
    return;
  }

  if (saved.pct) {
    waitFor(() => {
      const st = $('stage');
      return st.scrollHeight > st.clientHeight + 20 ? st : null;
    }, 8000).then((st) => {
      if (st) st.scrollTop = saved.pct * (st.scrollHeight - st.clientHeight);
    });
  }
}


/* ------------------------------------------------------------- bookmarks */
const MARKS_KEY = 'corpus-extendum:bookmarks';

function readMarks() {
  try { return JSON.parse(localStorage.getItem(MARKS_KEY) || '{}'); } catch (e) { return {}; }
}
function writeMarks(all) {
  try { localStorage.setItem(MARKS_KEY, JSON.stringify(all)); } catch (e) {}
}

function positionLabel(pos) {
  if (pos.fmt === 'pdf') return `page ${pos.page}`;
  if (pos.fmt === 'epub') return 'section';
  return `${Math.round((pos.pct || 0) * 100)}% through`;
}

function addBookmark() {
  if (!state.open) return;
  const all = readMarks();
  const slug = state.open.slug;
  const pos = currentPosition();
  const list = all[slug] || [];
  // one mark per place, so pressing it twice does not stack duplicates
  const dupe = list.some(m => m.fmt === pos.fmt && m.page === pos.page &&
                              Math.abs((m.pct || 0) - (pos.pct || 0)) < 0.01 && m.cfi === pos.cfi);
  if (!dupe) {
    list.unshift(Object.assign(pos, { at: Date.now(), label: positionLabel(pos) }));
    all[slug] = list.slice(0, 30);
    writeMarks(all);
  }
  renderMarks();
  $('marksPanel').hidden = false;
}

function jumpToPosition(pos) {
  const b = state.open;
  const available = ['pdf', ...(b.formats || [])];
  if (pos.fmt && pos.fmt !== state.fmt && available.includes(pos.fmt)) setFormat(pos.fmt);
  $('marksPanel').hidden = true;
  if (state.fmt === 'pdf') {
    if (pos.page > 1) {
      state.pendingPage = pos.page;
      if (state.pdfDoc) { state.pdfPage = pos.page; renderPdf(b); }
    }
    return;
  }
  if (state.fmt === 'epub') {
    if (!pos.cfi) return;
    waitFor(() => (state.epubRendition ? state.epubRendition : null), 8000)
      .then(r => { try { if (r) r.display(pos.cfi); } catch (e) {} });
    return;
  }
  if (typeof pos.pct === 'number') {
    waitFor(() => {
      const st = $('stage');
      return st.scrollHeight > st.clientHeight + 20 ? st : null;
    }, 8000).then(st => { if (st) st.scrollTop = pos.pct * (st.scrollHeight - st.clientHeight); });
  }
}

function renderMarks() {
  if (!state.open) return;
  const list = readMarks()[state.open.slug] || [];
  const el = $('marksList');
  if (!list.length) {
    el.innerHTML = '<div class="marksempty">No bookmarks yet. Press <b>b</b> or Mark to save this place.</div>';
    return;
  }
  el.innerHTML = list.map((m, i) => `
    <div class="marksrow">
      <button class="marksjump" data-i="${i}">${esc(m.label)}
        <small>${new Date(m.at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })} · ${(m.fmt || '').toUpperCase()}</small>
      </button>
      <button class="marksdel" data-del="${i}" title="Remove">✕</button>
    </div>`).join('');
  el.querySelectorAll('.marksjump').forEach(btn => btn.onclick = () => jumpToPosition(list[+btn.dataset.i]));
  el.querySelectorAll('.marksdel').forEach(btn => btn.onclick = () => {
    const all = readMarks();
    all[state.open.slug].splice(+btn.dataset.del, 1);
    writeMarks(all);
    renderMarks();
  });
}

/* ------------------------------------------------------------------ find */
async function bookText(b) {
  if (state.textCache && state.textCache[b.slug]) return state.textCache[b.slug];
  state.textCache = state.textCache || {};
  const t = await fetch(fileUrl(b, 'txt'), { cache: 'force-cache' }).then(r => {
    if (!r.ok) throw new Error(`text fetch failed (${r.status})`);
    return r.text();
  });
  state.textCache[b.slug] = t;
  return t;
}

function waitFor(fn, ms) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    (function poll() {
      const v = fn();
      if (v) return resolve(v);
      if (Date.now() - t0 > ms) return resolve(null);
      setTimeout(poll, 100);
    })();
  });
}

function paragraphs(text) {
  return text.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean);
}

function openFind() {
  if (!state.open) return;
  $('findBar').hidden = false;
  $('findInput').focus();
  $('findInput').select();
}

function closeFind() {
  $('findBar').hidden = true;
  $('findResults').hidden = true;
  $('findCount').textContent = '';
}

let findTimer = null;
async function runFind(q) {
  const b = state.open;
  const results = $('findResults');
  q = q.trim();
  if (!b || q.length < 2) {
    $('findCount').textContent = '';
    results.hidden = true;
    return;
  }
  let text;
  try {
    text = await bookText(b);
  } catch (err) {
    $('findCount').textContent = 'text unavailable';
    return;
  }
  const paras = paragraphs(text);
  const needle = q.toLowerCase();
  const hits = [];
  for (let i = 0; i < paras.length && hits.length < 60; i++) {
    const idx = paras[i].toLowerCase().indexOf(needle);
    if (idx === -1) continue;
    const from = Math.max(0, idx - 45);
    const to = Math.min(paras[i].length, idx + needle.length + 60);
    hits.push({ i, pre: paras[i].slice(from, idx), word: paras[i].slice(idx, idx + q.length),
                post: paras[i].slice(idx + q.length, to) });
  }
  $('findCount').textContent = hits.length ? `${hits.length}${hits.length === 60 ? '+' : ''} match${hits.length === 1 ? '' : 'es'}` : 'no matches';
  if (!hits.length) { results.hidden = true; return; }
  results.innerHTML = hits.map(h =>
    `<button class="fresult" data-i="${h.i}">…${esc(h.pre)}<mark>${esc(h.word)}</mark>${esc(h.post)}…</button>`
  ).join('');
  results.hidden = false;
  results.querySelectorAll('.fresult').forEach(el => el.onclick = () => jumpToParagraph(+el.dataset.i));
}

async function jumpToParagraph(i) {
  const b = state.open;
  $('findResults').hidden = true;
  if (state.fmt !== 'txt') setFormat('txt');
  // The text render is asynchronous (it fetches the book), so a fixed wait
  // loses the race on a large book and the jump silently does nothing. Wait
  // for the paragraph itself.
  const para = await waitFor(() => document.querySelector(`.txtpage p[data-i="${i}"]`), 6000);
  if (!para) return;
  document.querySelectorAll('.txtpage p.hit').forEach(p => p.classList.remove('hit'));
  para.classList.add('hit');
  para.scrollIntoView({ block: 'center', behavior: 'auto' });
}

/* ---------------------------------------------------------------- reader */
const reader = $('reader');
let lastFocus = null;

const FORMAT_LABEL = { pdf: 'PDF', epub: 'EPUB', txt: 'TXT', json: 'JSON' };

/* A format chip that leads to a blank pane is worse than no chip.
 *
 * Two things can make a format unusable on a given device:
 *   · a browser with no built-in PDF viewer, where the native path renders
 *     nothing (the canvas renderer is used instead, and if that fails too the
 *     chip goes away)
 *   · a file that failed to load once — remembered per book and format, so the
 *     reader does not offer the same dead end twice
 */
function nativePdfAvailable() {
  return navigator.pdfViewerEnabled !== false;
}

function isDead(b, fmt) {
  return !!(state.dead && state.dead[`${b.slug}:${fmt}`]);
}

function markDead(b, fmt) {
  state.dead = state.dead || {};
  state.dead[`${b.slug}:${fmt}`] = true;
  renderFmtBar(b);
}

function renderFmtBar(b) {
  const el = $('fmtbar');
  if (!el) return;
  el.innerHTML = availableFormats(b).map(f =>
    `<button class="fp${f === state.fmt ? ' on' : ''}" data-f="${f}">${FORMAT_LABEL[f] || f.toUpperCase()}</button>`
  ).join('');
  el.querySelectorAll('.fp').forEach(p => p.onclick = () => setFormat(p.dataset.f));
}

function availableFormats(b) {
  const out = (b.formats || []).filter(f => !isDead(b, f));
  // PDF stays on every screen. Removing it on phones was my mistake: when the
  // EPUB also failed there was nothing left to read, which is worse than a
  // format that might not render. The canvas fits the page to both axes now, so
  // the phone case is handled rather than avoided.
  if (!out.includes('json')) out.push('json');
  return out;
}

/* If the format we are on turns out to be unusable, move to one that is. */
function fallbackFormat(b, from) {
  const left = availableFormats(b).filter(f => f !== from);
  if (!left.length) return null;
  const order = ['epub', 'txt', 'pdf', 'json'];
  left.sort((x, y) => order.indexOf(x) - order.indexOf(y));
  return left[0];
}

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

  renderFmtBar(b);

  closeFind();
  $('findInput').value = '';
  state.epubTriedRaw = false;
  state.epubCfi = null;
  $('marksPanel').hidden = true;
  renderMarks();
  renderResume();
  reader.classList.add('open');
  document.body.classList.add('locked');
  $('rClose').focus();

  const start = availableFormats(b).filter(f => f !== 'json');
  setFormat(start.includes('pdf') ? 'pdf' : (start[0] || 'json'));
  setTimeout(() => restorePosition(b), 400);
}

function closeReader() {
  saveProgress();
  renderResume();
  reader.classList.remove('open');
  document.body.classList.remove('locked');
  if (state.epubRendition) { try { state.epubRendition.destroy(); } catch (e) {} state.epubRendition = null; }
  state.pdfDoc = null; state.epubBook = null; state.epubTriedRaw = false; state.epubCfi = null;
  if (lastFocus) lastFocus.focus();
}

function setFormat(fmt) {
  const b = state.open;
  // A format that already failed for this book is not a destination.
  if (fmt !== 'json' && isDead(b, fmt)) fmt = fallbackFormat(b, fmt) || 'json';
  state.fmt = fmt;
  $('fmtbar').querySelectorAll('.fp').forEach(p => p.classList.toggle('on', p.dataset.f === fmt));
  // Text comes from raw (the CDN refuses text files above a 50 MB repo) and
  // the record always does, so only binary formats use the CDN here.
  $('rDownload').href = fmt === 'json'
    ? raw(b, `books/${b.slug}/meta.json`)
    : fileUrl(b, fmt);
  $('page').style.display = 'none';
  $('pdfCanvas').style.display = 'none';
  $('epubBox').style.display = 'none';
  const canTurn = fmt !== 'pdf' || !!state.pdfDoc;
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
  // Canvas at every width: it fits the page to both axes, keeps the page
  // controls working, and does not depend on a browser PDF plugin. The native
  // viewer is the fallback below, not the default. Hiding PDF on phones left
  // nothing to read when the EPUB also failed, which was my mistake.

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
      const load = (url) => withTimeout(pdfjsLib.getDocument({ url }).promise, 30000,
                                        'the PDF did not finish loading');
      let doc;
      try {
        doc = await load(cdn(b, 'pdf'));
      } catch (e) {
        if (state.fmt !== 'pdf') return;
        doc = await load(rawFile(b, 'pdf'));   // CDN refused; raw has no size limit
      }
      if (state.fmt !== 'pdf') return;   // the reader changed format while loading
      state.pdfDoc = doc;
      state.pdfPage = state.pendingPage || 1;
      state.pendingPage = null;
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
    if (state.fmt !== 'pdf') return;
    if (nativePdfAvailable()) {
      showNativePdf(b, `The in-page renderer could not draw this (${err.message}), so the browser's own viewer is showing it instead.`);
      return;
    }
    markDead(b, 'pdf');
    const next = fallbackFormat(b, 'pdf');
    $('rNote').textContent = `This browser cannot show PDFs in the page (${err.message}).`;
    if (next) setFormat(next);
  }
}

async function renderEpub(b) {
  const box = $('epubBox');
  box.style.display = 'block';
  $('rNote').textContent = 'Reflowable EPUB — epub.js. This is the best view on a phone.';
  try {
    if (!window.ePub) throw new Error('epub.js did not load');
    if (state.epubRendition) { try { state.epubRendition.destroy(); } catch (e) {} }
    // Same fallback as the PDF: the CDN has per-file and per-package limits
    // (it refuses text outright above 50 MB), so a refusal must not end the
    // book. Try the CDN, then raw.
    state.epubBook = ePub(fileUrl(b, 'epub'));
    // renderTo() before the archive has opened produces an empty box and no
    // error. Wait for it — with a ceiling, because epub.js never rejects when
    // the fetch 404s or hangs, which is exactly how a blank pane happened.
    await withTimeout(state.epubBook.ready, 25000, 'the EPUB did not finish loading');
    // scrolled-continuous scrolls the whole book in one column. 'scrolled'
    // alone gave one section at a time with no way to reach the next, which is
    // why the EPUB felt dead: no scroll, and the page buttons were hidden.
    state.epubRendition = state.epubBook.renderTo(box, {
      width: '100%', height: '100%', flow: 'scrolled-continuous',
    });
    state.epubRendition.on('relocated', (loc) => {
      if (state.fmt !== 'epub' || !loc || !loc.start) return;
      // epub.js hands us a CFI for free. Storing that instead of a percentage
      // is what makes an EPUB reopen where you left it — jumping by percentage
      // would need book.locations.generate(), a full pass over the book.
      if (loc.start.cfi) state.epubCfi = loc.start.cfi;
      const pct = Math.round((loc.start.percentage || 0) * 100);
      $('rPage').textContent = pct ? pct + '%' : 'Scroll';
      saveProgressSoon();
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
    if (state.fmt !== 'epub') return;
    if (!state.epubTriedRaw) {
      state.epubTriedRaw = true;
      try {
        state.epubBook = ePub(rawFile(b, 'epub'));
        await state.epubBook.ready;
        if (state.fmt !== 'epub') return;
        state.epubRendition = state.epubBook.renderTo(box, { width: '100%', height: '100%', flow: 'scrolled-continuous' });
        await state.epubRendition.display();
        return;
      } catch (e2) { /* fall through to the message below */ }
    }
    box.style.display = 'none';
    markDead(b, 'epub');
    const next = fallbackFormat(b, 'epub');
    $('rNote').innerHTML = `This EPUB could not be opened here (${esc(err.message)}).`
      + (next ? ' Showing the text instead.' : '')
      + ` <a href="${rawFile(b, 'epub')}" target="_blank" rel="noopener" style="color:#A8C4BB">Download it</a>.`;
    if (next) setFormat(next);
  }
}

async function renderTxt(b) {
  const page = $('page');
  page.className = 'txtpage';
  page.style.display = 'block';
  $('rNote').textContent = 'Plain text, paginated in the browser — nothing to download to start reading.';
  try {
    const text = await bookText(b);
    // One paragraph per element: the browser does the wrapping, and a search
    // hit has an element to scroll to and highlight.
    page.innerHTML = `<div class="monoh"><span>${b.slug}.txt</span><span>plain text</span></div>`
      + paragraphs(text).map((p, i) => `<p data-i="${i}">${esc(p)}</p>`).join('');
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
    saveProgressSoon();
    return;
  }
  if (state.fmt === 'epub' && state.epubRendition) {
    if (dir > 0) state.epubRendition.next();
    else state.epubRendition.prev();
    saveProgressSoon();
    return;
  }
  // 'auto', not 'smooth': a whole-screen jump animated over 300ms reads as lag
  // when you are turning pages, and an instant jump is what a page turn is.
  const stage = $('stage');
  stage.scrollBy({ top: dir * Math.round(stage.clientHeight * 0.85), behavior: 'auto' });
}

$('rFind').onclick = () => { $('findBar').hidden ? openFind() : closeFind(); };
$('rMark').onclick = addBookmark;
$('rMarks').onclick = () => {
  renderMarks();
  $('marksPanel').hidden = !$('marksPanel').hidden;
};
$('marksClose').onclick = () => { $('marksPanel').hidden = true; };
$('findClose').onclick = closeFind;
$('findInput').addEventListener('input', (e) => {
  clearTimeout(findTimer);
  const q = e.target.value;
  findTimer = setTimeout(() => runFind(q), 180);
});
$('findInput').addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { e.stopPropagation(); closeFind(); }
});

$('rPrev').onclick = () => turn(-1);
$('rNext').onclick = () => turn(1);
document.addEventListener('keydown', (e) => {
  if (!reader.classList.contains('open')) {
    if (e.key === '/') { e.preventDefault(); $('q').focus(); }
    return;
  }
  const k = e.key;
  // Ctrl/Cmd+F or / opens find; Escape closes find before it closes the reader
  if ((e.ctrlKey || e.metaKey) && k === 'f') { e.preventDefault(); openFind(); return; }
  if (k === '/' && document.activeElement !== $('findInput')) { e.preventDefault(); openFind(); return; }
  if (k === 'Escape') {
    if (!$('findBar').hidden) { closeFind(); return; }
    closeReader(); return;
  }
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
  saveProgressSoon();
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
$('resumeClear').onclick = () => {
  writeProgress({});
  renderResume();
};

$('randomBtn').onclick = () => {
  if (!state.catalog.length) return;
  openBook(state.catalog[Math.floor(Math.random() * state.catalog.length)].slug);
};
$('theme').onclick = () => {
  const cur = document.documentElement.getAttribute('data-theme');
  document.documentElement.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
};

boot();
