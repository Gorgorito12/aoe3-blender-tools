// SPDX-License-Identifier: GPL-3.0-or-later
// Repaint a unit: its texture with its UV islands coloured by body part, a list of paint steps
// (the recipe of tools/retexture.py) painted live, the unit in 3D, then the texture written as
// the game reads it.
import { api, clear, debounce, fmt, h, pick, storeGet, storeSet, t, toast } from './core.js';
import { ImageView, fileToPng, pixels } from './canvas2d.js';
import { Viewer } from './viewer.js';
import { watchJob } from './jobs.js';

// each step's settings: [key, kind, default, min, max, step]
const STEPS = {
  recolour: [['colour', 'colour', '#a03030'], ['shading', 'range', 1, 0, 1.5, 0.05], ['amount', 'range', 1, 0, 1, 0.05]],
  tone: [['hue', 'range', 0, -180, 180, 1], ['sat', 'range', 1, 0, 2, 0.05], ['value', 'range', 1, 0, 2, 0.05],
    ['amount', 'range', 1, 0, 1, 0.05]],
  fill: [['swatch', 'picture', ''], ['tile', 'range', 64, 8, 512, 8], ['tint', 'colour?', ''],
    ['shading', 'range', 1, 0, 1.5, 0.05], ['amount', 'range', 1, 0, 1, 0.05]],
  paste: [['image', 'picture', ''], ['box', 'box', [0.25, 0.25, 0.75, 0.75]], ['shading', 'range', 0, 0, 1, 0.05]],
  blur: [['radius', 'range', 2, 1, 6, 1], ['passes', 'range', 2, 1, 4, 1]],
  grain: [['amount', 'range', 0.3, 0, 1, 0.05], ['cell', 'range', 2, 1, 16, 1], ['kind', 'choice', 'weave', ['weave', 'noise']],
    ['seed', 'number', 0]],
  player: [['amount', 'range', 1, 0, 1, 0.05]],
  ai: [['prompt', 'text', ''], ['strength', 'range', 0.45, 0.1, 0.9, 0.05], ['seed', 'number', 1]],
};
// what narrows any step's selection
const NARROW = [['near', 'colour?', ''], ['tol', 'range', 60, 0, 200, 5], ['edge', 'range', 0, 0, 20, 1],
  ['feather', 'range', 0, 0, 10, 1]];

export async function retexScreen(main, app) {
  clear(main);
  let session = null, data = null, labels = null, ops = [], current = 0, view = 'result', result = null;
  const loadBox = h('div', { class: 'card stack' });
  const work = h('div', {});
  main.append(h('div', { class: 'head' }, h('div', {},
    h('button', { type: 'button', class: 'ghost small', text: '← ' + t('nav.textures'), onclick: () => app.go('textures') }),
    h('h1', { text: t('r.title') }), h('p', { class: 'muted', text: t('r.intro') }))), loadBox, work);

  // -- loading ------------------------------------------------------------------------------
  const last = storeGet('retex.load', { source: 'game', target: '', prefer: '', model: '', texture: '', by: 'bone', scale: 1 });
  const hasGame = !!app.state.settings.paths.game;
  const src = h('select', { 'aria-label': t('r.source') },
    h('option', { value: 'game', text: t('r.source.game'), selected: last.source === 'game' }),
    h('option', { value: 'file', text: t('r.source.file'), selected: last.source === 'file' }));
  const units = h('datalist', { id: 'retex-units' });
  const target = h('input', { type: 'text', value: last.target, placeholder: t('r.target.ph'), class: 'grow', list: 'retex-units',
    oninput: () => findUnits() });
  const unitInfo = h('span', { class: 'small muted' });
  // the game's units as the name is typed (its unit list, read once)
  const findUnits = debounce(async () => {
    if (!hasGame || target.value.trim().length < 2) return;
    try {
      const r = await api('/api/game/units', { q: target.value });
      clear(units).append(...r.units.map(u => h('option', { value: u.name, label: u.anim })));
      unitInfo.textContent = t('r.units', { n: r.count });
    } catch (e) { unitInfo.textContent = e.message; }
  }, 300);
  const prefer = h('input', { type: 'text', value: last.prefer, placeholder: t('r.prefer') });
  const model = h('input', { type: 'text', value: last.model, class: 'grow', placeholder: t('r.model') });
  const texture = h('input', { type: 'text', value: last.texture, class: 'grow', placeholder: t('r.texture') });
  const by = h('select', { 'aria-label': t('r.by') }, ['bone', 'position'].map(v => h('option', { value: v, text: t('r.by.' + v), selected: v === last.by })));
  const scale = h('select', { 'aria-label': t('r.scale') }, [1, 2, 4].map(v => h('option', { value: v, text: '× ' + v, selected: v === Number(last.scale) })));
  const gameRow = h('div', { class: 'row' }, target, units, prefer, unitInfo,
    hasGame ? null : h('span', { class: 'small bad', text: t('r.nogame') }));
  const fileRow = h('div', { class: 'stack' },
    h('div', { class: 'row' }, model, h('button', { type: 'button', text: t('browse'), onclick: async () => {
      const p = await pick('file', { title: t('r.model'), filters: [['Granny model', '*.gr2']] }); if (p) model.value = p; } })),
    h('div', { class: 'row' }, texture, h('button', { type: 'button', text: t('browse'), onclick: async () => {
      const p = await pick('file', { title: t('r.texture'), filters: [['Texture', '*.ddt *.png']] }); if (p) texture.value = p; } })));
  const showSource = () => { gameRow.hidden = src.value !== 'game'; fileRow.hidden = src.value !== 'file'; };
  src.addEventListener('change', showSource);
  const loadBtn = h('button', { type: 'button', class: 'primary', text: t('r.load'), onclick: () => load() });
  loadBox.append(h('div', { class: 'row' }, h('strong', { text: t('r.what') }), src,
    h('label', { class: 'row small' }, t('r.by'), by), h('label', { class: 'row small', title: t('r.scale.help') }, t('r.scale'), scale), loadBtn),
    gameRow, fileRow);
  showSource();

  async function load() {
    const req = { source: src.value, target: target.value.trim(), prefer: prefer.value, model: model.value.trim(),
      texture: texture.value.trim(), by: by.value, scale: Number(scale.value) };
    storeSet('retex.load', req);
    loadBtn.disabled = true;
    clear(work).append(h('p', { class: 'muted', text: t('b.working') }));
    try {
      data = await api('/api/retex/load', req);
    } catch (e) {
      clear(work).append(h('div', { class: 'notice bad', text: e.message }));
      return;
    } finally { loadBtn.disabled = false; }
    session = data.session;
    labels = await pixels(data.labels);
    ops = storeGet('retex.ops.' + data.name, null) || [{ op: 'recolour', where: [], colour: '#a03030', shading: 1, amount: 1 }];
    current = 0;
    build();
  }

  // -- the work area -------------------------------------------------------------------------
  let imageView = null, viewer = null, list = null, status = null, legend = null, hover = null;
  app.onLeave(() => { imageView?.dispose(); viewer?.dispose(); });

  function build() {
    imageView?.dispose(); viewer?.dispose();
    clear(work);
    list = h('div', { class: 'stack' });
    status = h('p', { class: 'small muted' });
    hover = h('span', { class: 'small muted' });
    legend = h('div', { class: 'row small' });
    const picture = h('div', { class: 'viewport', style: { height: '62vh', background: 'var(--viewport)' } });
    const model3d = h('div', { class: 'viewport', style: { height: '40vh' } });
    const tabs = h('div', { class: 'tabs' }, ['result', 'start', 'islands'].map(v =>
      h('button', { type: 'button', 'aria-selected': String(v === view), text: t('r.view.' + v), onclick: e => {
        view = v; e.target.parentNode.querySelectorAll('button').forEach(b => b.setAttribute('aria-selected', String(b === e.target))); show(); } })));
    const add = h('select', { 'aria-label': t('r.add'), onchange: e => {
      if (!e.target.value) return;
      ops.push(defaults(e.target.value)); current = ops.length - 1; e.target.value = ''; drawList(); changed(); } },
      h('option', { value: '', text: t('r.add') }), Object.keys(STEPS).map(k => h('option', { value: k, text: t('r.op.' + k) })));
    const left = h('section', { class: 'stack' }, h('div', { class: 'row' }, h('h2', { class: 'grow', text: t('r.steps') }), add), list,
      h('p', { class: 'small muted', text: t('r.howto') }));
    const mid = h('section', { class: 'stack' }, tabs, picture, h('div', { class: 'row' }, legend, h('span', { class: 'grow' }), hover), status);
    const save = saveCard();
    const right = h('section', { class: 'stack' }, model3d, save);
    work.append(h('div', { class: 'retex' }, left, mid, right));
    imageView = new ImageView(picture, {
      onPick: (x, y, mods) => pickIsland(x, y, mods),
      onBox: box => boxTo(box),
      onHover: p => { hover.textContent = p ? islandText(islandAt(Math.floor(p[0]), Math.floor(p[1]))) : ''; },
    });
    viewer = new Viewer(model3d);
    if (data.mesh) viewer.setModel({ mesh: data.mesh, attach: {}, boxes: [] }, data.start, true);
    drawLegend();
    drawList();
    paintNow();
  }

  function islandAt(x, y) {
    if (!labels || x < 0 || y < 0 || x >= labels.width || y >= labels.height) return null;
    const i = (y * labels.width + x) * 4;
    const v = labels.data[i] + 256 * labels.data[i + 1];
    return v ? data.islands.find(r => r.id === v - 1) : null;
  }

  function islandText(isl) {
    return isl ? `${t('r.island')} ${isl.id} · ${t('part.' + isl.part, null, isl.part)}${isl.bone ? ' · ' + isl.bone : ''}` : '';
  }

  function pickIsland(x, y, { subtract }) {
    const isl = islandAt(x, y);
    if (!isl) return;
    const op = ops[current];
    if (!op) return;
    const term = (subtract ? '-' : '') + 'island:' + isl.id;
    const other = (subtract ? '' : '-') + 'island:' + isl.id;
    op.where = (op.where || []).filter(w => w !== other);
    op.where = op.where.includes(term) ? op.where.filter(w => w !== term) : [...op.where, term];
    drawList(); changed();
  }

  function boxTo(box) {
    const op = ops[current];
    if (!op) return;
    const r = box.map(v => Math.round(v * 1000) / 1000);
    if (op.op === 'paste') op.box = r;
    else op.where = [...(op.where || []), 'rect:' + r.join(',')];
    imageView.box = null;
    drawList(); changed();
  }

  function drawLegend() {
    clear(legend);
    const parts = data.parts.filter(p => p !== 'body');
    for (const p of ['body', ...parts]) {
      const c = data.colours[p] || [200, 200, 200];
      legend.append(h('button', { type: 'button', class: 'chip', title: t('r.part.add'),
        onclick: () => { const op = ops[current]; if (!op) return; const term = 'part:' + p;
          op.where = (op.where || []).includes(term) ? op.where.filter(w => w !== term) : [...(op.where || []), term]; drawList(); changed(); } },
      h('i', { class: 'swatch', style: { background: `rgb(${c.join(',')})` } }), t('part.' + p, null, p)));
    }
  }

  // the islands an op selects, drawn over the picture
  function overlay() {
    if (!labels) return null;
    const op = ops[current] || { where: [] };
    const where = op.where || [];
    const partsOf = new Set(), add = new Set(), sub = new Set();
    for (const w of where) {
      if (w.startsWith('part:')) partsOf.add(w.slice(5));
      if (w.startsWith('island:')) w.slice(7).split(',').forEach(v => add.add(Number(v)));
      if (w.startsWith('-island:')) w.slice(8).split(',').forEach(v => sub.add(Number(v)));
    }
    const groups = { arms: ['arm_l', 'arm_r'], hands: ['hand_l', 'hand_r'], legs: ['leg_l', 'leg_r'], feet: ['foot_l', 'foot_r'] };
    const chosen = new Set();
    for (const isl of data.islands) {
      const inPart = partsOf.has('body') || partsOf.has(isl.part) || Object.entries(groups).some(([g, ps]) => partsOf.has(g) && ps.includes(isl.part));
      if ((inPart || add.has(isl.id)) && !sub.has(isl.id)) chosen.add(isl.id);
    }
    const W = labels.width, H = labels.height;
    const out = new ImageData(W, H);
    const byId = new Map(data.islands.map(i => [i.id, i]));
    const all = view === 'islands';
    // which island each pixel shows, and whether the step paints it
    const sel = new Uint8Array(W * H);
    for (let i = 0; i < W * H; i++) {
      const v = labels.data[4 * i] + 256 * labels.data[4 * i + 1];
      if (!v) continue;
      const isl = byId.get(v - 1);
      if (!isl) continue;
      if (chosen.has(isl.id)) sel[i] = 1;
      if (all) {                                   // every island in its part's colour
        const c = data.colours[isl.part] || [200, 200, 200];
        out.data.set([c[0], c[1], c[2], sel[i] ? 200 : 110], 4 * i);
      }
    }
    // the step's selection as an outline, so the result under it stays visible
    const line = Math.max(1, Math.round(Math.max(W, H) / 400));
    for (let y = 0; y < H; y++) {
      for (let x = 0; x < W; x++) {
        const i = y * W + x;
        if (!sel[i]) continue;
        let edge = false;
        for (let d = 1; d <= line && !edge; d++) {
          edge = x < d || y < d || x >= W - d || y >= H - d || !sel[i - d] || !sel[i + d] || !sel[i - d * W] || !sel[i + d * W];
        }
        if (edge) out.data.set([255, 222, 89, 255], 4 * i);
      }
    }
    return out;
  }

  async function show() {
    if (!imageView) return;
    const url = view === 'start' || !result ? data.start : result;
    await imageView.setImage(url, true);
    imageView.setOverlay(overlay());
  }

  // -- the steps -------------------------------------------------------------------------------
  function defaults(kind) {
    const op = { op: kind, where: [] };
    for (const [k, type, d] of STEPS[kind]) if (type !== 'colour?' && d !== '') op[k] = Array.isArray(d) ? [...d] : d;
    return op;
  }

  function drawList() {
    clear(list);
    ops.forEach((op, i) => list.append(stepCard(op, i)));
    if (!ops.length) list.append(h('p', { class: 'muted small', text: t('r.nosteps') }));
    imageView?.setOverlay(overlay());
  }

  function stepCard(op, i) {
    const card = h('div', { class: 'card stack step' + (i === current ? ' current' : '') + (op.off ? ' off' : ''),
      onclick: e => { if (current !== i && !e.target.closest('input,select,button')) { current = i; drawList(); } } });
    card.append(h('div', { class: 'row' },
      h('input', { type: 'checkbox', checked: !op.off, title: t('r.on'), 'aria-label': t('r.on'), onchange: e => { op.off = !e.target.checked; changed(); } }),
      h('strong', { class: 'grow', text: `${i + 1}. ${t('r.op.' + op.op)}` }),
      h('button', { type: 'button', class: 'ghost small', text: '↑', 'aria-label': t('r.up'), disabled: i === 0,
        onclick: () => { [ops[i - 1], ops[i]] = [ops[i], ops[i - 1]]; current = i - 1; drawList(); changed(); } }),
      h('button', { type: 'button', class: 'ghost small', text: '↓', 'aria-label': t('r.down'), disabled: i === ops.length - 1,
        onclick: () => { [ops[i + 1], ops[i]] = [ops[i], ops[i + 1]]; current = i + 1; drawList(); changed(); } }),
      h('button', { type: 'button', class: 'ghost small', text: '×', 'aria-label': t('remove'),
        onclick: () => { ops.splice(i, 1); current = Math.max(0, Math.min(current, ops.length - 1)); drawList(); changed(); } })));
    if (i !== current) {
      card.append(h('p', { class: 'small muted', text: (op.where || []).map(termText).join(', ') || t('r.where.none') }));
      return card;
    }
    // where it paints
    const chips = h('div', { class: 'row' });
    for (const w of op.where || []) {
      chips.append(h('span', { class: 'chip' + (w.startsWith('-') ? ' minus' : '') }, termText(w),
        h('button', { type: 'button', class: 'ghost small', text: '×', 'aria-label': t('remove'),
          onclick: () => { op.where = op.where.filter(x => x !== w); drawList(); changed(); } })));
    }
    if (!(op.where || []).length) chips.append(h('span', { class: 'small muted', text: t('r.where.none') }));
    card.append(h('div', { class: 'stack' }, h('span', { class: 'small', text: t('r.where') }), chips,
      h('div', { class: 'row' },
        h('button', { type: 'button', class: 'small', text: t('r.where.all'), onclick: () => { op.where = ['all']; drawList(); changed(); } }),
        h('button', { type: 'button', class: 'small', text: t('r.where.pc'), title: t('r.where.pc.help'),
          onclick: () => { op.where = [...new Set([...(op.where || []), 'pc'])]; drawList(); changed(); } }))));
    for (const spec of STEPS[op.op]) card.append(setting(op, spec));
    card.append(h('details', {}, h('summary', { class: 'small', text: t('r.narrow') }), NARROW.map(spec => setting(op, spec))));
    if (op.op === 'ai') card.append(h('p', { class: 'small notice', text: t('r.ai.note') }));
    return card;
  }

  function termText(w) {
    const minus = w.startsWith('-') ? '− ' : '';
    const v = w.replace(/^-/, '');
    if (v === 'all') return t('r.where.all');
    if (v === 'pc') return minus + t('r.where.pc');
    if (v.startsWith('part:')) return minus + t('part.' + v.slice(5), null, v.slice(5));
    if (v.startsWith('island:')) return minus + t('r.island') + ' ' + v.slice(7);
    if (v.startsWith('rect:')) return minus + t('r.rect');
    return minus + v;
  }

  function setting(op, [key, kind, def, a, b, step]) {
    const label = t('r.k.' + key, null, key);
    let ctl;
    const set = (v, now) => { op[key] = v; now ? changed() : changedLater(); };
    if (kind === 'range') {
      const v = op[key] ?? def;
      const num = h('span', { class: 'small mono', text: String(v) });
      ctl = [h('input', { type: 'range', min: a, max: b, step, value: v, oninput: e => { num.textContent = e.target.value; set(Number(e.target.value)); } }), num];
    } else if (kind === 'colour' || kind === 'colour?') {
      const optional = kind === 'colour?';
      const on = !optional || op[key] !== undefined;
      const input = h('input', { type: 'color', value: op[key] || '#808080', disabled: !on, oninput: e => set(e.target.value) });
      ctl = [optional ? h('input', { type: 'checkbox', checked: on, 'aria-label': label, onchange: e => {
        input.disabled = !e.target.checked; if (e.target.checked) op[key] = input.value; else delete op[key]; changed(); } }) : null, input];
    } else if (kind === 'choice') {
      ctl = h('select', { onchange: e => set(e.target.value, true) }, a.map(v => h('option', { value: v, text: t('r.v.' + v, null, v), selected: v === (op[key] ?? def) })));
    } else if (kind === 'number') {
      ctl = h('input', { type: 'number', value: op[key] ?? def, style: { width: '80px' }, onchange: e => set(Number(e.target.value), true) });
    } else if (kind === 'text') {
      ctl = h('input', { type: 'text', value: op[key] ?? '', class: 'grow', onchange: e => set(e.target.value, true) });
    } else if (kind === 'picture') {
      ctl = [h('span', { class: 'small mono grow', text: op[key] || t('r.picture.none') }),
        h('button', { type: 'button', class: 'small', text: t('r.picture'), onclick: () => choosePicture(op, key) })];
    } else if (kind === 'box') {
      ctl = h('span', { class: 'small muted', text: t('r.box', { box: (op[key] || def).map(v => fmt(v, 2)).join(', ') }) });
    }
    return h('div', { class: 'field' }, h('label', { text: label }), h('div', { class: 'ctl' }, ctl));
  }

  function choosePicture(op, key) {
    const input = h('input', { type: 'file', accept: 'image/*' });
    input.addEventListener('change', async () => {
      const file = input.files[0];
      if (!file) return;
      try {
        const png = await fileToPng(file);
        const name = file.name.replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9_-]+/g, '_').slice(0, 60) + '.png';
        const r = await api('/api/retex/picture', { session, name, data: png });
        op[key] = r.name; drawList(); changed();
      } catch (e) { toast(e.message, 'bad'); }
    });
    input.click();
  }

  // -- painting ------------------------------------------------------------------------------
  let busy = false, again = false;
  async function paintNow() {
    if (busy) { again = true; return; }
    busy = true;
    try {
      const r = await api('/api/retex/paint', { session, ops });
      result = r.image;
      status.className = 'small muted';
      status.textContent = t('r.painted', { s: fmt(r.seconds, 2) })
        + (r.ai_skipped.length ? ' ' + t('r.ai.skipped', { n: r.ai_skipped.length }) : '')
        + (r.empty.length ? ' ' + t('r.empty', { steps: r.empty.map(i => i + 1).join(', ') }) : '');
      await show();
      viewer?.setTexture(result);
    } catch (e) {
      status.className = 'small bad';
      status.textContent = e.message;
    } finally {
      busy = false;
      if (again) { again = false; paintNow(); }
    }
  }
  const changedLater = debounce(() => changed(), 250);
  function changed() {
    storeSet('retex.ops.' + data.name, ops);
    imageView?.setOverlay(overlay());
    paintNow();
  }

  // -- writing -------------------------------------------------------------------------------
  function saveCard() {
    const opts = storeGet('retex.save', { out: 'new', format: 'same', mips: 'same', bump: true });
    const box = h('div', {});
    const out = h('input', { type: 'text', value: opts.out, style: { width: '120px' } });
    const format = h('select', {}, ['same', 'BGRA', 'DXT1', 'DXT3', 'DXT5'].map(v => h('option', { value: v, text: v === 'same' ? t('r.same') : v, selected: v === opts.format })));
    const mips = h('select', {}, ['same', 'full', 'none'].map(v => h('option', { value: v, text: t('r.mips.' + v), selected: v === opts.mips })));
    const bump = h('input', { type: 'checkbox', checked: opts.bump });
    return h('div', { class: 'card stack' }, h('h2', { text: t('r.write') }),
      h('div', { class: 'field' }, h('label', { text: t('r.name') }), h('div', { class: 'ctl' }, out, h('span', { class: 'small muted', text: '.ddt' }))),
      h('div', { class: 'field' }, h('label', { text: t('b.format') }), h('div', { class: 'ctl' }, format)),
      h('div', { class: 'field' }, h('label', { text: t('r.mips') }), h('div', { class: 'ctl' }, mips)),
      h('label', { class: 'row small' }, bump, t('r.bump')),
      h('p', { class: 'small muted', text: t('r.write.help', { folder: data.folder }) }),
      h('div', { class: 'row' }, h('button', { type: 'button', class: 'primary', text: t('r.write.go'), onclick: async () => {
        const o = { out: out.value.trim(), format: format.value, mips: mips.value, bump: bump.checked };
        storeSet('retex.save', o);
        try {
          const r = await api('/api/retex/save', { session, ops, ...o });
          watchJob(r.job, box);
        } catch (e) { toast(e.message, 'bad'); }
      } }), h('button', { type: 'button', text: t('open.folder'), onclick: () => api('/api/open', { path: data.folder }) })), box);
  }

  if (last.source === 'game' ? last.target && hasGame : last.model) load();
}
