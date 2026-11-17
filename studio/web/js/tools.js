// SPDX-License-Identifier: GPL-3.0-or-later
// Every command-line tool as a form: the catalog's options, what the tool needs and writes, a
// trial before a change in place, a confirmation before touching the test copy.
import { api, clear, confirmDialog, h, pick, storeGet, storeSet, t, toast, tr } from './core.js';
import { watchJob } from './jobs.js';

let catalog = null;

export async function loadCatalog(force) {
  if (!catalog || force) catalog = await api('/api/catalog');
  return catalog;
}

export async function areaScreen(main, app, area) {
  const cat = await loadCatalog(true);
  clear(main);
  main.append(h('div', { class: 'head' }, h('div', {}, h('h1', { text: tr(cat.areas[area]) }),
    h('p', { class: 'muted', text: t('area.' + area + '.intro') }))));
  const extra = app.extraFor?.(area);
  if (extra) main.append(extra);
  const grid = h('div', { class: 'tool-grid' });
  main.append(grid);
  for (const tool of cat.tools.filter(x => x.area === area)) {
    const missing = tool.needs.filter(n => !cat.requirements[n]);
    grid.append(h('button', { type: 'button', class: 'card tool-card', onclick: () => app.go(`tool/${tool.id}`) },
      h('strong', { text: tr(tool.title) }), h('span', { class: 'muted', text: tr(tool.desc) }),
      h('div', { class: 'row' },
        tool.engine === 'blender' ? h('span', { class: 'pill', text: 'Blender' }) : null,
        tool.writes === 'copy' ? h('span', { class: 'pill warn', text: t('tool.copy') }) : null,
        tool.writes === 'in_place' ? h('span', { class: 'pill warn', text: t('tool.inplace') }) : null,
        missing.length ? h('span', { class: 'pill bad', text: t('tool.missing', { n: missing.length }) }) : null)));
  }
}

export async function toolScreen(main, app, id) {
  const cat = await loadCatalog(true);
  const tool = cat.tools.find(x => x.id === id);
  clear(main);
  if (!tool) { main.append(h('p', { text: t('tool.unknown') })); return; }
  const settings = app.state.settings.paths;
  const saved = storeGet('tool.' + id, {});
  const values = {};
  const missing = tool.needs.filter(n => !cat.requirements[n]);
  const formBox = h('form', { class: 'card stack', onsubmit: e => e.preventDefault() });
  const jobBox = h('div', {});
  main.append(h('div', { class: 'head' }, h('div', {},
    h('button', { type: 'button', class: 'ghost small', text: '← ' + tr(cat.areas[tool.area]), onclick: () => app.go(tool.area) }),
    h('h1', { text: tr(tool.title) }), h('p', { class: 'muted', text: tr(tool.desc) }))),
    h('div', { class: 'tool' }, formBox, jobBox));

  formBox.append(h('div', { class: 'row small' }, h('span', { class: 'pill', text: tr(cat.writes[tool.writes]) }),
    tool.engine === 'blender' ? h('span', { class: 'pill', text: t('tool.blender') }) : null,
    tool.minutes ? h('span', { class: 'pill', text: t('tool.minutes', { n: tool.minutes }) }) : null));
  if (missing.length) {
    formBox.append(h('div', { class: 'notice bad small' }, h('strong', { text: t('tool.needs') }),
      h('ul', {}, missing.map(n => h('li', { text: tr(cat.needs[n]) }))),
      h('button', { type: 'button', class: 'small', text: t('nav.settings'), onclick: () => app.go('settings') })));
  }

  for (const a of tool.args) {
    let v = saved[a.key];
    if (v === undefined || v === '') v = a.setting && settings[a.setting] ? settings[a.setting] : a.default;
    if ((a.kind === 'folders' || a.kind === 'files') && typeof v === 'string' && v) v = [v];
    values[a.key] = v ?? (a.kind === 'bool' ? false : a.kind === 'folders' || a.kind === 'files' ? [] : '');
    formBox.append(argField(tool, a, values));
  }

  const runBtn = h('button', { type: 'button', class: 'primary', text: tool.trial ? t('tool.trial') : t('tool.run') });
  const applyBtn = tool.trial ? h('button', { type: 'button', class: 'danger', disabled: true, text: t('tool.apply') }) : null;
  if (tool.trial) formBox.append(h('p', { class: 'small muted', text: t('tool.trial.help') }));
  formBox.append(h('div', { class: 'row' }, runBtn, applyBtn,
      h('button', { type: 'button', class: 'ghost', text: t('tool.reset'),
        onclick: () => { storeSet('tool.' + id, {}); toolScreen(main, app, id); } })));

  let trialOf = null;
  const snapshot = () => JSON.stringify(values);
  const start = async (apply) => {
    storeSet('tool.' + id, values);
    if (tool.confirm && (apply || !tool.trial)) {
      if (!await confirmDialog(tr(tool.title), tr(tool.confirm))) return;
    }
    if (apply && !await confirmDialog(tr(tool.title), t('tool.apply.confirm'))) return;
    try {
      const body = { values: clean(values) };
      if (apply) body.apply = true;
      const r = await api('/api/tools/' + id, body);
      const at = snapshot();
      watchJob(r.job, jobBox, { onDone: j => {
        if (r.trial) { trialOf = j.status === 'done' && j.code === 0 ? at : null; if (applyBtn) applyBtn.disabled = trialOf !== snapshot(); }
      } });
    } catch (e) { toast(e.message, 'bad'); }
  };
  runBtn.addEventListener('click', () => start(false));
  applyBtn?.addEventListener('click', () => start(true));
  formBox.addEventListener('input', () => { if (applyBtn) applyBtn.disabled = trialOf !== snapshot(); });
  formBox.addEventListener('change', () => { if (applyBtn) applyBtn.disabled = trialOf !== snapshot(); });
}

function clean(values) {
  const out = {};
  for (const [k, v] of Object.entries(values)) {
    if (v === '' || v === null || v === undefined || v === false || (Array.isArray(v) && !v.length)) continue;
    out[k] = v;
  }
  return out;
}

function argField(tool, a, values) {
  const id = `a-${tool.id}-${a.key}`;
  const label = h('label', { for: id, class: a.required ? 'req' : '', text: tr(a.label) });
  const help = tr(a.help);
  const set = v => { values[a.key] = v; };
  let ctl;
  switch (a.kind) {
    case 'bool':
      ctl = h('input', { id, type: 'checkbox', checked: !!values[a.key], onchange: e => set(e.target.checked) });
      break;
    case 'choice':
      ctl = h('select', { id, onchange: e => set(e.target.value) },
        a.choices.map(c => h('option', { value: c.value, selected: String(c.value) === String(values[a.key] ?? ''), text: c.label === '' ? t('tool.default') : c.label })));
      break;
    case 'int': case 'float':
      ctl = h('input', { id, type: 'number', step: a.kind === 'int' ? 1 : 'any', value: values[a.key] ?? '', placeholder: a.placeholder,
        oninput: e => set(e.target.value) });
      break;
    case 'color': {
      const hex = String(values[a.key] || 'FF8C00').replace('#', '');
      ctl = [h('input', { id, type: 'color', value: '#' + hex, oninput: e => set(e.target.value.slice(1).toUpperCase()) })];
      set(hex);
      break;
    }
    case 'file': case 'save': case 'folder': case 'outdir': {
      const input = h('input', { id, type: 'text', value: values[a.key] ?? '', placeholder: a.placeholder || (a.work ? t('tool.out.default') : ''),
        oninput: e => set(e.target.value) });
      const mode = a.kind === 'file' ? 'file' : a.kind === 'save' ? 'save' : 'folder';
      ctl = [input, h('button', { type: 'button', text: t('browse'), onclick: async () => {
        const p = await pick(mode, { title: tr(a.label), initial: input.value, filters: a.filters || [] }).catch(e => toast(e.message, 'bad'));
        if (p) { input.value = p; set(p); input.dispatchEvent(new Event('change', { bubbles: true })); }
      } })];
      break;
    }
    case 'files': case 'folders': {
      const list = h('div', { class: 'stack grow' });
      const draw = () => {
        clear(list);
        for (const [i, p] of (values[a.key] || []).entries()) {
          list.append(h('div', { class: 'row' }, h('span', { class: 'mono small grow', text: p }),
            h('button', { type: 'button', class: 'ghost small', text: '×', 'aria-label': t('remove'),
              onclick: () => { values[a.key].splice(i, 1); draw(); list.dispatchEvent(new Event('change', { bubbles: true })); } })));
        }
        const input = h('input', { type: 'text', placeholder: t('tool.addpath'), id });
        list.append(h('div', { class: 'row' }, input,
          h('button', { type: 'button', text: '+', 'aria-label': t('add'), onclick: () => { if (input.value.trim()) { values[a.key] = [...(values[a.key] || []), input.value.trim()]; draw(); } } }),
          h('button', { type: 'button', text: t('browse'), onclick: async () => {
            const mode = a.kind === 'files' ? 'files' : 'folder';
            const got = await pick(mode, { title: tr(a.label), filters: a.filters || [] }).catch(e => toast(e.message, 'bad'));
            const add = Array.isArray(got) ? got : got ? [got] : [];
            if (add.length) { values[a.key] = [...(values[a.key] || []), ...add]; draw(); list.dispatchEvent(new Event('change', { bubbles: true })); }
          } })));
      };
      draw();
      ctl = [list];
      break;
    }
    default:
      ctl = h('input', { id, type: 'text', value: values[a.key] ?? '', placeholder: a.placeholder, oninput: e => set(e.target.value) });
  }
  return h('div', { class: 'field' }, label, h('div', { class: 'ctl' }, ctl), help ? h('div', { class: 'help', text: help }) : null);
}
