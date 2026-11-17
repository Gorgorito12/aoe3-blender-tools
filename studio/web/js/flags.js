// SPDX-License-Identifier: GPL-3.0-or-later
// The flag designer: a design picture, cropped on screen, shown as every texture of a civ's flag
// set (the in-game flag, the postgame flag, the buttons in their four states) as the game copy's
// own sets are made, next to one of them; then the set written.
import { api, clear, h, pick, storeGet, storeSet, t, toast } from './core.js';
import { ImageView, fileToPng } from './canvas2d.js';
import { showOutputs } from './jobs.js';

const STATES = ['normal', 'click', 'high', 'disable'];

export async function flagsScreen(main, app) {
  clear(main);
  const saved = storeGet('flags', { flags_dir: 'War of the Triple Alliance\\Flags', buttons_dir: 'War of the Triple Alliance\\Buttons', name: '' });
  let session = null, design = null, crop = null, compare = '';
  const game = h('input', { type: 'text', class: 'grow', value: saved.game || app.state.settings.paths.game || '', placeholder: t('f.game') });
  const fdir = h('input', { type: 'text', class: 'grow', value: saved.flags_dir });
  const bdir = h('input', { type: 'text', class: 'grow', value: saved.buttons_dir });
  const measured = h('span', { class: 'small muted' });
  const measureBtn = h('button', { type: 'button', class: 'primary', text: t('f.measure'), onclick: () => measure() });
  const work = h('div', {});
  main.append(h('div', { class: 'head' }, h('div', {},
    h('button', { type: 'button', class: 'ghost small', text: '← ' + t('nav.art'), onclick: () => app.go('art') }),
    h('h1', { text: t('f.title') }), h('p', { class: 'muted', text: t('f.intro') }))),
    h('div', { class: 'card stack' },
      h('div', { class: 'row' }, h('strong', { text: t('f.copy') }), game,
        h('button', { type: 'button', text: t('browse'), onclick: async () => { const p = await pick('folder', { title: t('f.copy') }); if (p) game.value = p; } })),
      h('div', { class: 'row small' }, t('f.flags'), fdir, t('f.buttons'), bdir),
      h('div', { class: 'row' }, measureBtn, measured)),
    work);

  async function measure() {
    storeSet('flags', { ...saved, game: game.value, flags_dir: fdir.value, buttons_dir: bdir.value });
    measureBtn.disabled = true;
    measured.textContent = t('b.working');
    try {
      const r = await api('/api/flags/measure', { game: game.value, flags_dir: fdir.value, buttons_dir: bdir.value });
      session = r.session;
      measured.textContent = t('f.measured', { n: r.count });
      build(r);
    } catch (e) {
      measured.textContent = '';
      toast(e.message, 'bad');
    } finally { measureBtn.disabled = false; }
  }

  let view = null, cells = null, mine = null, theirs = null;
  app.onLeave(() => view?.dispose());

  function build(r) {
    view?.dispose();
    clear(work);
    const picture = h('div', { class: 'viewport', style: { height: '320px', background: 'var(--viewport)' } });
    const chooser = h('button', { type: 'button', class: 'primary', text: t('f.design'), onclick: () => chooseDesign() });
    const resetCrop = h('button', { type: 'button', text: t('f.crop.reset'), onclick: () => { crop = null; view.box = null; view.draw(); refresh(); } });
    const cmp = h('select', { onchange: e => { compare = e.target.value; showExisting(); } },
      h('option', { value: '', text: t('f.compare.none') }), r.sets.map(n => h('option', { value: n, text: n })));
    cells = h('div', { class: 'flagsheet' });
    const name = h('input', { type: 'text', value: saved.name, placeholder: 'mynation', style: { width: '160px' } });
    const outBox = h('div', { class: 'stack' });
    work.append(h('div', { class: 'flags' },
      h('section', { class: 'stack' }, h('div', { class: 'row' }, chooser, resetCrop), picture,
        h('p', { class: 'small muted', text: t('f.crop.help') }),
        h('div', { class: 'card stack' }, h('h2', { text: t('f.write') }),
          h('div', { class: 'row' }, h('label', { class: 'small', text: t('f.name') }), name,
            h('button', { type: 'button', class: 'primary', text: t('f.write.go'), onclick: () => write(name.value.trim(), outBox) })),
          h('p', { class: 'small muted', text: t('f.write.help') }), outBox)),
      h('section', { class: 'stack' }, h('div', { class: 'row' }, h('h2', { class: 'grow', text: t('f.set') }),
        h('label', { class: 'row small' }, t('f.compare'), cmp)), cells)));
    view = new ImageView(picture, { onBox: box => { crop = box; refresh(); } });
    view.smooth = true;
    drawCells();
    if (design) { view.setImage(design); refresh(); }
  }

  // one row per texture kind: this design's, and the set compared with
  function drawCells() {
    clear(cells);
    mine = {}; theirs = {};
    const rows = [['flag', t('f.k.flag'), 2], ['postgame', t('f.k.postgame'), 2.5]];
    for (const s of STATES) rows.push(['button_' + s, t('f.k.button', { s: t('f.s.' + s) }), 2]);
    for (const s of STATES) rows.push(['large_' + s, t('f.k.large', { s: t('f.s.' + s) }), 2]);
    for (const [key, label, zoom] of rows) {
      mine[key] = h('img', { alt: label, class: 'checker pixel' });
      theirs[key] = h('img', { alt: '', class: 'checker pixel' });
      for (const img of [mine[key], theirs[key]]) img.addEventListener('load', () => { img.style.width = img.naturalWidth * zoom + 'px'; });
      cells.append(h('div', { class: 'flagrow' }, h('span', { class: 'small', text: label }), mine[key], theirs[key]));
    }
  }

  // the design's file input stays in the page (hidden): a picture can also be dropped on it
  const fileInput = h('input', { type: 'file', accept: 'image/*', id: 'flag-design', hidden: true,
    onchange: () => { if (fileInput.files[0]) useDesign(fileInput.files[0]); } });
  main.append(fileInput);
  function chooseDesign() { fileInput.value = ''; fileInput.click(); }

  async function useDesign(file) {
    try {
      design = await fileToPng(file, 1024);
      crop = null;
      if (view) { view.box = null; await view.setImage(design); }
      refresh();
    } catch (e) { toast(e.message, 'bad'); }
  }
  main.addEventListener('dragover', e => e.preventDefault());
  main.addEventListener('drop', e => {
    e.preventDefault();
    const f = [...(e.dataTransfer?.files || [])].find(x => x.type.startsWith('image/'));
    if (f) useDesign(f);
  });

  let busy = false, again = false;
  async function refresh() {
    if (!design || !session) return;
    if (busy) { again = true; return; }
    busy = true;
    try {
      const r = await api('/api/flags/preview', { session, design, crop });
      for (const [k, url] of Object.entries(r)) if (mine[k]) mine[k].src = url;
    } catch (e) { toast(e.message, 'bad'); } finally {
      busy = false;
      if (again) { again = false; refresh(); }
    }
  }

  async function showExisting() {
    for (const img of Object.values(theirs)) img.removeAttribute('src');
    if (!compare) return;
    try {
      const r = await api('/api/flags/preview', { session, existing: compare });
      for (const [k, url] of Object.entries(r)) if (theirs[k]) theirs[k].src = url;
    } catch (e) { toast(e.message, 'bad'); }
  }

  async function write(name, box) {
    if (!design) { toast(t('f.nodesign'), 'bad'); return; }
    storeSet('flags', { ...storeGet('flags', saved), name });
    try {
      const r = await api('/api/flags/write', { session, design, crop, name });
      toast(t('f.written', { n: Object.keys(r.files).length }), 'ok');
      showOutputs([r.sheet, r.folder], box);
    } catch (e) { toast(e.message, 'bad'); }
  }

  if (game.value) measure();
}
