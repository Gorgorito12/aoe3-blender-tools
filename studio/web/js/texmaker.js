// SPDX-License-Identifier: GPL-3.0-or-later
// The texture maker: a photograph, the square of it to use, the tileable texture made from it at
// once (no ComfyUI needed) seen alone and tiled 3 by 3, measured against the mod's own textures;
// then kept in the library, which the buildings can paint with.
import { api, clear, confirmDialog, debounce, fmt, h, storeGet, storeSet, t, toast } from './core.js';
import { ImageView, fileToPng } from './canvas2d.js';
import { watchJob } from './jobs.js';

export async function texmakerScreen(main, app) {
  clear(main);
  const o = storeGet('tex', { cx: 0.5, cy: 0.5, part: 1, size: 256, light: true, fit: false, material: '', category: 'buildings',
    name: '', licence: '', style: '', role: '', tile_m: 2, prompt: '', strength: 0.6, seed: 1, folder: '' });
  let session = null, width = 0, height = 0, lib = null;
  const save = () => storeSet('tex', o);

  const photoInput = h('input', { type: 'file', accept: 'image/*', id: 'tex-photo', hidden: true,
    onchange: () => { if (photoInput.files[0]) usePhoto(photoInput.files[0]); } });
  const photo = h('div', { class: 'viewport', style: { height: '380px', background: 'var(--viewport)' } });
  const texImg = h('img', { alt: t('x.texture'), class: 'texout' });
  const sheetImg = h('img', { alt: t('x.sheet'), class: 'texout' });
  const report = h('div', { class: 'small' });
  const busy = h('span', { class: 'small muted' });
  const libBox = h('div', { class: 'stack' });
  const aiBox = h('div', {});
  main.append(photoInput, h('div', { class: 'head' }, h('div', {},
    h('button', { type: 'button', class: 'ghost small', text: '← ' + t('nav.textures'), onclick: () => app.go('textures') }),
    h('h1', { text: t('x.title') }), h('p', { class: 'muted', text: t('x.intro') }))));

  // -- the crop ---------------------------------------------------------------------------------
  const slider = (key, label, min, max, step) => {
    const num = h('span', { class: 'small mono', text: fmt(o[key], 2) });
    const input = h('input', { type: 'range', min, max, step, value: o[key], oninput: e => {
      o[key] = Number(e.target.value); num.textContent = fmt(o[key], 2); showCrop(); later(); } });
    sliders[key] = input;
    return h('div', { class: 'field' }, h('label', { text: label }), h('div', { class: 'ctl' }, input, num));
  };
  const sliders = {};
  const view = new ImageView(photo, { onBox: box => {
    // a box drawn on the photograph: its centre, and its larger side as the square's
    const [x0, y0, x1, y1] = box;
    o.cx = (x0 + x1) / 2; o.cy = (y0 + y1) / 2;
    const side = Math.max((x1 - x0) * width, (y1 - y0) * height);
    o.part = Math.max(0.02, Math.min(1, side / Math.min(width, height)));
    for (const k of ['cx', 'cy', 'part']) { sliders[k].value = o[k]; sliders[k].dispatchEvent(new Event('input')); }
  } });
  view.smooth = true;
  app.onLeave(() => view.dispose());
  function showCrop() {
    if (!width) return;
    const n = Math.min(width, height) * o.part;
    const x0 = Math.min(Math.max(o.cx * width - n / 2, 0), width - n), y0 = Math.min(Math.max(o.cy * height - n / 2, 0), height - n);
    view.box = [x0, y0, x0 + n, y0 + n];
    view.draw();
  }

  // -- settings ---------------------------------------------------------------------------------
  const check = (key, label, help) => h('label', { class: 'row small', title: help || '' },
    h('input', { type: 'checkbox', checked: !!o[key], onchange: e => { o[key] = e.target.checked; refresh(); } }), label);
  const text = (key, label, placeholder) => h('div', { class: 'field' }, h('label', { text: label }),
    h('div', { class: 'ctl' }, h('input', { type: 'text', value: o[key] ?? '', placeholder: placeholder || '', onchange: e => { o[key] = e.target.value.trim(); refresh(); } })));
  const sizeSel = h('select', { onchange: e => { o.size = Number(e.target.value); refresh(); } },
    [128, 256, 512].map(v => h('option', { value: v, text: v + ' px', selected: v === o.size })));
  const styleSel = h('select', {});
  const roleSel = h('select', {});
  const fillRoles = () => {
    clear(styleSel).append(h('option', { value: '', text: t('x.style.none') }),
      ...Object.keys(lib?.roles || {}).map(s => h('option', { value: s, text: t('style.' + s, null, s), selected: s === o.style })));
    clear(roleSel).append(h('option', { value: '', text: '—' }),
      ...((lib?.roles || {})[o.style] || []).map(r => h('option', { value: r, text: r, selected: r === o.role })));
  };
  styleSel.addEventListener('change', e => { o.style = e.target.value; o.role = ''; fillRoles(); save(); });
  roleSel.addEventListener('change', e => { o.role = e.target.value; save(); });
  const keepCard = h('div', { class: 'card stack' }, h('h2', { text: t('x.keep') }),
    text('name', t('x.name'), 'plaster_sun'), text('licence', t('x.licence'), t('x.licence.ph')),
    h('div', { class: 'field' }, h('label', { text: t('x.style') }), h('div', { class: 'ctl' }, styleSel, roleSel)),
    h('div', { class: 'field' }, h('label', { text: t('x.tile') }), h('div', { class: 'ctl' },
      h('input', { type: 'number', min: 0.2, max: 20, step: 0.1, value: o.tile_m, style: { width: '80px' }, onchange: e => { o.tile_m = Number(e.target.value); save(); } }),
      h('span', { class: 'small muted', text: 'm' }))),
    h('p', { class: 'small muted', text: t('x.keep.help') }),
    h('button', { type: 'button', class: 'primary', text: t('x.keep.go'), onclick: () => keep() }));
  const comfy = app.state.requirements.comfy;
  const aiCard = h('div', { class: 'card stack' }, h('h2', { text: t('x.ai') }),
    comfy ? null : h('p', { class: 'small notice', text: t('b.ai.off') }),
    text('prompt', t('x.prompt'), 'weathered lime plaster'),
    h('div', { class: 'row small' }, t('r.k.strength'),
      h('input', { type: 'number', min: 0.1, max: 0.95, step: 0.05, value: o.strength, style: { width: '70px' }, onchange: e => { o.strength = Number(e.target.value); save(); } }),
      t('r.k.seed'), h('input', { type: 'number', value: o.seed, style: { width: '70px' }, onchange: e => { o.seed = Number(e.target.value); save(); } })),
    h('button', { type: 'button', disabled: !comfy, text: t('x.ai.go'), onclick: () => ai() }), aiBox);

  main.append(h('div', { class: 'texmaker' },
    h('section', { class: 'stack' }, h('div', { class: 'row' },
      h('button', { type: 'button', class: 'primary', text: t('x.photo'), onclick: () => { photoInput.value = ''; photoInput.click(); } }),
      h('span', { class: 'small muted', text: t('x.photo.help') })), photo,
      slider('cx', t('x.cx'), 0, 1, 0.01), slider('cy', t('x.cy'), 0, 1, 0.01), slider('part', t('x.part'), 0.05, 1, 0.01)),
    h('section', { class: 'stack' }, h('div', { class: 'row' }, h('h2', { class: 'grow', text: t('x.result') }), busy),
      h('div', { class: 'row', style: { alignItems: 'flex-start' } },
        h('figure', {}, texImg, h('figcaption', { class: 'small muted', text: t('x.texture') })),
        h('figure', {}, sheetImg, h('figcaption', { class: 'small muted', text: t('x.sheet') }))), report,
      h('div', { class: 'card stack' }, h('div', { class: 'row' }, h('label', { class: 'small', text: t('x.size') }), sizeSel),
        check('light', t('x.light'), t('x.light.help')), check('fit', t('x.fit'), t('x.fit.help')),
        text('material', t('x.material'), 'plaster, wood, stone…'), text('category', t('x.category'), 'buildings'))),
    h('section', { class: 'stack' }, keepCard, aiCard)),
  h('div', { class: 'card stack', style: { marginTop: '14px' } }, libBox));

  main.addEventListener('dragover', e => e.preventDefault());
  main.addEventListener('drop', e => {
    e.preventDefault();
    const f = [...(e.dataTransfer?.files || [])].find(x => x.type.startsWith('image/'));
    if (f) usePhoto(f);
  });

  async function usePhoto(file) {
    try {
      const png = await fileToPng(file, 2048);
      const r = await api('/api/tex/source', { data: png });
      session = r.session; width = r.width; height = r.height;
      await view.setImage(png);
      showCrop();
      refresh();
    } catch (e) { toast(e.message, 'bad'); }
  }

  let inFlight = false, again = false;
  async function refresh() {
    save();
    if (!session) return;
    if (inFlight) { again = true; return; }
    inFlight = true; busy.textContent = t('b.working');
    try {
      const r = await api('/api/tex/preview', { session, ...o });
      texImg.src = r.texture; sheetImg.src = r.sheet;
      drawReport(r.report);
    } catch (e) { report.textContent = e.message; report.className = 'small bad'; } finally {
      inFlight = false; busy.textContent = '';
      if (again) { again = false; refresh(); }
    }
  }
  const later = debounce(refresh, 400);

  function drawReport(r) {
    clear(report); report.className = 'small';
    report.append(h('p', {}, t('x.seam', { before: fmt(r.seam_before, 2), after: fmt(r.seam, 2) })));
    if (r.style) {
      const row = (k) => {
        const v = r.style[k];
        const cls = Math.abs(v) <= 0.5 ? 'ok' : Math.abs(v) <= 1 ? 'warn' : 'bad';
        return h('span', { class: 'pill ' + cls, text: `${t('x.m.' + k)} ${v > 0 ? '+' : ''}${fmt(v, 2)}` });
      };
      report.append(h('p', {}, t('x.against', { what: r.style.against, n: r.style.textures })),
        h('div', { class: 'row' }, row('grain'), row('saturation'), row('luminance')),
        h('p', { class: 'muted', text: t('x.distance.help') }));
    }
    if (r.note) report.append(h('p', { class: 'warn', text: r.note }));
  }

  async function keep() {
    if (!session) { toast(t('x.nophoto'), 'bad'); return; }
    try {
      const r = await api('/api/tex/keep', { session, ...o, folder: o.folder || null });
      toast(t('x.kept', { name: r.entry.name }), 'ok');
      lib = r.library; drawLibrary();
    } catch (e) { toast(e.message, 'bad'); }
  }

  async function ai() {
    if (!session) { toast(t('x.nophoto'), 'bad'); return; }
    try {
      const r = await api('/api/tex/ai', { session, ...o });
      watchJob(r.job, aiBox, { onDone: () => loadLibrary() });
    } catch (e) { toast(e.message, 'bad'); }
  }

  // -- the library ------------------------------------------------------------------------------
  async function loadLibrary() {
    try { lib = await api('/api/tex/library', { folder: o.folder || null }); } catch (e) { toast(e.message, 'bad'); return; }
    fillRoles(); drawLibrary();
  }

  function drawLibrary() {
    clear(libBox);
    const inUse = Object.keys(lib.in_use || {}).length > 0;
    libBox.append(h('div', { class: 'row' }, h('h2', { class: 'grow', text: t('x.library') }),
      h('button', { type: 'button', text: t('open.folder'), onclick: () => api('/api/open', { path: lib.folder }).catch(e => toast(e.message, 'bad')) }),
      h('button', { type: 'button', class: inUse ? '' : 'primary', text: inUse ? t('x.use.off') : t('x.use.on'), title: t('x.use.help'),
        onclick: async () => { const r = await api('/api/tex/use', { on: !inUse, folder: o.folder || null }); lib.in_use = r.in_use;
          toast(Object.keys(r.in_use).length ? t('x.use.done', { list: Object.entries(r.in_use).map(([k, v]) => `${k}: ${v}`).join(', ') }) : t('x.use.none'), 'ok');
          drawLibrary(); } })), h('p', { class: 'small muted mono', text: lib.folder }));
    if (!lib.textures.length) { libBox.append(h('p', { class: 'muted small', text: t('x.library.empty') })); return; }
    const grid = h('div', { class: 'outputs' });
    for (const x of lib.textures) {
      const e = x.entry || {};
      grid.append(h('figure', {}, x.image ? h('img', { src: x.image, alt: x.name }) : null,
        h('figcaption', {}, h('strong', { text: x.name }), h('br'),
          h('span', { class: 'muted', text: [e.style, e.role].filter(Boolean).join(' · ') || t('x.style.none') }), h('br'),
          h('span', { class: 'muted', text: e.licence || '' }), h('br'),
          h('button', { type: 'button', class: 'ghost small danger', text: t('x.delete'), onclick: async () => {
            if (!await confirmDialog(t('x.delete'), t('x.delete.confirm', { name: x.name }))) return;
            try { lib = await api('/api/tex/delete', { name: x.name, folder: o.folder || null }); drawLibrary(); } catch (err) { toast(err.message, 'bad'); }
          } }))));
    }
    libBox.append(grid);
  }

  loadLibrary();
}
