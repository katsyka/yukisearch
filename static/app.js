(() => {
  const $ = (s) => document.querySelector(s);
  const q = $('#q'), form = $('#form'), sug = $('#sug'), clearBtn = $('#clear');
  const page = $('#page'), res = $('#res'), side = $('#side'), pager = $('#pager'), moreBtn = $('#more');
  const ov = $('#ov'), ovBody = $('#ovBody'), ovSrc = $('#ovSrc'), ovMore = $('#ovMore');

  // ---------- i18n (EN / RU) ----------
  const RU = {
    'All': 'Все', 'Images': 'Картинки', 'News': 'Новости', 'Videos': 'Видео',
    'Search the web': 'Поиск в интернете', 'Search the web. Kopro reads it for you.': 'Ищите в интернете. Kopro прочитает за вас.',
    'Kopro overview': 'Обзор от Kopro', 'Show more': 'Показать ещё', 'Show less': 'Свернуть',
    'More results': 'Ещё результаты', 'More images': 'Ещё картинки', 'Open in Yuki Maps': 'Открыть в Yuki Maps', "This site doesn't let its image load here. Open the page to see it.": 'Этот сайт не даёт показать картинку здесь. Откройте страницу, чтобы её увидеть.', 'More': 'Подробнее', 'Less': 'Свернуть', 'Artist': 'Исполнитель', 'Song': 'Песня', 'fans': 'поклонников', 'Open in YukiMusic': 'Открыть в YukiMusic', 'Play in YukiMusic': 'Слушать в YukiMusic', 'Play preview': 'Слушать отрывок', 'on the map': 'на карте', 'Image': 'Картинка', 'Visit page': 'Открыть страницу', 'Open image': 'Открыть картинку', 'Close': 'Закрыть', 'Previous': 'Назад', 'Next': 'Дальше', 'Top stories': 'Главные новости', 'Videos ': 'Видео ',
    'Nothing found': 'Ничего не нашлось', 'Try other words or check the spelling.': 'Попробуйте другие слова или проверьте написание.',
    'Something went wrong': 'Что-то пошло не так', 'Search is unavailable right now. Try again in a moment.': 'Поиск сейчас недоступен. Попробуйте чуть позже.',
    'Overview is unavailable for this search.': 'Обзор для этого запроса недоступен.', 'Read more': 'Подробнее',
    'Results from': 'Результаты от', 'Overviews by Kopro': 'Обзоры от Kopro', 'Yuki apps': 'Приложения Yuki', 'Clear': 'Очистить',
  };
  let langPref = null;
  try { langPref = localStorage.getItem('ys-lang'); } catch { /* storage may be blocked */ }
  const ru = langPref === 'ru';
  const tr = (s) => (ru && RU[s]) || s;
  if (ru) {
    document.documentElement.lang = 'ru';
    document.querySelectorAll('.tabs a, .tag, .ov-head span, #ovMore span, #more').forEach((el) => { el.textContent = tr(el.textContent); });
    q.placeholder = tr('Search the web');
    document.querySelectorAll('#lb [data-t]').forEach((el) => { const k = el.dataset.t; if (el.tagName === 'BUTTON') el.setAttribute('aria-label', tr(k)); else el.textContent = tr(k); });
    $('#foot span').firstChild.textContent = tr('Results from') + ' ';
    $('#foot span').lastChild.textContent = ' · ' + tr('Overviews by Kopro');
    $('#foot a[href^="https://yuki"]').textContent = tr('Yuki apps'); $('#foot a[href="/about"]').textContent = 'О сервисе';
  }

  const langBtn = $('#langBtn');
  langBtn.textContent = ru ? 'English' : 'Русский';
  langBtn.lang = ru ? 'en' : 'ru';
  langBtn.addEventListener('click', () => {
    try { localStorage.setItem('ys-lang', ru ? 'en' : 'ru'); } catch { /* ignore */ }
    location.reload();
  });

  // example questions on the home page (each opens a search with a Kopro overview)
  const TRY = ru
    ? ['Почему небо голубое?', 'Как работает биткоин?', 'Что такое чёрная дыра?', 'Сколько спать взрослому?', 'Как варить гречку?']
    : ['Why is the sky blue?', 'How does bitcoin work?', 'What is a black hole?', 'How much sleep do adults need?', 'How do I boil an egg?'];
  $('#try').innerHTML = TRY.map((t) => `<button type="button"><svg aria-hidden="true"><use href="#i-spark"/></svg>${t}</button>`).join('');
  $('#try').addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) go(b.textContent, 'web'); });
  if (ru) document.querySelector('.apps').setAttribute('aria-label', 'Приложения Yuki');

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const host = (u) => { try { return new URL(u).hostname.replace(/^www\./, ''); } catch { return ''; } };
  const crumbs = (u) => { try { const x = new URL(u); return (x.hostname.replace(/^www\./, '') + x.pathname.replace(/\/$/, '')).replace(/\//g, ' › '); } catch { return u; } };
  const safeUrl = (u) => (/^https?:\/\//i.test(u || '') ? u : '#');
  const favicon = (r) => {
    const h = host(r.url);
    const src = r.icon || (h ? `https://icons.duckduckgo.com/ip3/${h}.ico` : '');
    return `<span class="fav">${src ? `<img src="${esc(src)}" alt="" loading="lazy" onerror="this.replaceWith(Object.assign(document.createElement('i'),{textContent:'${esc(h[0] || '?')}'}))">` : `<i>${esc(h[0] || '?')}</i>`}</span>`;
  };

  // ---------- state ----------
  let state = { q: '', t: 'web', page: 0 };
  let lbList = [];
  let ovCtl = null, reqId = 0;

  function readUrl() {
    const p = new URLSearchParams(location.search);
    state = { q: (p.get('q') || '').trim(), t: ['web', 'images', 'news', 'videos'].includes(p.get('t')) ? p.get('t') : 'web', page: 0 };
  }
  function urlFor(qv, t) {
    const p = new URLSearchParams({ q: qv });
    if (t && t !== 'web') p.set('t', t);
    return '/search?' + p;
  }
  function go(qv, t, push = true) {
    qv = qv.trim();
    if (!qv) return;
    if (push) history.pushState(null, '', urlFor(qv, t));
    readUrl();
    render();
  }

  // ---------- render ----------
  function setBrandW() {
    const b = $('.brand');
    if (b) document.documentElement.style.setProperty('--brandw', b.offsetWidth + 'px');
  }

  function render() {
    hideSug();
    if (!state.q) {
      document.body.classList.add('home');
      document.title = 'Yuki Search';
      page.hidden = true;
      q.value = '';
      clearBtn.hidden = true;
      setTimeout(() => q.focus(), 0);
      return;
    }
    document.body.classList.remove('home');
    setBrandW();
    document.title = `${state.q} — Yuki Search`;
    q.value = state.q;
    clearBtn.hidden = false;
    page.hidden = false;
    page.classList.toggle('wide', state.t === 'images' || state.t === 'videos');
    document.querySelectorAll('#tabs a').forEach((a) => {
      a.href = urlFor(state.q, a.dataset.t);
      if (a.dataset.t === state.t) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
    res.innerHTML = skeleton();
    lbList = [];
    side.innerHTML = '';
    pager.hidden = true;
    window.scrollTo(0, 0);
    stopOverview();
    ov.hidden = true;
    $('#place').innerHTML = '';
    $('#music').innerHTML = ''; $('#kpTop').innerHTML = ''; stopPreview();
    if (state.t === 'web') { startOverview(state.q); loadPlace(state.q); loadMusic(state.q); loadEntity(state.q); }
    load(false);
  }

  function skeleton() {
    return Array.from({ length: 5 }, () => `<div class="r"><div class="skel" style="width:30%"></div><div class="skel" style="width:70%;height:16px"></div><div class="skel"></div><div class="skel" style="width:85%"></div></div>`).join('');
  }

  async function load(append) {
    const my = ++reqId;
    moreBtn.disabled = true;
    let d;
    try {
      const r = await fetch(`/api/search?type=${state.t}&page=${state.page}&q=${encodeURIComponent(state.q)}${ru ? '&lang=ru' : ''}`);
      d = await r.json();
      if (!r.ok) throw new Error(d.error || r.status);
    } catch (e) {
      if (my !== reqId) return;
      if (!append) res.innerHTML = empty(tr('Something went wrong'), tr('Search is unavailable right now. Try again in a moment.'));
      moreBtn.disabled = false;
      return;
    }
    if (my !== reqId) return;
    $('#srcName').textContent = ({ bing: 'Bing', tavily: 'Tavily', brave: 'Brave' })[d.source] || 'Brave';
    const list = d.results || [];
    if (!append && !list.length) {
      res.innerHTML = empty(d.error ? tr('Something went wrong') : tr('Nothing found'), d.error || tr('Try other words or check the spelling.'));
      return;
    }
    const html = state.t === 'web' ? webHtml(d, append) : state.t === 'images' ? imagesHtml(list) : state.t === 'news' ? newsHtml(list) : videosHtml(list);
    if (append) {
      const box = state.t === 'images' ? res.querySelector('.imgs') : state.t === 'videos' ? res.querySelector('.vids') : res;
      if (box) box.insertAdjacentHTML('beforeend', html);
    } else {
      res.innerHTML = state.t === 'images' ? `<div class="imgs">${html}</div>` : state.t === 'videos' ? `<div class="vids">${html}</div>` : html;
    }
    if (!append && state.t === 'web' && d.infobox) side.innerHTML = infobox(d.infobox);
    pager.hidden = d.more === false || list.length < 8 || state.page >= 9;
    moreBtn.disabled = false;
  }

  function empty(t, s) { return `<div class="empty"><b>${esc(t)}</b>${esc(s)}</div>`; }

  function webHtml(d, append) {
    let out = '';
    d.results.forEach((r, i) => {
      const th = r.thumb ? `<a class="r-th" href="${esc(safeUrl(r.url))}" tabindex="-1" aria-hidden="true"><img src="${esc(r.thumb)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.parentNode.classList.remove('has-th');this.parentNode.remove()"></a>` : '';
      out += `<article class="r${th ? ' has-th' : ''}">
        <a class="r-site" href="${esc(safeUrl(r.url))}" tabindex="-1">${favicon(r)}<span class="r-host"><b>${esc(r.site || host(r.url))}</b><span>${esc(crumbs(r.url))}</span></span></a>
        <h3><a href="${esc(safeUrl(r.url))}">${esc(r.title)}</a></h3>
        <p>${r.age ? `<span class="age">${esc(r.age)} — </span>` : ''}${esc(r.desc)}</p>${th}
      </article>`;
      if (!append && i === 0 && d.images && d.images.length >= 4) { lbList = d.images; out += imgStrip(d.images); }
      if (!append && i === 2 && d.news && d.news.length) out += strip(tr('Top stories'), d.news, false);
      if (!append && i === 5 && d.videos && d.videos.length) out += strip(tr('Videos'), d.videos, true);
    });
    return out;
  }

  function imgStrip(list) {
    return `<section class="istrip"><div class="istrip-h"><h4>${esc(tr('Images'))}</h4><a href="${esc(urlFor(state.q, 'images'))}" data-tab="images">${esc(tr('More images'))} →</a></div>
      <div class="istrip-row">${list.slice(0, 10).map((m, i) => `<button type="button" data-lb="${i}" aria-label="${esc(m.title || tr('Image'))}"><img src="${esc(m.thumb)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.remove()"></button>`).join('')}</div></section>`;
  }

  function strip(title, items, video) {
    return `<section class="strip"><h4>${esc(title)}</h4><div class="strip-row">${items.map((n) => tile(n, video)).join('')}</div></section>`;
  }
  function tile(n, video) {
    return `<a class="tile" href="${esc(safeUrl(n.url))}">
      <div class="th">${n.thumb ? `<img src="${esc(n.thumb)}" alt="" loading="lazy" onerror="this.remove()">` : ''}${video ? '<span class="pl"><svg><use href="#i-play"/></svg></span>' : ''}</div>
      <b>${esc(n.title)}</b><span>${esc(n.site || host(n.url))}${n.age ? ' · ' + esc(n.age) : ''}</span></a>`;
  }
  function imagesHtml(list) {
    const base = lbList.length;
    lbList = lbList.concat(list.filter((r) => r.thumb));
    return list.filter((r) => r.thumb).map((r, i) => `<a href="${esc(safeUrl(r.url))}" title="${esc(r.title)}" data-lb="${base + i}"><img src="${esc(r.thumb)}" alt="${esc(r.title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.remove()"><span>${esc(r.site || host(r.url))}</span></a>`).join('');
  }
  function newsHtml(list) {
    return list.map((n) => `<a class="nw" href="${esc(safeUrl(n.url))}"><div>
      <div class="src">${esc(n.site || host(n.url))}${n.age ? ' · ' + esc(n.age) : ''}</div>
      <h3>${esc(n.title)}</h3><p>${esc(n.desc)}</p></div>
      ${n.thumb ? `<div class="th"><img src="${esc(n.thumb)}" alt="" loading="lazy"></div>` : '<div></div>'}</a>`).join('');
  }
  function videosHtml(list) { return list.map((v) => tile(v, true)).join(''); }
  function infobox(ib) {
    return `<div class="ib">${ib.thumb ? `<img src="${esc(ib.thumb)}" alt="">` : ''}<div><h2>${esc(ib.title)}</h2><p>${esc(ib.desc)}</p>${ib.url ? `<a href="${esc(safeUrl(ib.url))}">${tr('Read more')} →</a>` : ''}</div></div>`;
  }

  moreBtn.addEventListener('click', () => { state.page++; load(true); });

  // ---------- music card (artists and songs) ----------
  const player = new Audio();
  let playing = null;
  function stopPreview() { player.pause(); if (playing) playing.querySelector('use').setAttribute('href', '#i-play'); playing = null; }
  player.addEventListener('ended', stopPreview);
  const ym = (q) => 'https://music.yukichat.lol/search?q=' + encodeURIComponent(q);
  const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  const fans = (n) => n >= 1e6 ? (n / 1e6).toFixed(1).replace(/\.0$/, '') + (ru ? ' млн' : 'M') : n >= 1e3 ? Math.round(n / 1e3) + (ru ? ' тыс.' : 'K') : String(n);
  const playBtn = (t) => t.preview ? `<button type="button" class="mu-play" data-src="${esc(t.preview)}" aria-label="${esc(tr('Play preview'))}: ${esc(t.title)}"><svg><use href="#i-play"/></svg></button>` : '';
  async function loadMusic(query) {
    try {
      const m = await (await fetch('/api/music?q=' + encodeURIComponent(query))).json();
      if (!m || !m.kind || state.q !== query || state.t !== 'web') return;
      if (m.kind === 'artist') {
        $('#music').innerHTML = `<section class="mu" aria-label="${esc(m.name)}">
          <div class="mu-head"><img class="mu-pic round" src="${esc(m.pic)}" alt="" width="96" height="96">
            <div><small>${esc(tr('Artist'))}</small><h3>${esc(m.name)}</h3><span>${esc(fans(m.fans))} ${esc(tr('fans'))}</span></div>
            <a class="mu-open" href="${esc(ym(m.name))}"><img src="https://yuki.yukichat.lol/img/ic-music.png" alt="" width="20" height="20">${esc(tr('Open in YukiMusic'))}</a></div>
          <ol class="mu-list">${m.tracks.map((t) => `<li>${playBtn(t)}<img src="${esc(t.cover)}" alt="" width="40" height="40" loading="lazy"><b>${esc(t.title)}</b><span>${t.dur ? mmss(t.dur) : ''}</span><a href="${esc(ym(t.artist + ' ' + t.title))}" aria-label="${esc(tr('Play in YukiMusic'))}: ${esc(t.title)}">${esc(tr('Play in YukiMusic'))}</a></li>`).join('')}</ol>
        </section>`;
      } else {
        $('#music').innerHTML = `<section class="mu" aria-label="${esc(m.title)}">
          <div class="mu-head"><img class="mu-pic" src="${esc(m.cover)}" alt="" width="96" height="96">
            <div><small>${esc(tr('Song'))}</small><h3>${esc(m.title)}</h3><span>${esc(m.artist)} · ${esc(m.album)}${m.dur ? ' · ' + mmss(m.dur) : ''}</span></div>
            <div class="mu-acts">${playBtn(m)}<a class="mu-open" href="${esc(ym(m.artist + ' ' + m.title))}"><img src="https://yuki.yukichat.lol/img/ic-music.png" alt="" width="20" height="20">${esc(tr('Play in YukiMusic'))}</a></div></div>
        </section>`;
      }
    } catch { /* no card */ }
  }
  $('#music').addEventListener('click', (e) => {
    const b = e.target.closest('.mu-play');
    if (!b) return;
    if (playing === b) { stopPreview(); return; }
    stopPreview();
    player.src = b.dataset.src;
    player.play().then(() => { playing = b; b.querySelector('use').setAttribute('href', '#i-pause'); }).catch(() => {});
  });

  // ---------- knowledge panel (people, companies, things) ----------
  async function loadEntity(query) {
    try {
      const k = await (await fetch('/api/entity?q=' + encodeURIComponent(query))).json();
      if (!k || !k.title || state.q !== query || state.t !== 'web') return;
      const html = `<aside class="kp" aria-label="${esc(k.title)}">
        <div class="kp-head">${k.img ? `<img class="kp-img" src="${esc(k.img)}" alt="${esc(k.title)}" referrerpolicy="no-referrer" onerror="this.remove()">` : ''}
          <div class="kp-name"><h2>${esc(k.title)}</h2>${k.desc ? `<p class="kp-desc">${esc(k.desc)}</p>` : ''}</div></div>
        <div class="kp-body"><p class="kp-ex">${esc(k.extract)} ${k.url ? `<a href="${esc(safeUrl(k.url))}">Wikipedia</a>` : ''}</p>
          <div class="kp-more">${k.facts && k.facts.length ? `<dl>${k.facts.map(([a, b]) => `<div><dt>${esc(a)}</dt><dd>${esc(b)}</dd></div>`).join('')}</dl>` : ''}
          ${k.site ? `<a class="kp-site" href="${esc(safeUrl(k.site))}">${esc(host(k.site))} ↗</a>` : ''}</div>
          <button type="button" class="kp-tog" aria-expanded="false"><span>${esc(tr('More'))}</span><svg aria-hidden="true"><use href="#i-chev"/></svg></button></div></aside>`;
      const wide = matchMedia('(min-width: 1181px)').matches;
      const box = wide ? side : $('#kpTop');
      box.innerHTML = html;
      const kp = box.querySelector('.kp'), tog = kp.querySelector('.kp-tog');
      tog.addEventListener('click', () => {
        const open = kp.classList.toggle('open');
        tog.setAttribute('aria-expanded', open);
        tog.querySelector('span').textContent = tr(open ? 'Less' : 'More');
      });
    } catch { /* no panel */ }
  }

  // ---------- Yuki Maps card for place searches ----------
  async function loadPlace(query) {
    try {
      const p = await (await fetch('/api/place?q=' + encodeURIComponent(query))).json();
      if (!p || !isFinite(p.lat) || state.q !== query || state.t !== 'web') return;
      const at = `${p.zoom}/${(+p.lat).toFixed(5)}/${(+p.lon).toFixed(5)}`;
      const open = `https://maps.yukichat.lol/?pin=${p.lat},${p.lon}&n=${encodeURIComponent(p.name)}#map=${at}`;
      $('#place').innerHTML = `<section class="pl" aria-label="${esc(p.name)} ${esc(tr('on the map'))}">
        <a class="pl-map" href="${esc(open)}" aria-label="${esc(tr('Open in Yuki Maps'))}"><iframe src="https://maps.yukichat.lol/?embed&amp;pin=${p.lat},${p.lon}#map=${at}" title="${esc(p.name)}" loading="lazy" tabindex="-1"></iframe></a>
        <div class="pl-cap"><div><b>${esc(p.name)}</b><span>${esc(p.desc)}</span></div>
          <a class="pl-btn" href="${esc(open)}"><img src="https://yuki.yukichat.lol/img/ic-maps.svg" alt="" width="20" height="20">${esc(tr('Open in Yuki Maps'))}</a></div>
      </section>`;
    } catch { /* no card, no problem */ }
  }

  // ---------- overview ----------
  let sources = [];
  function stopOverview() { if (ovCtl) { ovCtl.close(); ovCtl = null; } }

  function md(text, done) {
    const lines = esc(text).split('\n');
    let out = '', list = null;
    const inline = (s) => s
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/(^|[^*])\*(?!\s)(.+?)\*/g, '$1<em>$2</em>')
      .replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (m, nums) => nums.split(/\s*,\s*/).map((n) => {
        const s = sources[+n - 1];
        return s ? `<a class="cite" href="${esc(safeUrl(s.url))}" title="${esc(s.title)}">${n}</a>` : '';
      }).join(''));
    for (const raw of lines) {
      const l = raw.trim();
      const m = l.match(/^(?:[-*•]|\d+[.)])\s+(.*)/);
      if (m) {
        const kind = /^\d/.test(l) ? 'ol' : 'ul';
        if (list !== kind) { if (list) out += `</${list}>`; out += `<${kind}>`; list = kind; }
        out += `<li>${inline(m[1])}</li>`;
      } else {
        if (list) { out += `</${list}>`; list = null; }
        if (l) out += `<p>${inline(l)}</p>`;
      }
    }
    if (list) out += `</${list}>`;
    if (!done) out = out.replace(/(<\/(?:p|li)>)(?:<\/[uo]l>)?$/, (m) => '<span class="cursor"></span>' + m);
    return out;
  }

  function startOverview(query) {
    let text = '';
    sources = [];
    ovBody.className = 'ov-body';
    ovBody.innerHTML = '<div class="skel" style="width:92%"></div><div class="skel" style="width:80%"></div><div class="skel" style="width:60%"></div>';
    ovSrc.innerHTML = '';
    ovMore.hidden = true;
    ov.hidden = false;
    const es = new EventSource('/api/overview?q=' + encodeURIComponent(query));
    ovCtl = es;
    es.onmessage = (ev) => {
      if (ovCtl !== es) return es.close();
      const d = JSON.parse(ev.data);
      if (d.sources) {
        sources = d.sources;
      }
      if (d.t) { text += d.t; if (/^\s*N(O(_(A(N(S(W(E(R)?)?)?)?)?)?)?)?\s*$/.test(text)) return; ovBody.innerHTML = md(text, false); }
      if (d.error && !text) { ovBody.innerHTML = `<p class="ov-err">${esc(tr('Overview is unavailable for this search.'))}</p>`; }
      if (d.done) {
        es.close(); ovCtl = null;
        if (d.skip || (!text && !d.error) || /^\s*NO_ANSWER/.test(text)) { ov.hidden = true; return; }
        if (text) finishOverview(text);
      }
    };
    es.onerror = () => { es.close(); if (ovCtl === es) { ovCtl = null; if (!text) ov.hidden = true; else finishOverview(text); } };
  }

  function finishOverview(text) {
    ovBody.innerHTML = md(text, true);
    const used = new Set([...text.matchAll(/\[(\d+(?:\s*,\s*\d+)*)\]/g)].flatMap((m) => m[1].split(/\s*,\s*/).map(Number)));
    const list = sources.filter((s) => used.has(s.n));
    ovSrc.innerHTML = list.map((s) => `<a href="${esc(safeUrl(s.url))}" title="${esc(s.title)}"><b>${s.n}</b><span>${esc(s.site || host(s.url))}</span></a>`).join('');
    requestAnimationFrame(() => {
      if (ovBody.scrollHeight > ovBody.clientHeight + 4 || ovBody.scrollHeight > 230) {
        ovBody.classList.add('clip');
        ovMore.hidden = false;
        ovMore.classList.remove('up');
        ovMore.querySelector('span').textContent = tr('Show more');
      }
    });
  }
  ovMore.addEventListener('click', () => {
    const open = ovBody.classList.toggle('clip');
    ovMore.classList.toggle('up', !open);
    ovMore.querySelector('span').textContent = open ? tr('Show more') : tr('Show less');
  });

  // ---------- image preview ----------
  const lb = $('#lb'), lbImg = $('#lbImg');
  let lbAt = 0;
  function lbShow(i) {
    if (!lbList.length) return;
    lbAt = (i + lbList.length) % lbList.length;
    const m = lbList[lbAt];
    lbImg.classList.remove('on');
    $('#lbErr').hidden = true;
    lbImg.hidden = false;
    lbImg.onload = () => lbImg.classList.add('on');
    lbImg.onerror = () => { lbImg.hidden = true; $('#lbErr').hidden = false; };
    lbImg.src = m.thumb;
    lbImg.alt = m.title || '';
    $('#lbTitle').textContent = m.title || state.q;
    $('#lbSite').textContent = m.site || host(m.url);
    $('#lbVisit').href = safeUrl(m.page || m.url);
    $('#lbOpen').href = safeUrl(m.thumb);
    $('#lbCount').textContent = `${lbAt + 1} / ${lbList.length}`;
    $('#lbPrev').hidden = $('#lbNext').hidden = lbList.length < 2;
    if (!lb.open) lb.showModal();
  }
  res.addEventListener('click', (e) => {
    const a = e.target.closest('[data-lb]');
    if (a && !e.ctrlKey && !e.metaKey && !e.shiftKey) { e.preventDefault(); lbShow(+a.dataset.lb); return; }
    const t = e.target.closest('[data-tab]');
    if (t && !e.ctrlKey && !e.metaKey) { e.preventDefault(); go(state.q, t.dataset.tab); }
  });
  $('#lbPrev').addEventListener('click', () => lbShow(lbAt - 1));
  $('#lbNext').addEventListener('click', () => lbShow(lbAt + 1));
  $('#lbClose').addEventListener('click', () => lb.close());
  lb.addEventListener('click', (e) => { if (e.target === lb) lb.close(); });
  lb.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') lbShow(lbAt - 1);
    else if (e.key === 'ArrowRight') lbShow(lbAt + 1);
  });
  let tx = 0;
  lb.addEventListener('touchstart', (e) => { tx = e.touches[0].clientX; }, { passive: true });
  lb.addEventListener('touchend', (e) => { const dx = e.changedTouches[0].clientX - tx; if (Math.abs(dx) > 50) lbShow(lbAt + (dx < 0 ? 1 : -1)); });

  // ---------- suggestions ----------
  let sugItems = [], sugIdx = -1, sugTimer = 0, sugSeq = 0;
  function hideSug() { sug.hidden = true; form.classList.remove('open'); sugIdx = -1; q.removeAttribute('aria-activedescendant'); }
  function showSug(items, typed) {
    sugItems = items; sugIdx = -1;
    if (!items.length || document.activeElement !== q) return hideSug();
    const t = typed.toLowerCase();
    sug.innerHTML = items.map((s, i) => {
      const rest = s.toLowerCase().startsWith(t) ? `${esc(s.slice(0, t.length))}<b>${esc(s.slice(t.length))}</b>` : esc(s);
      return `<li role="option" id="sg${i}" data-i="${i}"><svg><use href="#i-search"/></svg><span>${rest}</span></li>`;
    }).join('');
    sug.hidden = false; form.classList.add('open');
  }
  function markSug() {
    sug.querySelectorAll('li').forEach((li, i) => li.setAttribute('aria-selected', i === sugIdx));
    if (sugIdx >= 0) { q.value = sugItems[sugIdx]; q.setAttribute('aria-activedescendant', 'sg' + sugIdx); }
  }
  let typed = '';
  q.addEventListener('input', () => {
    typed = q.value;
    clearBtn.hidden = !q.value;
    clearTimeout(sugTimer);
    const v = q.value.trim();
    if (!v) return hideSug();
    sugTimer = setTimeout(async () => {
      const my = ++sugSeq;
      try {
        const r = await fetch('/api/suggest?q=' + encodeURIComponent(v));
        const items = await r.json();
        if (my === sugSeq) showSug(items.filter((s) => s.toLowerCase() !== v.toLowerCase()).slice(0, 8), v);
      } catch { /* suggestions are optional */ }
    }, 110);
  });
  q.addEventListener('keydown', (e) => {
    if (sug.hidden) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const n = sugItems.length;
      sugIdx = e.key === 'ArrowDown' ? (sugIdx + 1 >= n ? -1 : sugIdx + 1) : (sugIdx - 1 < -1 ? n - 1 : sugIdx - 1);
      if (sugIdx === -1) q.value = typed;
      markSug();
    } else if (e.key === 'Escape') { q.value = typed; hideSug(); }
  });
  q.addEventListener('blur', () => setTimeout(hideSug, 150));
  sug.addEventListener('mousedown', (e) => {
    const li = e.target.closest('li');
    if (!li) return;
    e.preventDefault();
    go(sugItems[+li.dataset.i], state.q ? state.t : 'web');
    q.blur();
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const v = q.value.trim();
    if (!v) return;
    go(v, state.q ? state.t : 'web');
    q.blur();
  });
  clearBtn.addEventListener('click', () => { q.value = ''; typed = ''; clearBtn.hidden = true; hideSug(); q.focus(); });
  $('#tabs').addEventListener('click', (e) => {
    const a = e.target.closest('a');
    if (!a || e.metaKey || e.ctrlKey) return;
    e.preventDefault();
    if (a.dataset.t !== state.t) go(state.q, a.dataset.t);
  });
  $('.brand').addEventListener('click', (e) => {
    if (e.metaKey || e.ctrlKey) return;
    e.preventDefault();
    history.pushState(null, '', '/');
    readUrl(); render();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement !== q && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) {
      e.preventDefault(); q.focus(); q.select();
    }
  });
  window.addEventListener('popstate', () => { readUrl(); render(); });
  window.addEventListener('resize', setBrandW);
  document.fonts && document.fonts.ready.then(setBrandW);

  // Phones: the header slides away while you scroll down and comes back when you scroll up.
  let lastY = 0;
  addEventListener('scroll', () => {
    const y = scrollY, small = innerWidth <= 860;
    document.body.classList.toggle('bar-off', small && y > 140 && y > lastY && !document.body.classList.contains('home') && document.activeElement !== q);
    lastY = y;
  }, { passive: true });

  readUrl();
  render();
})();
