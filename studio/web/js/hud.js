// SPDX-License-Identifier: GPL-3.0-or-later
// The game interface screen: a game copy's in-game HUD (the main screen and its panels, normal or
// minimised) drawn as the game draws it, at a chosen screen size and culture; its gadgets as a
// tree; the one under the mouse or chosen in the tree outlined, with everything it says.
import { api, clear, fetchBlob, h, storeGet, storeSet, t, toast } from './core.js';
import { ASSUMED, HudRenderer, displayText, fontAt } from './hud_render.js';

const SIZES = ['1024x768', '1280x720', '1280x768', '1280x800', '1280x1024', '1366x768', '1600x900', '1680x1050', '1920x1080'];

export async function hudScreen(main, app) {
  clear(main);
  const saved = storeGet('hud', { variant: 'min', culture: 'Eur', size: '1280x720', showHidden: false, outlines: false });
  const moments = storeGet('hud.moments', {}), oneOf = storeGet('hud.oneOf', {});
  const momentsBox = h('details', { class: 'hud-moments small' }, h('summary', { text: t('h.moments') }));
  let scene = null, renderer = null, list = [], selected = null, hover = null, frame = null;
  const images = new Map(), faces = new Map(), ratios = new Map();
  // textures are fetched a few at a time: a scene names over a hundred
  const queue = []; let active = 0;
  function fetchSoon(url, done) { queue.push([url, done]); pump(); }
  function pump() {
    while (active < 6 && queue.length) {
      const [url, done] = queue.shift();
      active++;
      fetchBlob(url).then(b => (b ? createImageBitmap(b) : null)).catch(() => null)
        .then(img => { active--; done(img); pump(); });
    }
  }
  let view = { zoom: 1, x: 0, y: 0, fitted: false };

  const variant = h('select', { onchange: () => { keep(); open(); } },
    [['min', t('h.min')], ['normal', t('h.normal')]].map(([v, l]) => h('option', { value: v, selected: v === saved.variant, text: l })));
  const culture = h('select', { onchange: () => { keep(); redraw(); } },
    [['Eur', t('h.eur')], ['Nat', t('h.nat')], ['Asi', t('h.asi')]].map(([v, l]) => h('option', { value: v, selected: v === saved.culture, text: l })));
  const size = h('select', { onchange: () => { keep(); view.fitted = false; redraw(); } },
    SIZES.map(s => h('option', { value: s, selected: s === saved.size, text: s.replace('x', ' × ') })));
  const showHidden = h('input', { type: 'checkbox', checked: saved.showHidden, onchange: () => { keep(); redraw(); } });
  const outlines = h('input', { type: 'checkbox', checked: saved.outlines, onchange: () => { keep(); redraw(); } });
  const search = h('input', { type: 'search', class: 'grow', placeholder: t('h.search'), oninput: () => drawTree() });
  const tree = h('div', { class: 'hud-tree' });
  const stage = h('div', { class: 'viewport hud-stage' });
  const canvas = h('canvas', { tabindex: 0, 'aria-label': t('h.stage') });
  stage.append(canvas);
  const details = h('div', { class: 'hud-details stack' });
  const status = h('span', { class: 'small muted' });
  const notes = h('details', { class: 'small' }, h('summary', { text: t('h.assumed') }),
    h('ul', {}, Object.values(ASSUMED).map(s => h('li', { text: s }))));

  main.append(h('div', { class: 'head' }, h('div', {},
    h('button', { type: 'button', class: 'ghost small', text: '← ' + t('nav.art'), onclick: () => app.go('art') }),
    h('h1', { text: t('h.title') }), h('p', { class: 'muted', text: t('h.intro') }))),
    h('div', { class: 'card row hud-bar' },
      h('label', { class: 'small' }, t('h.variant') + ' ', variant),
      h('label', { class: 'small' }, t('h.culture') + ' ', culture),
      h('label', { class: 'small' }, t('h.size') + ' ', size),
      h('label', { class: 'small row' }, showHidden, t('h.hidden')),
      h('label', { class: 'small row' }, outlines, t('h.outlines')),
      momentsBox,
      h('button', { type: 'button', class: 'small', text: t('h.fit'), onclick: () => { view.fitted = false; paint(); } }),
      h('button', { type: 'button', class: 'small', text: t('h.snapshot'), onclick: () => snapshot() }),
      status),
    h('div', { class: 'hud-body' },
      h('div', { class: 'card stack hud-left' }, h('div', { class: 'row' }, search), tree),
      h('div', { class: 'stack' }, stage, notes),
      h('div', { class: 'card hud-right' }, details)));

  function keep() {
    storeSet('hud', { variant: variant.value, culture: culture.value, size: size.value, showHidden: showHidden.checked, outlines: outlines.checked });
  }
  function dims() { const [w, hh] = size.value.split('x').map(Number); return [w, hh]; }
  function opts() {
    return { variant: scene.variant, culture: culture.value, showHidden: showHidden.checked, backdrop: '#3a4a2a',
      moments: Object.fromEntries(scene.rules.moments.map(m => [m.id, moments[m.id] ?? m.on])),
      oneOf: Object.fromEntries(scene.rules.oneOf.map(o => [o.re, oneOf[o.re] || o.show])) };
  }

  // ---- assets: textures as bitmaps, the copy's typefaces as fonts of the page
  const assets = {
    image(path) {
      const key = path.toLowerCase();
      if (!images.has(key)) {
        images.set(key, undefined);
        fetchSoon(`/api/hud/texture?s=${scene.session}&path=${encodeURIComponent(path)}`,
          img => { images.set(key, img); redrawSoon(); });
      }
      return images.get(key);
    },
    face(face) { return faces.get((face || '').toLowerCase()) || face; },
    // [ascent, descent] of a typeface per pixel of em, from the font itself
    metrics(family) {
      if (!ratios.has(family)) {
        const c = document.createElement('canvas').getContext('2d');
        c.font = `100px "${family}", Arial`;
        const m = c.measureText('Hg');
        ratios.set(family, [(m.fontBoundingBoxAscent || 90) / 100, (m.fontBoundingBoxDescent || 21) / 100]);
      }
      return ratios.get(family);
    },
  };

  async function loadFaces() {
    for (const face of scene.faces) {
      if (faces.has(face)) continue;
      try {
        const blob = await fetchBlob(`/api/hud/font?s=${scene.session}&face=${encodeURIComponent(face)}`);
        if (!blob) continue;
        const family = 'aoe3 ' + face;
        const ff = new FontFace(family, await blob.arrayBuffer());
        await ff.load();
        document.fonts.add(ff);
        faces.set(face, family);
        ratios.delete(family);
      } catch { /* a typeface the page cannot load: the system font stands in */ }
    }
  }

  async function open() {
    if (!app.state.settings.paths.game) {          // nothing to read yet: say where to set it
      clear(details).append(h('p', { class: 'notice', text: t('h.nogame') }),
        h('button', { type: 'button', class: 'primary', text: t('nav.settings'), onclick: () => app.go('settings') }));
      return;
    }
    status.textContent = t('b.working');
    try {
      scene = await api('/api/hud/open', { variant: variant.value });
      images.clear();
      renderer = new HudRenderer(scene, assets);
      drawMoments();
      selected = hover = null;
      await loadFaces();
      view.fitted = false;
      drawTree();
      redraw();
      drawDetails();
    } catch (e) {
      status.textContent = '';
      clear(details).append(h('p', { class: 'notice bad', text: e.message }));
      toast(e.message, 'bad');
    }
  }

  // ---- drawing: the frame at the screen's pixels, then shown zoomed in the stage
  let pending = 0;
  function redrawSoon() { if (!pending) pending = requestAnimationFrame(() => { pending = 0; redraw(); }); }
  function redraw() {
    if (!scene) return;
    const [w, hh] = dims();
    frame = frame || document.createElement('canvas');
    frame.width = w; frame.height = hh;
    const r = renderer.draw(frame.getContext('2d'), w, hh, opts());
    list = r.list;
    const loading = [...images.values()].filter(v => v === undefined).length;
    status.textContent = t('h.status', { n: list.length, files: scene.files.length })
      + (r.missing.textures.size ? ' · ' + t('h.missingtex', { n: r.missing.textures.size }) : '')
      + (r.missing.fonts.size ? ' · ' + t('h.missingfont', { list: [...r.missing.fonts].join(', ') }) : '')
      + (loading ? ' · ' + t('h.loading', { n: loading }) : '');
    paint();
  }

  const ctx = canvas.getContext('2d');
  function fit() {
    const [w, hh] = dims();
    const cw = stage.clientWidth, ch = stage.clientHeight;
    view.zoom = Math.min(cw / w, ch / hh) * 0.98;
    view.x = (cw - w * view.zoom) / 2; view.y = (ch - hh * view.zoom) / 2;
    view.fitted = true;
  }
  function paint() {
    const dpr = window.devicePixelRatio || 1;
    const cw = stage.clientWidth, ch = stage.clientHeight;
    if (!cw || !ch) return;
    canvas.width = Math.round(cw * dpr); canvas.height = Math.round(ch * dpr);
    canvas.style.width = cw + 'px'; canvas.style.height = ch + 'px';
    if (!view.fitted) fit();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);
    if (!frame) return;
    ctx.imageSmoothingEnabled = view.zoom < 1;
    ctx.drawImage(frame, view.x, view.y, frame.width * view.zoom, frame.height * view.zoom);
    const box = (g, colour, width) => {
      const hit = list.find(e => e[0] === g);
      if (!hit) return;
      const [, x, y, w, hh] = hit;
      ctx.strokeStyle = colour; ctx.lineWidth = width;
      ctx.strokeRect(view.x + x * view.zoom, view.y + y * view.zoom, w * view.zoom, hh * view.zoom);
    };
    if (outlines.checked) for (const [g] of list) box(g, 'rgba(120,200,255,0.35)', 1);
    if (hover && hover !== selected) box(hover, 'rgba(255,255,255,0.8)', 1);
    if (selected) box(selected, '#ffcc33', 2);
  }
  const resizer = new ResizeObserver(() => { view.fitted = false; paint(); });
  resizer.observe(stage);
  app.onLeave(() => resizer.disconnect());

  const toFrame = e => { const b = canvas.getBoundingClientRect(); return [(e.clientX - b.left - view.x) / view.zoom, (e.clientY - b.top - view.y) / view.zoom]; };
  let drag = null;
  canvas.addEventListener('pointermove', e => {
    if (drag) { view.x = drag.vx + e.clientX - drag.x; view.y = drag.vy + e.clientY - drag.y; view.fitted = true; paint(); return; }
    if (!renderer) return;
    const [x, y] = toFrame(e);
    const g = renderer.hit(list, x, y);
    if (g !== hover) { hover = g; paint(); canvas.title = g ? g.name : ''; }
  });
  canvas.addEventListener('pointerdown', e => {
    if (e.button === 1 || e.button === 2 || e.altKey) { drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; canvas.setPointerCapture(e.pointerId); return; }
    if (!renderer) return;
    const [x, y] = toFrame(e);
    select(renderer.hit(list, x, y));
  });
  canvas.addEventListener('pointerup', () => { drag = null; });
  canvas.addEventListener('contextmenu', e => e.preventDefault());
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    const b = canvas.getBoundingClientRect();
    const mx = e.clientX - b.left, my = e.clientY - b.top;
    const k = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    view.x = mx - (mx - view.x) * k; view.y = my - (my - view.y) * k; view.zoom *= k; view.fitted = true;
    paint();
  }, { passive: false });

  function select(g) {
    selected = g;
    paint();
    drawDetails();
    drawTree();
    if (g) tree.querySelector(`[data-id="${g.id}"]`)?.scrollIntoView({ block: 'nearest' });
  }

  // ---- the tree: each file, its gadgets nested as the game reads them
  function drawTree() {
    clear(tree);
    if (!scene) return;
    const word = search.value.trim().toLowerCase();
    const shown = new Set(list.map(e => e[0].id));
    scene.files.forEach((f, i) => {
      const items = scene.gadgets.filter(g => g.file === i && (!word || g.name.toLowerCase().includes(word)));
      const depth = g => { let d = 0; for (let p = g.parent; p !== null && p !== undefined; p = scene.gadgets[p].parent) d++; return d; };
      tree.append(h('div', { class: 'hud-file small', title: f.where, text: `${f.stem} · ${items.length}` }),
        ...items.slice(0, word ? 400 : 2000).map(g => h('button', {
          type: 'button', 'data-id': g.id,
          class: 'hud-node' + (g === selected ? ' on' : '') + (shown.has(g.id) ? '' : ' off'),
          style: { paddingLeft: (6 + (word ? 0 : depth(g) * 10)) + 'px' },
          title: g.type, onclick: () => select(g),
        }, g.name || '(' + g.type + ')')));
    });
  }

  // ---- the moments of a game the engine shows gadgets for (aoe3game/uidata/hud_scene.json)
  function drawMoments() {
    clear(momentsBox).append(h('summary', { text: t('h.moments') }));
    const lang = document.documentElement.lang === 'es' ? 'es' : 'en';
    const box = h('div', { class: 'stack' });
    for (const m of scene.rules.moments) {
      box.append(h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: moments[m.id] ?? m.on,
        onchange: e => { moments[m.id] = e.target.checked; storeSet('hud.moments', moments); redraw(); } }), m[lang] || m.en));
    }
    for (const o of scene.rules.oneOf) {
      box.append(h('label', { class: 'row' }, (o[lang] || o.en) + ' ', h('select', { onchange: e => { oneOf[o.re] = e.target.value; storeSet('hud.oneOf', oneOf); redraw(); } },
        o.choices.map(c => h('option', { value: c, selected: c === (oneOf[o.re] || o.show), text: c })))));
    }
    momentsBox.append(box);
  }

  // ---- what the chosen gadget says: its properties, or where each thing it names leads
  let tab = storeGet('hud.tab', 'refs');
  function drawDetails() {
    clear(details);
    if (!scene) return;
    if (!selected) { details.append(h('p', { class: 'small muted', text: t('h.pick') })); return; }
    const g = selected;
    const tabs = h('div', { class: 'row' }, [['refs', t('h.refs')], ['props', t('h.props')]].map(([k, l]) =>
      h('button', { type: 'button', class: 'small' + (tab === k ? ' primary' : ''), text: l,
        onclick: () => { tab = k; storeSet('hud.tab', k); drawDetails(); } })));
    details.append(h('h3', { text: g.name || '(' + g.type + ')' }), tabs);
    if (tab === 'refs') drawRefs(g); else drawProps(g);
  }

  async function drawRefs(g) {
    const box = h('div', { class: 'stack hud-refs small' }, h('p', { class: 'muted', text: t('b.working') }));
    details.append(box);
    let r;
    try { r = await api('/api/hud/refs', { session: scene.session, id: g.id, width: dims()[0] }); }
    catch (e) { clear(box).append(h('p', { class: 'bad', text: e.message })); return; }
    if (selected !== g) return;
    const lang = document.documentElement.lang === 'es' ? 'es' : 'en';
    const short = p => String(p).replace(/^.*[\\/](data|art)[\\/]/i, '$1\\');
    const sec = (title, ...items) => h('section', {}, h('h4', { text: title }), ...items);
    clear(box);
    box.append(sec(t('h.r.file'), h('p', { class: 'mono', text: `${short(r.file.where)} · ${t('h.line')} ${r.file.line}` }),
      r.file.hidden.length ? h('p', { class: 'muted', text: t('h.r.hides', { list: r.file.hidden.map(short).join(', ') }) }) : null));
    if (r.engine.length) {
      box.append(sec(t('h.r.engine'), ...r.engine.map(e => h('div', {}, h('p', { text: e[lang] }),
        h('p', { class: 'muted', text: t('h.r.when') + ' ' + e.when[lang] })))));
    }
    if (r.strings.length) {
      box.append(sec(t('h.r.strings'), ...r.strings.map(s => h('p', {},
        h('span', { class: 'mono', text: `$$${s.id}$$ ` }), t('h.r.in.' + s.in) + ': ',
        s.found ? h('strong', { text: `“${s.text}”` }) : h('span', { class: 'bad', text: t('h.r.nostring', { fallback: s.fallback }) }),
        s.symbol ? h('span', { class: 'muted mono', text: ` (${s.symbol})` }) : null))));
    }
    if (r.textures.length) {
      box.append(sec(t('h.r.textures'), ...r.textures.map(x => {
        const img = h('img', { class: 'hud-thumb', alt: x.path });
        if (x.found.length) fetchBlob(`/api/hud/texture?s=${scene.session}&path=${encodeURIComponent(x.path)}`).then(b => { if (b && b.size) img.src = URL.createObjectURL(b); });
        return h('div', { class: 'row', style: { alignItems: 'flex-start' } }, img, h('div', { class: 'grow' },
          h('p', {}, h('strong', { text: t('h.r.role.' + x.role.split(' ')[0], null, x.role) + (x.role.includes(' ') ? ' ' + x.role.split(' ')[1] : '') + ': ' }), h('span', { class: 'mono', text: x.path })),
          x.found.length ? h('p', { class: 'muted mono', text: '→ ' + short(x.found[0]) + (x.size ? ` · ${x.size[0]} × ${x.size[1]}` : '') + (x.crop ? ` · texturecoords ${x.crop}` : '') })
            : h('p', { class: 'bad', text: t('h.r.notex') }),
          x.hidden.length ? h('p', { class: 'muted', text: t('h.r.hides', { list: x.hidden.map(short).join(', ') }) }) : null));
      })));
    }
    if (r.font) {
      const f = r.font;
      box.append(sec(t('h.r.font'),
        h('p', {}, h('span', { class: 'mono', text: f.asked }), ' → ',
          f.found ? h('span', { text: `${f.entry}` }) : h('span', { class: 'warn', text: t('h.r.nofont', { entry: f.entry }) })),
        h('p', { class: 'muted', text: t('h.r.face', { face: f.typeface, file: f.file ? short(f.file) : t('h.r.system'), cell: f.cell, resx: f.resx }) + (f.bold ? ' · bold' : '') })));
    }
    if (r.live.length) {
      box.append(sec(t('h.r.live'), ...r.live.map(l => h('div', {},
        h('p', {}, h('span', { class: 'mono', text: l.text }), ' ', !l.known ? h('span', { class: 'warn', text: t('h.r.unknownfn') })
          : l.works ? h('span', { text: l[lang] }) : h('span', { class: 'bad', text: t('h.r.stub') + ' ' + l[lang] })),
        l.proto ? h('p', { class: 'muted', text: t('h.r.reads', { field: l.proto }) }) : null))));
    }
    if (r.commands.length) box.append(sec(t('h.r.commands'), ...r.commands.map(c => h('p', { class: 'mono', text: c }))));
    if (r.parents.length) {
      box.append(sec(t('h.r.parents'), h('p', { text: r.parents.map(p => p.name + (p.hidden ? ' (' + t('h.r.hiddenp') + ')' : '')).join(' ‹ ') }),
        r.outside ? h('p', { class: 'warn', text: t('h.r.outside') }) : null));
    }
  }

  function drawProps(g) {
    const f = scene.files[g.file];
    const [w] = dims();
    const font = g.attrs.textfont ? fontAt(scene.fonts, g.attrs.textfont, g.attrs.textfontsize || '12', w, dims()[1]) : null;
    const row = (k, v) => h('tr', {}, h('th', { text: k }), h('td', { class: 'mono', text: v }));
    details.append(
      h('table', { class: 'hud-props small' },
        row(t('h.type'), g.type),
        row(t('h.file'), `${f.stem} (${f.where.split(/[\\/]/).pop()}), ${t('h.line')} ${g.line}`),
        row('size1024', g.rect.join(' ')),
        g.text ? row(t('h.text'), g.text) : null,
        g.text ? row(t('h.shows'), displayText(g.text, scene.strings)) : null,
        g.attrs.textfont ? row(t('h.font'), font && !font.Fallback ? `${font.Name} → ${font.TypeFace}, ${font.AscentHeight} px`
          : t('h.nofont', { f: `${g.attrs.textfont} ${g.attrs.textfontsize || ''}` }) + (font ? ` (${font.Name}, ${Number(font.AscentHeight).toFixed(1)} px)` : '')) : null,
        g.states.length ? row(t('h.states'), g.states.join(' · ')) : null,
        g.commands.length ? row(t('h.commands'), g.commands.join(' · ')) : null),
      h('h4', { text: t('h.attrs') }),
      h('table', { class: 'hud-props small' }, Object.entries(g.attrs).map(([k, v]) => row(k, v))));
  }

  async function snapshot() {
    if (!frame) return;
    try {
      const r = await api('/api/hud/snapshot', { picture: frame.toDataURL('image/png'), name: `${scene.variant}-${size.value}-${culture.value}` });
      toast(t('h.saved', { path: r.path }), 'ok');
    } catch (e) { toast(e.message, 'bad'); }
  }

  details.append(h('p', { class: 'small muted', text: t('h.pick') }));
  open();
}
