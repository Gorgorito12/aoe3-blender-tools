// SPDX-License-Identifier: GPL-3.0-or-later
// The first start: what works with nothing set, and the folders that open the rest, each checked
// as it is typed or chosen.
import { api, clear, debounce, h, pick, storeSet, t, toast } from './core.js';

// the settings the welcome asks for, most needed first
const STEPS = [['game', true], ['test_copy', false], ['mod', false], ['comfy_dir', false]];

export async function welcomeScreen(main, app) {
  clear(main);
  const st = app.state;
  const paths = { ...st.settings.paths };
  const ready = [
    ['w.ready.buildings', true], ['w.ready.textures', true], ['w.ready.inspect', true],
    ['w.ready.exports', st.blender.available], ['w.ready.ai', st.requirements.comfy],
  ];
  const steps = h('div', { class: 'stack' });
  main.append(h('div', { class: 'welcome stack' },
    h('h1', { text: t('w.title') }), h('p', { class: 'muted', text: t('w.intro') }),
    h('div', { class: 'card stack' }, h('h2', { text: t('w.now') }),
      h('ul', { class: 'checks' }, ready.map(([k, ok]) => h('li', { class: ok ? 'ok' : 'warn' },
        h('span', { 'aria-hidden': 'true', text: ok ? '✔ ' : '○ ' }), t(k + (ok ? '' : '.no')))))),
    h('div', { class: 'card stack' }, h('h2', { text: t('w.folders') }), h('p', { class: 'small muted', text: t('w.folders.help') }), steps),
    h('div', { class: 'row' },
      h('button', { type: 'button', class: 'primary', text: t('w.save'), onclick: () => save(true) }),
      h('button', { type: 'button', class: 'ghost', text: t('w.later'), onclick: () => { storeSet('welcomed', true); app.go('buildings'); } }))));

  const valid = {};
  for (const [key, needed] of STEPS) {
    const status = h('ul', { class: 'checks small' });
    const input = h('input', { type: 'text', class: 'grow', value: paths[key] || '', placeholder: t('set.' + key + '.help'),
      oninput: () => { paths[key] = input.value.trim(); later(); } });
    const check = async () => {
      clear(status);
      if (!input.value.trim()) { valid[key] = !needed; return; }
      try {
        const r = await api('/api/check-path', { key, path: input.value.trim() });
        valid[key] = r.ok;
        for (const [level, code] of r.notes) {
          status.append(h('li', { class: level === 'info' ? 'muted' : level },
            h('span', { 'aria-hidden': 'true', text: { ok: '✔ ', bad: '✖ ', info: '• ' }[level] || '' }), t('w.n.' + code, null, code)));
        }
      } catch (e) { status.append(h('li', { class: 'bad', text: e.message })); }
    };
    const later = debounce(check, 350);
    steps.append(h('div', { class: 'stack' },
      h('div', { class: 'row' }, h('strong', { text: t('set.' + key) }),
        h('span', { class: 'pill' + (needed ? ' warn' : ''), text: needed ? t('w.recommended') : t('w.optional') })),
      h('p', { class: 'small muted', text: t('w.why.' + key) }),
      h('div', { class: 'row' }, input, h('button', { type: 'button', text: t('browse'), onclick: async () => {
        const p = await pick('folder', { title: t('set.' + key), initial: input.value }).catch(e => toast(e.message, 'bad'));
        if (p) { input.value = p; paths[key] = p; check(); }
      } })), status));
    check();
  }

  async function save(go) {
    const changes = {};
    for (const [key] of STEPS) if (paths[key] !== st.settings.paths[key] && (valid[key] || !paths[key])) changes[key] = paths[key] || '';
    const bad = STEPS.filter(([key]) => paths[key] && !valid[key]).map(([key]) => t('set.' + key));
    try {
      if (Object.keys(changes).length) app.state = await api('/api/settings', { paths: changes });
      if (bad.length) { toast(t('w.notsaved', { list: bad.join(', ') }), 'bad'); return; }
      storeSet('welcomed', true);
      toast(t('settings.saved'), 'ok');
      if (go) app.go('buildings');
    } catch (e) { toast(e.message, 'bad'); }
  }
}
