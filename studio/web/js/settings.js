// SPDX-License-Identifier: GPL-3.0-or-later
// The folders and programs the studio works with, the language, and what it found.
import { api, clear, dialog, h, pick, t, toast } from './core.js';

export async function settingsScreen(main, app) {
  clear(main);
  const st = app.state;
  const s = st.settings;
  const paths = { ...s.paths };
  const form = h('div', { class: 'card stack' });
  const engines = h('div', { class: 'card stack' });
  main.append(h('div', { class: 'head' }, h('div', {}, h('h1', { text: t('nav.settings') }),
    h('p', { class: 'muted', text: t('settings.intro') }))),
    h('div', { class: 'tool' }, form, engines));

  for (const [key, d] of Object.entries(s.describe)) {
    const id = 's-' + key;
    const input = h('input', { id, type: 'text', value: paths[key] || '', oninput: e => { paths[key] = e.target.value; } });
    const browse = d.kind === 'url' ? null : h('button', { type: 'button', text: t('browse'), onclick: async () => {
      const p = await pick(d.kind === 'file' ? 'file' : 'folder', { title: t('set.' + key), initial: input.value,
        filters: d.kind === 'file' ? [['Program', '*.exe']] : [] }).catch(e => toast(e.message, 'bad'));
      if (p) { input.value = p; paths[key] = p; }
    } });
    form.append(h('div', { class: 'field' }, h('label', { for: id, text: t('set.' + key) }), h('div', { class: 'ctl' }, input, browse),
      h('div', { class: 'help', text: t('set.' + key + '.help', null, d.help) })));
  }
  form.append(h('div', { class: 'row' },
    h('button', { type: 'button', class: 'primary', text: t('save'), onclick: async () => {
      try { app.state = await api('/api/settings', { paths }); toast(t('settings.saved'), 'ok'); settingsScreen(main, app); }
      catch (e) { toast(e.message, 'bad'); }
    } })),
    h('p', { class: 'small muted', text: t('settings.file', { file: s.file }) }),
    h('button', { type: 'button', class: 'ghost small', text: t('w.open'), onclick: () => app.go('welcome') }));

  // ComfyUI: start it from its folder, and see what it lacks for the repaints
  const comfyOut = h('div', { class: 'small' });
  const comfyBox = h('div', { class: 'stack', style: { marginLeft: '24px' } },
    h('div', { class: 'row' },
      h('button', { type: 'button', class: 'small', disabled: !s.paths.comfy_dir, title: s.paths.comfy_dir ? '' : t('c.nodir'),
        text: t('c.start'), onclick: async () => {
          try {
            const r = await api('/api/comfy/start', {});
            comfyOut.textContent = r.already ? t('c.already') : t('c.starting');
          } catch (e) { comfyOut.textContent = e.message; }
        } }),
      h('button', { type: 'button', class: 'small', text: t('c.check'), onclick: async () => {
        comfyOut.textContent = t('b.working');
        const r = await api('/api/comfy/check', {});
        clear(comfyOut);
        if (r.running && !r.problems.length) comfyOut.append(h('span', { class: 'ok', text: t('c.ready') }));
        else comfyOut.append(h('ul', { class: 'bad' }, r.problems.map(x => h('li', { text: x }))));
        if (r.running !== st.requirements.comfy) { app.state = await api('/api/refresh', {}); }
      } })),
    comfyOut);
  const b = st.blender;
  const req = st.requirements;
  const line = (ok, title, detail) => h('div', { class: 'row' }, h('span', { class: 'pill ' + (ok ? 'ok' : 'bad'), text: ok ? t('found') : t('missing') }),
    h('strong', { text: title }), h('span', { class: 'muted small grow', text: detail || '' }));
  engines.append(h('h2', { text: t('settings.engines') }),
    line(true, t('eng.python'), t('eng.python.detail')),
    line(b.available, 'Blender', b.mode === 'module' ? t('eng.bpy') : b.detail),
    line(req.comfy, 'ComfyUI', s.paths.comfy_url),
    comfyBox,
    line(req.granny, t('eng.granny'), s.paths.granny || ''),
    line(req.game, t('set.game'), s.paths.game || ''),
    line(req.test_copy, t('set.test_copy'), s.paths.test_copy || ''),
    line(req.profile, t('eng.profile'), ''),
    h('p', { class: 'small muted', text: t('settings.engines.help') }),
    h('div', { class: 'row' },
      h('button', { type: 'button', text: t('settings.refresh'), onclick: async () => { app.state = await api('/api/refresh', {}); settingsScreen(main, app); } }),
      h('button', { type: 'button', text: t('log.show'), onclick: async () => {
        const r = await api('/api/log');
        const body = h('div', { class: 'stack' }, h('p', { class: 'small muted mono', text: r.path || '' }),
          h('pre', { class: 'log', style: { height: '60vh', width: 'min(900px, 86vw)' }, text: r.text || t('log.empty') }),
          r.path ? h('button', { type: 'button', text: t('open.folder'), onclick: () => api('/api/open', { path: r.path }) }) : null);
        dialog(t('log.title'), body);
      } })),
    h('p', { class: 'small muted', text: t('log.help') }));
}
