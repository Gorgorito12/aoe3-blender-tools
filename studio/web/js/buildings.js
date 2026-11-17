// SPDX-License-Identifier: GPL-3.0-or-later
// The building generator: presets, the form drawn from the schema, the live 3D preview, the
// texture, the numbers against the budget, the technical sheet, and the exports.
import { api, clear, confirmDialog, debounce, fmt, h, pick, storeGet, storeSet, t, toast } from './core.js';
import { markdown } from './md.js';
import { Viewer } from './viewer.js';
import { watchJob } from './jobs.js';

const QUICK = 256;                   // the texture painted while a control moves
const FULL = 1024;                   // the largest texture the preview paints

let schema = null;
let state = null;

function label(f) { return t('param.' + f.name, null, f.label); }
function helpOf(f) { return t('param.' + f.name + '.help', null, f.help || ''); }
function choiceLabel(f, c) { return t(`choice.${f.name}.${c.value}`, null, c.label); }

function visible(f, p) {
  if (!f.show) return true;
  return f.show.some(rule => (!rule.styles || rule.styles.includes(p.style)) &&
    Object.entries(rule.if).every(([k, vals]) => vals.includes(p[k])));
}

export async function buildingsScreen(main, app) {
  if (!schema) schema = await api('/api/schema');
  if (!state) {
    const saved = storeGet('building', null);
    state = { preset: saved?.preset || 'WHITE_HOUSE', params: saved?.params || null, view: '3d', full: false,
      seq: 0, preview: null, sheet: null, budget: null, filter: '' };
    if (!state.params) state.params = await api('/api/preset/' + state.preset);
  }
  clear(main);
  const left = h('section', {}), mid = h('section', {}), right = h('section', {});
  main.append(h('div', { class: 'bld' }, left, mid, right));

  // -- left: presets and the form -----------------------------------------------------------
  const presetBox = h('div', { class: 'presets', role: 'group', 'aria-label': t('b.presets') });
  const filter = h('input', { type: 'text', placeholder: t('b.filter'), value: state.filter, 'aria-label': t('b.filter'),
    oninput: e => { state.filter = e.target.value; drawPresets(); } });
  const form = h('div', { class: 'scroll' });
  left.append(h('div', { class: 'head' }, h('div', {}, h('h1', { text: t('nav.buildings') }),
    h('p', { class: 'muted small', text: t('b.intro') }))),
    h('div', { class: 'row', style: { marginBottom: '6px' } }, filter,
      h('button', { type: 'button', text: t('b.random'), title: t('b.random.help'), onclick: randomise })),
    presetBox, h('hr', { style: { border: 0, borderTop: '1px solid var(--line)', width: '100%' } }), form);

  function drawPresets() {
    clear(presetBox);
    const q = state.filter.toLowerCase();
    for (const p of schema.presets) {
      const text = `${p.key} ${p.name} ${p.style}`.toLowerCase();
      if (q && !text.includes(q)) continue;
      presetBox.append(h('button', { type: 'button', 'aria-pressed': String(p.key === state.preset),
        onclick: () => loadPreset(p.key) }, p.name, h('small', { text: t('style.' + p.style, null, p.style) })));
    }
  }

  async function loadPreset(key) {
    state.preset = key;
    state.params = await api('/api/preset/' + key);
    drawPresets();
    drawForm();
    refresh(true);
  }

  async function randomise() {
    const style = state.params.style;
    const s = schema.styles.find(x => x.key === style);
    if (!s?.random) { toast(t('b.random.none'), 'bad'); return; }
    state.params = await api('/api/building/random', { style, seed: Math.floor(Math.random() * 1e6) });
    state.preset = null;
    drawPresets();
    drawForm();
    refresh(true);
  }

  const groups = ['general', 'style', 'size', 'texture'];
  function drawForm() {
    clear(form);
    const p = state.params;
    for (const g of groups) {
      const fs = h('fieldset', { class: 'fieldset' }, h('legend', { text: t('group.' + g) }));
      let any = false;
      for (const f of schema.fields.filter(x => x.group === g)) {
        if (!visible(f, p)) continue;
        any = true;
        fs.append(fieldFor(f, p));
      }
      if (any) form.append(fs);
    }
    const colors = h('div', { class: 'colors' });
    for (const c of schema.colors) {
      const rgb = p.colors?.[c.key] || c.default;
      colors.append(h('label', {}, h('input', { type: 'color', value: toHex(rgb), 'aria-label': t('color.' + c.key, null, c.key),
        oninput: e => { p.colors = { ...(p.colors || {}), [c.key]: fromHex(e.target.value) }; changed(); } }),
        t('color.' + c.key, null, c.key)));
    }
    form.append(h('details', {}, h('summary', { text: t('group.colors') }), colors,
      h('button', { type: 'button', class: 'ghost small', text: t('b.colors.reset'),
        onclick: async () => { p.colors = (await api('/api/preset/' + (state.preset || 'WHITE_HOUSE'))).colors; drawForm(); changed(); } })));
  }

  function fieldFor(f, p) {
    const id = 'f-' + f.name;
    let ctl;
    const v = p[f.name];
    if (f.kind === 'bool') {
      ctl = h('input', { id, type: 'checkbox', checked: !!v, onchange: e => set(f, e.target.checked, true) });
    } else if (f.kind === 'choice') {
      ctl = h('select', { id, onchange: e => set(f, typeof f.default === 'number' ? Number(e.target.value) : e.target.value, true) },
        f.choices.map(c => h('option', { value: c.value, selected: c.value === v, title: c.help ? t(`choice.${f.name}.${c.value}.help`, null, c.help) : null },
          choiceLabel(f, c))));
    } else if (f.kind === 'text') {
      ctl = h('input', { id, type: 'text', value: v ?? '', onchange: e => set(f, e.target.value, false) });
    } else {
      const num = h('input', { type: 'number', min: f.min, max: f.max, step: f.step || 1, value: v, 'aria-label': label(f),
        onchange: e => { const x = clampNum(f, e.target.value); range && (range.value = x); set(f, x, true); } });
      const range = f.max - f.min <= 1000 ? h('input', { id, type: 'range', min: f.min, max: f.max, step: f.step || 1, value: v,
        oninput: e => { num.value = e.target.value; set(f, Number(e.target.value), false, true); },
        onchange: e => set(f, Number(e.target.value), true) }) : null;
      if (!range) num.id = id;
      ctl = [range, num, f.unit ? h('span', { class: 'unit', text: f.unit }) : null];
    }
    const help = helpOf(f);
    return h('div', { class: 'field', title: help }, h('label', { for: id, text: label(f) }), h('div', { class: 'ctl' }, ctl));
  }

  function set(f, value, redraw, dragging) {
    state.params[f.name] = value;
    if (redraw) drawForm();
    changed(dragging);
  }

  // -- middle: the view ---------------------------------------------------------------------
  const tabs = h('div', { class: 'tabs', role: 'tablist' });
  const view = h('div', { class: 'viewport' });
  const tex = h('div', { class: 'texview', hidden: true });
  const busy = h('div', { class: 'busy', hidden: true, text: t('b.working') });
  const stat = h('div', { class: 'stat' });
  view.append(busy, stat);
  mid.append(tabs, view, tex);
  const viewer = new Viewer(view);
  app.onLeave(() => viewer.dispose());
  const over = h('div', { class: 'over' });
  view.append(over);
  const toggles = [['texture', t('b.v.texture')], ['clay', t('b.v.clay')]];
  for (const [mode, text] of toggles) {
    over.append(h('button', { type: 'button', 'aria-pressed': String(viewer.mode === mode), 'data-mode': mode, text,
      onclick: e => { viewer.setMode(mode); over.querySelectorAll('[data-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === mode))); void e; } }));
  }
  for (const [what, text] of [['wire', t('b.v.wire')], ['attach', t('b.v.attach')], ['boxes', t('b.v.boxes')], ['grid', t('b.v.grid')]]) {
    over.append(h('button', { type: 'button', 'aria-pressed': String(viewer.show[what]), text,
      onclick: e => { const on = e.target.getAttribute('aria-pressed') !== 'true'; e.target.setAttribute('aria-pressed', String(on)); viewer.toggle(what, on); } }));
  }
  over.append(h('select', { 'aria-label': t('b.v.camera'), onchange: e => { if (e.target.value) viewer.view(e.target.value); e.target.value = ''; } },
    h('option', { value: '', text: t('b.v.camera') }),
    ['three', 'front', 'back', 'left', 'right', 'top'].map(v => h('option', { value: v, text: t('b.cam.' + v) }))));
  over.append(h('button', { type: 'button', text: t('b.v.snapshot'), onclick: () => saveSnapshot(viewer) }));

  for (const [key, text] of [['3d', t('b.tab.3d')], ['texture', t('b.tab.texture')], ['damaged', t('b.tab.damaged')]]) {
    tabs.append(h('button', { type: 'button', role: 'tab', 'aria-selected': String(state.view === key), text,
      onclick: () => { state.view = key; tabs.querySelectorAll('button').forEach(b => b.setAttribute('aria-selected', String(b.textContent === text))); showView(); if (key === 'damaged' && !state.preview?.damaged) refresh(false, true); } }));
  }
  const fullBox = h('input', { type: 'checkbox', id: 'b-full', checked: state.full,
    onchange: e => { state.full = e.target.checked; refresh(false); } });
  tabs.append(h('label', { class: 'row small', style: { marginLeft: 'auto' }, title: t('b.full.help') }, fullBox, t('b.full')));

  function showView() {
    view.hidden = state.view !== '3d';
    tex.hidden = state.view === '3d';
    if (state.view !== '3d') drawTexture();
    else viewer.resize();
  }

  function drawTexture() {
    clear(tex);
    const d = state.preview;
    if (!d) return;
    const url = state.view === 'damaged' ? d.damaged : d.texture;
    if (!url) { tex.append(h('p', { class: 'muted', text: t('b.working') })); return; }
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 1 1');
    svg.setAttribute('preserveAspectRatio', 'none');
    for (const r of d.atlas.regions) {
      const [u0, v0, u1, v1] = r.box;
      const rect = document.createElementNS(svg.namespaceURI, 'rect');
      rect.setAttribute('x', u0); rect.setAttribute('y', 1 - v1);
      rect.setAttribute('width', u1 - u0); rect.setAttribute('height', v1 - v0);
      const title = document.createElementNS(svg.namespaceURI, 'title');
      title.textContent = r.name;
      rect.append(title);
      svg.append(rect);
    }
    const showRegions = h('label', { class: 'row small' }, h('input', { type: 'checkbox', checked: storeGet('regions', true),
      onchange: e => { storeSet('regions', e.target.checked); svg.style.display = e.target.checked ? '' : 'none'; } }), t('b.regions'));
    svg.style.display = storeGet('regions', true) ? '' : 'none';
    tex.append(h('div', { class: 'stack', style: { width: '100%', padding: '10px' } }, showRegions,
      h('div', { class: 'wrap' }, h('img', { src: url, alt: t('b.tab.texture') }), svg),
      h('p', { class: 'small muted', text: t('b.texsize', { n: d.texture_size }) })));
  }

  // -- right: numbers, sheet, export --------------------------------------------------------
  const numbers = h('div', { class: 'card stack' });
  const actions = h('div', { class: 'card stack' });
  const sheetBox = h('div', { class: 'card md' });
  right.append(h('div', { class: 'scroll stack' }, numbers, actions, h('details', { class: 'card' },
    h('summary', { text: t('b.sheet') }), sheetBox)));

  function drawNumbers() {
    clear(numbers);
    const d = state.preview;
    if (!d) return;
    const tris = d.triangles;
    const b = state.budget || {};
    const band = b.band;                     // [target, low, high] of a style guide
    const limit = band ? band[2] : b.p90;
    numbers.append(h('h2', { text: d.params.name }));
    if (limit) {
      const share = Math.min(1, tris / (limit * 1.25));
      numbers.append(h('div', {}, h('div', { class: 'row small' }, h('span', { text: t('b.tris') }),
        h('strong', { class: 'grow', style: { textAlign: 'right' }, text: fmt(tris) })),
        h('div', { class: 'bar' + (tris > limit ? ' over' : ''), title: t('b.budget.help') }, h('i', { style: { width: (share * 100) + '%' } })),
        h('p', { class: 'small muted', text: band ? t('b.band', { lo: fmt(band[1]), target: fmt(band[0]), hi: fmt(band[2]) })
          : t('b.p90', { cls: b.class, p90: fmt(b.p90), max: fmt(b.max) }) })));
      if (tris > limit) numbers.append(h('p', { class: 'notice bad small', text: t('b.over') }));
    } else {
      numbers.append(h('dl', { class: 'kv' }, h('dt', { text: t('b.tris') }), h('dd', { text: fmt(tris) })));
    }
    const f = state.sheet?.facts;
    const [w, dep, hgt] = d.extent;
    numbers.append(h('dl', { class: 'kv' },
      h('dt', { text: t('b.tris.low') }), h('dd', { text: f ? fmt(f.tris_low) : '…' }),
      h('dt', { text: t('b.verts') }), h('dd', { text: fmt(d.vertices) }),
      h('dt', { text: t('b.size') }), h('dd', { text: `${fmt(w, 1)} × ${fmt(dep, 1)} × ${fmt(hgt, 1)} m` }),
      f ? [h('dt', { text: t('b.obstruction') }), h('dd', { text: f.game.radius.map(x => fmt(2 * x, 1)).join(' × ') })] : null,
      f ? [h('dt', { text: t('b.texmb') }), h('dd', { text: fmt(f.texture_mb, 2) + ' MB' })] : null,
      h('dt', { text: t('b.paint') }), h('dd', { text: `${d.texture_size} px · ${fmt(d.seconds, 2)} s` })));
    if (d.parts?.length) {
      numbers.append(h('details', {}, h('summary', { text: t('b.parts') }),
        h('table', { class: 'parts' }, d.parts.slice(0, 40).map(([name, n]) => h('tr', {}, h('td', { text: name }), h('td', { text: fmt(n) }))))));
    }
    // what the style held to its own range, for the fields this building shows
    const clamped = Object.entries(d.clamped || {}).filter(([k]) => {
      const f = schema.fields.find(x => x.name === k);
      return f && visible(f, state.params);
    });
    const notes = [...d.notes, ...clamped.map(([k, v]) =>
      t('b.clamped', { name: t('param.' + k, null, k), v: typeof v === 'number' ? fmt(v, 2) : String(v) }))];
    const display = document.getElementById('o-display');
    if (display) display.placeholder = d.params.name;
    if (notes.length) numbers.append(h('div', { class: 'notice small' }, h('strong', { text: t('b.notes') }), h('ul', {}, notes.map(n => h('li', { text: n })))));
    stat.textContent = `${fmt(tris)} ${t('b.tris.short')} · ${fmt(d.vertices)} ${t('b.verts.short')}`;
  }

  function drawActions() {
    clear(actions);
    const blender = app.state.blender;
    actions.append(h('h2', { text: t('b.export') }));
    if (!blender.available) actions.append(h('p', { class: 'notice small', text: t('b.noblender') }));
    const opts = storeGet('gameOpts', { prefix: 'mod', texture_format: 'DXT3', display: '', no_icons: false, no_lowpoly: false, no_damaged: false });
    const optForm = h('div', {},
      h('div', { class: 'field' }, h('label', { text: t('b.prefix'), for: 'o-prefix' }),
        h('input', { id: 'o-prefix', type: 'text', value: opts.prefix, onchange: e => { opts.prefix = e.target.value; storeSet('gameOpts', opts); } })),
      h('div', { class: 'field' }, h('label', { text: t('b.display'), for: 'o-display' }),
        h('input', { id: 'o-display', type: 'text', value: opts.display, placeholder: state.params.name, onchange: e => { opts.display = e.target.value; storeSet('gameOpts', opts); } })),
      h('div', { class: 'field' }, h('label', { text: t('b.format'), for: 'o-format' }),
        h('select', { id: 'o-format', onchange: e => { opts.texture_format = e.target.value; storeSet('gameOpts', opts); } },
          ['DXT3', 'DXT1', 'BGRA'].map(x => h('option', { value: x, selected: x === opts.texture_format, text: x })))),
      [['no_icons', t('b.noicons')], ['no_lowpoly', t('b.nolowpoly')], ['no_damaged', t('b.nodamaged')]].map(([k, text]) =>
        h('label', { class: 'row small' }, h('input', { type: 'checkbox', checked: !!opts[k], onchange: e => { opts[k] = e.target.checked; storeSet('gameOpts', opts); } }), text)),
      // the AI repaint: only when ComfyUI answers
      h('label', { class: 'row small', title: app.state.requirements.comfy ? t('b.ai.help') : t('b.ai.off') },
        h('input', { type: 'checkbox', disabled: !app.state.requirements.comfy, checked: !!opts.ai && app.state.requirements.comfy,
          onchange: e => { opts.ai = e.target.checked; storeSet('gameOpts', opts); } }), t('b.ai'),
        h('input', { type: 'number', min: 0.05, max: 0.95, step: 0.05, value: opts.ai_strength || 0.45, style: { width: '64px' },
          'aria-label': t('b.ai.strength'), disabled: !app.state.requirements.comfy,
          onchange: e => { opts.ai_strength = Number(e.target.value); storeSet('gameOpts', opts); } })));
    const outInput = h('input', { type: 'text', class: 'grow', placeholder: t('b.out.default'), value: storeGet('gameOut', '') });
    actions.append(optForm, h('div', { class: 'row' }, outInput,
      h('button', { type: 'button', text: t('browse'), onclick: async () => { const p = await pick('folder', { title: t('b.out') }); if (p) { outInput.value = p; storeSet('gameOut', p); } } })));
    const run = async (kind) => {
      try {
        const r = await api('/api/building/export', { kind, params: state.params, out: outInput.value || null,
          options: kind === 'game' ? opts : { views: ['front34', 'back34', 'wire'] } });
        toast(t('job.started'), 'ok');
        lastBundle = kind === 'game' ? r.out : lastBundle;
        watchJob(r.job, jobBox, { onDone: drawDeploy });
      } catch (e) { toast(e.message, 'bad'); }
    };
    actions.append(h('div', { class: 'row' },
      h('button', { type: 'button', class: 'primary', disabled: !blender.available, text: t('b.export.game'), onclick: () => run('game') }),
      h('button', { type: 'button', disabled: !blender.available, text: t('b.export.files'), onclick: () => run('files'), title: t('b.export.files.help') }),
      h('button', { type: 'button', text: t('b.save'), onclick: saveParams }),
      h('button', { type: 'button', text: t('b.load'), onclick: loadParams })));
    actions.append(jobBox, deployBox);
    drawDeploy();
  }

  let lastBundle = storeGet('lastBundle', null);
  const jobBox = h('div', {});
  const deployBox = h('div', { class: 'stack' });
  function drawDeploy() {
    clear(deployBox);
    const copy = app.state.settings.paths.test_copy;
    deployBox.append(h('h3', { text: t('b.deploy') }));
    if (!copy) { deployBox.append(h('p', { class: 'small muted', text: t('b.deploy.nocopy') })); return; }
    if (lastBundle) storeSet('lastBundle', lastBundle);
    deployBox.append(h('p', { class: 'small', text: t('b.deploy.to', { copy }) }),
      lastBundle ? h('p', { class: 'small muted mono', text: lastBundle }) : h('p', { class: 'small muted', text: t('b.deploy.first') }),
      h('div', { class: 'row' },
        h('button', { type: 'button', class: 'primary', disabled: !lastBundle, text: t('b.deploy.go'), onclick: async () => {
          if (!await confirmDialog(t('b.deploy'), t('b.deploy.confirm', { copy }))) return;
          runTool('deploy', { install: copy, bundle: [lastBundle], builder: 'Settler' });
        } }),
        h('button', { type: 'button', text: t('b.deploy.undo'), onclick: async () => {
          if (!await confirmDialog(t('b.deploy.undo'), t('b.undo.confirm', { copy }))) return;
          runTool('deploy_undo', { install: copy });
        } })));
  }

  async function runTool(id, values) {
    try {
      const r = await api('/api/tools/' + id, { values });
      watchJob(r.job, jobBox, {});
    } catch (e) { toast(e.message, 'bad'); }
  }

  async function saveParams() {
    const blob = new Blob([JSON.stringify(state.params, null, 1)], { type: 'application/json' });
    const a = h('a', { href: URL.createObjectURL(blob), download: (state.params.name || 'building') + '.json' });
    document.body.append(a); a.click(); a.remove();
  }

  async function loadParams() {
    const input = h('input', { type: 'file', accept: '.json,application/json' });
    input.addEventListener('change', async () => {
      try {
        const data = JSON.parse(await input.files[0].text());
        await api('/api/building/preview', { params: data, texture: 128 });       // checked by the server
        state.params = data; state.preset = null;
        drawPresets(); drawForm(); refresh(true);
      } catch (e) { toast(t('b.load.bad') + ' ' + e.message, 'bad'); }
    });
    input.click();
  }

  // -- the preview loop ---------------------------------------------------------------------
  const sheetLater = debounce(loadSheet, 600);
  const fullLater = debounce(() => refresh(false), 900);
  function changed(dragging) {
    storeSet('building', { preset: state.preset, params: state.params });
    refresh(false, false, dragging);
    if (!dragging) sheetLater();
  }

  let inFlight = false, queued = null;
  async function refresh(frame, damaged, dragging) {
    const job = { frame, damaged: damaged || state.view === 'damaged', dragging };
    if (inFlight) { queued = job; return; }
    inFlight = true;
    busy.hidden = false;
    const seq = ++state.seq;
    try {
      // the full texture is shown up to FULL pixels: a 2048 African texture takes half a minute
      // to paint, which the export does once
      const size = Math.min(dragging || !state.full ? QUICK : FULL, state.params.texture_size);
      const d = await api('/api/building/preview', { params: state.params, texture: size, damaged: job.damaged });
      if (seq === state.seq) {
        state.preview = d;
        viewer.setModel(d, d.texture, frame || !viewer.mesh);
        drawNumbers();
        if (state.view !== '3d') drawTexture();
        if (frame) loadSheet();
      }
    } catch (e) {
      toast(e.message, 'bad');
    } finally {
      inFlight = false;
      busy.hidden = true;
      if (queued) { const q = queued; queued = null; refresh(q.frame, q.damaged, q.dragging); }
      else if (dragging && state.full) fullLater();
    }
  }

  async function loadSheet() {
    try {
      const s = await api('/api/building/sheet', { params: state.params });
      state.sheet = s; state.budget = s.budget;
      sheetBox.innerHTML = markdown(s.markdown);
      drawNumbers();
    } catch (e) { sheetBox.textContent = e.message; }
  }

  drawPresets();
  drawForm();
  drawActions();
  showView();
  refresh(true);
}

function clampNum(f, v) {
  let x = Number(v);
  if (Number.isNaN(x)) x = f.default;
  if (f.min !== undefined) x = Math.max(f.min, x);
  if (f.max !== undefined) x = Math.min(f.max, x);
  return f.kind === 'int' ? Math.round(x) : x;
}

function toHex(rgb) { return '#' + rgb.map(c => c.toString(16).padStart(2, '0')).join(''); }
function fromHex(hex) { return [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)); }

async function saveSnapshot(viewer) {
  const url = viewer.snapshot();
  const a = h('a', { href: url, download: 'building.png' });
  document.body.append(a); a.click(); a.remove();
}
