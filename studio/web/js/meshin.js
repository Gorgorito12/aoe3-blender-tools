// SPDX-License-Identifier: GPL-3.0-or-later
// Your own model: a static .obj / .glb / .gltf made ready for the game (axes, size, ground,
// normals), seen in 3D beside a person and its obstruction, checked as a generated building is,
// then written as a game bundle by scripts/mesh_to_game.py.
import { api, clear, debounce, fmt, h, pick, storeGet, storeSet, t, toast } from './core.js';
import { Viewer } from './viewer.js';
import { watchJob } from './jobs.js';

// a picture the repository cannot read (a JPEG) decoded here and returned as a PNG
async function toPng(dataUrl) {
  const blob = await (await fetch(dataUrl)).blob();
  const bmp = await createImageBitmap(blob);
  const c = document.createElement('canvas');
  c.width = bmp.width; c.height = bmp.height;
  c.getContext('2d').drawImage(bmp, 0, 0);
  return c.toDataURL('image/png');
}

export async function meshinScreen(main, app) {
  clear(main);
  const last = storeGet('meshin', { path: '', up: 'y', scale: 1, fit_units: '', turn: 0, flat: false, kind: 'BUILDING',
    name: '', display: '', template: 'House', prefix: 'mod', texture: 'DXT3' });
  let picture = null, data = null;
  main.append(h('div', { class: 'head' }, h('div', {},
    h('button', { type: 'button', class: 'ghost small', text: '← ' + t('nav.buildings'), onclick: () => app.go('buildings') }),
    h('h1', { text: t('m.title') }), h('p', { class: 'muted', text: t('m.intro') }))));

  // -- the file and how to read it ------------------------------------------------------------
  const path = h('input', { type: 'text', class: 'grow mono', value: last.path, placeholder: t('m.path.ph'), 'aria-label': t('m.path'),
    onchange: () => { picture = null; reload(); } });
  const browse = h('button', { type: 'button', text: t('browse'), onclick: async () => {
    const p = await pick('file', { title: t('m.path'), initial: path.value, filters: [['Model', '*.obj *.glb *.gltf']] }).catch(() => null);
    if (p) { path.value = p; picture = null; reload(); }
  } });
  const sel = (key, values, label) => h('label', { class: 'stack small' }, label,
    h('select', { 'data-key': key, onchange: () => reload() }, values.map(([v, text]) => h('option', { value: v, text, selected: String(v) === String(last[key]) }))));
  const num = (key, label, help, step) => h('label', { class: 'stack small', title: help }, label,
    h('input', { type: 'number', 'data-key': key, value: last[key], step, min: 0, onchange: () => reload() }));
  const flat = h('input', { type: 'checkbox', 'data-key': 'flat', checked: last.flat, onchange: () => reload() });
  const opts = h('div', { class: 'row wrap' },
    sel('up', [['y', t('m.up.y')], ['z', t('m.up.z')]], t('m.up')),
    num('scale', t('m.scale'), t('m.scale.help'), 'any'),
    num('fit_units', t('m.fit'), t('m.fit.help'), 0.5),
    sel('turn', [[0, '0°'], [90, '90°'], [180, '180°'], [270, '270°']], t('m.turn')),
    sel('kind', [['BUILDING', t('m.kind.building')], ['PROP', t('m.kind.prop')]], t('m.kind')),
    h('label', { class: 'row small' }, flat, t('m.flat')));
  main.append(h('div', { class: 'card stack' }, h('div', { class: 'row' }, path, browse), opts));

  const values = () => {
    const v = { path: path.value.trim() };
    for (const el of opts.querySelectorAll('[data-key]')) v[el.dataset.key] = el.type === 'checkbox' ? el.checked : el.value;
    return v;
  };

  // -- the view and what it found ---------------------------------------------------------------
  const view = h('div', { class: 'viewport meshin-view' });
  const facts = h('div', { class: 'stack small' });
  const exportBox = h('div', { class: 'card stack' });
  main.append(h('div', { class: 'meshin-grid' }, view, h('div', { class: 'card stack meshin-side' }, facts)), exportBox);
  const viewer = new Viewer(view);
  app.onLeave(() => viewer.dispose());
  const over = h('div', { class: 'over' });
  view.append(over);
  const show = { person: true, obstruction: true };
  for (const [mode, text] of [['texture', t('b.v.texture')], ['clay', t('b.v.clay')]]) {
    over.append(h('button', { type: 'button', 'aria-pressed': String(viewer.mode === mode), 'data-mode': mode, text,
      onclick: () => { viewer.setMode(mode); over.querySelectorAll('[data-mode]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === mode))); } }));
  }
  over.append(h('button', { type: 'button', 'aria-pressed': 'false', text: t('b.v.wire'),
    onclick: e => { const on = e.target.getAttribute('aria-pressed') !== 'true'; e.target.setAttribute('aria-pressed', String(on)); viewer.toggle('wire', on); } }));
  for (const [what, text] of [['person', t('b.v.person')], ['obstruction', t('b.v.obstruction')]]) {
    over.append(h('button', { type: 'button', 'aria-pressed': 'true', text, onclick: e => {
      show[what] = !show[what]; e.target.setAttribute('aria-pressed', String(show[what])); extras();
    } }));
  }
  const extras = () => {
    if (!data) return;
    viewer.setExtras({ person: show.person ? [data.footprint[0] / 2 + 1.2, -data.footprint[1] / 2] : null,
      obstruction: show.obstruction ? data.obstruction_m : null });
  };

  const reload = debounce(async () => {
    const v = values();
    storeSet('meshin', { ...last, ...v });
    if (!v.path) { clear(facts).append(h('p', { class: 'muted', text: t('m.none') })); return; }
    clear(facts).append(h('p', { class: 'muted', text: t('b.working') }));
    try {
      let r = await api('/api/mesh/load', { ...v, picture });
      if (r.decode) {                                // a JPEG: decoded here, then read again
        picture = await toPng(r.decode);
        r = await api('/api/mesh/load', { ...v, picture });
      }
      data = r;
      viewer.setModel(r, r.texture, true);
      extras();
      drawFacts();
      drawExport();
    } catch (e) {
      data = null;
      clear(facts).append(h('p', { class: 'bad', text: e.message }));
      clear(exportBox);
    }
  }, 250);

  function drawFacts() {
    const d = data;
    const row = (k, v) => [h('dt', { text: k }), h('dd', { text: v })];
    const level = { ERROR: 'bad', WARNING: 'warn', INFO: 'muted' };
    clear(facts).append(...[
      h('dl', { class: 'kv' },
        row(t('m.tris'), fmt(d.triangles)), row(t('m.verts'), fmt(d.vertices)),
        row(t('m.size'), `${d.footprint[0]} × ${d.footprint[1]} m, ${d.height} m`),
        row(t('m.units'), `${d.units[0]} × ${d.units[1]}` + (d.class ? ` (${t('m.class', { c: d.class })})` : '')),
        row(t('m.obstruction'), `${d.obstruction[0]} × ${d.obstruction[1]}`),
        row(t('m.texsize'), `${d.texture_size[0]} × ${d.texture_size[1]}` + (picture ? ' · ' + t('m.decoded') : ''))),
      d.warnings.length ? h('h4', { text: t('m.warnings') }) : null,
      ...d.warnings.map(w => h('p', { class: 'warn', text: w })),
      h('h4', { text: t('m.checks') }),
      ...d.checks.map(c => h('p', { class: level[c.level] || '', text: c.message })),
      h('p', { class: 'muted', text: t('m.noextras') })].filter(Boolean));
  }

  function drawExport() {
    const field = (key, label, attrs = {}) => h('label', { class: 'stack small' }, label,
      h('input', { type: 'text', 'data-x': key, value: last[key] || '', ...attrs }));
    const fmtSel = h('select', { 'data-x': 'texture' }, ['DXT3', 'DXT1', 'BGRA'].map(f => h('option', { value: f, text: f, selected: f === last.texture })));
    const out = h('input', { type: 'text', class: 'grow mono', placeholder: t('m.out.ph'), 'data-x': 'out', value: '' });
    const box = h('div', {});
    const name = (last.name || path.value.split(/[\\/]/).pop().replace(/\.[^.]+$/, '')).replace(/[^A-Za-z0-9_]/g, '_');
    clear(exportBox).append(h('h3', { text: t('m.export') }),
      h('div', { class: 'row wrap' }, field('name', t('m.name'), { value: name, pattern: '[A-Za-z0-9_]+' }),
        field('display', t('m.display')), field('template', t('m.template')), field('prefix', t('m.prefix')),
        h('label', { class: 'stack small' }, t('m.format'), fmtSel)),
      h('div', { class: 'row' }, out, h('button', { type: 'button', text: t('browse'), onclick: async () => {
        const p = await pick('folder', { title: t('m.out') }).catch(() => null);
        if (p) out.value = p;
      } })),
      h('div', { class: 'row' }, h('button', { type: 'button', class: 'primary', text: t('m.go'), onclick: async () => {
        const x = {};
        for (const el of exportBox.querySelectorAll('[data-x]')) x[el.dataset.x] = el.value.trim();
        storeSet('meshin', { ...storeGet('meshin', last), ...values(), ...x, out: undefined });
        try {
          const r = await api('/api/mesh/export', { ...values(), ...x, picture, out: x.out || null });
          watchJob(r.job, box, { onDone: () => toast(t('m.done', { out: r.out }), 'ok') });
        } catch (e) { toast(e.message, 'bad'); }
      } }), h('button', { type: 'button', text: t('m.deploy'), onclick: () => app.go('tool/deploy') })),
      box);
  }

  reload();
}
