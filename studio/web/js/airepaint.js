// SPDX-License-Identifier: GPL-3.0-or-later
// The AI repaint of a building, region by region: choose the regions (each with the material the
// local ComfyUI is asked for), start, watch the texture change on the model one region at a time,
// stop when you like; then the export uses exactly that texture.
import { api, clear, fmt, h, storeGet, storeSet, t, toast } from './core.js';

// ctx: params() -> the building's parameters; show(url) -> put a texture on the model;
// use(path, key) -> the export takes this texture; restore() -> back to the painted texture
export function aiCard(app, ctx) {
  const o = storeGet('ai', { strength: 0.45, seed: 1, blend: 1, prompt: '', guard: true });
  const card = h('details', { class: 'card stack' });
  const body = h('div', { class: 'stack' });
  card.append(h('summary', {}, h('strong', { text: t('a.title') })), body);
  let regions = null, chosen = new Set(), session = null, polling = null, key = null;
  card.addEventListener('toggle', () => { if (card.open) draw(); });

  async function draw() {
    clear(body);
    if (!app.state.requirements.comfy) {
      body.append(h('p', { class: 'small notice', text: t('a.nocomfy') }),
        h('button', { type: 'button', class: 'small', text: t('settings.refresh'), onclick: async () => {
          app.state = await api('/api/refresh', {}); draw(); } }));
      return;
    }
    body.append(h('p', { class: 'small muted', text: t('a.intro') }));
    try { regions = await api('/api/ai/regions', { params: ctx.params() }); } catch (e) { body.append(h('p', { class: 'bad small', text: e.message })); return; }
    key = JSON.stringify(ctx.params());
    const usable = regions.regions.filter(r => r.material && !r.small).map(r => r.name);
    if (!chosen.size || [...chosen].some(n => !usable.includes(n))) chosen = new Set(usable);
    const list = h('div', { class: 'regionlist' });
    const drawList = () => {
      clear(list);
      for (const r of regions.regions) {
        const off = !r.material || r.small;
        list.append(h('label', { class: 'row small' + (off ? ' muted' : ''), title: r.material || t('a.noprompt') },
          h('input', { type: 'checkbox', disabled: off, checked: chosen.has(r.name),
            onchange: e => { e.target.checked ? chosen.add(r.name) : chosen.delete(r.name); } }),
          h('span', { class: 'mono', text: r.name }),
          h('span', { class: 'grow muted', text: off ? (r.small ? t('a.small') : t('a.noprompt')) : r.material })));
      }
    };
    drawList();
    const pick = names => { chosen = new Set((names || usable).filter(n => usable.includes(n))); drawList(); };
    const num = (k, min, max, step) => h('input', { type: 'number', min, max, step, value: o[k], style: { width: '68px' },
      onchange: e => { o[k] = Number(e.target.value); storeSet('ai', o); } });
    const status = h('div', { class: 'stack' });
    body.append(
      h('div', { class: 'row' }, h('button', { type: 'button', class: 'small', text: t('a.all'), onclick: () => pick() }),
        h('button', { type: 'button', class: 'small', text: t('a.walls'), onclick: () => pick(regions.walls) }),
        h('button', { type: 'button', class: 'small', text: t('a.roofs'), onclick: () => pick(regions.roofs) }),
        h('button', { type: 'button', class: 'small', text: t('a.none'), onclick: () => pick([]) })),
      list,
      h('div', { class: 'row small' }, t('r.k.strength'), num('strength', 0.05, 0.95, 0.05), t('r.k.seed'), num('seed', 0, 999999, 1),
        t('a.blend'), num('blend', 0, 1, 0.1)),
      h('div', { class: 'field' }, h('label', { class: 'small', text: t('a.prompt') }), h('div', { class: 'ctl' },
        h('input', { type: 'text', value: o.prompt, placeholder: t('a.prompt.ph'), onchange: e => { o.prompt = e.target.value; storeSet('ai', o); } }))),
      h('label', { class: 'row small', title: t('a.guard.help') }, h('input', { type: 'checkbox', checked: o.guard,
        onchange: e => { o.guard = e.target.checked; storeSet('ai', o); } }), t('a.guard')),
      h('div', { class: 'row' }, h('button', { type: 'button', class: 'primary', text: t('a.start'), onclick: () => start(status) })),
      status);
  }

  async function start(status) {
    if (!chosen.size) { toast(t('a.choose'), 'bad'); return; }
    clear(status);
    key = JSON.stringify(ctx.params());
    try {
      const r = await api('/api/ai/start', { params: ctx.params(), regions: [...chosen], strength: o.strength, seed: o.seed,
        blend: o.blend, prompt: o.prompt, guard: o.guard });
      session = r.session;
    } catch (e) { status.append(h('p', { class: 'bad small', text: e.message })); return; }
    const bar = h('i', { style: { width: '0%' } });
    const line = h('p', { class: 'small', text: t('a.starting') });
    const stop = h('button', { type: 'button', class: 'danger small', text: t('a.stop'), onclick: () => api('/api/ai/cancel', { session }) });
    const after = h('div', { class: 'row' });
    status.append(h('div', { class: 'progress' }, bar), line, h('div', { class: 'row' }, stop), after);
    let since = -1;
    clearInterval(polling);
    polling = setInterval(async () => {
      if (!card.isConnected) { clearInterval(polling); return; }
      let s;
      try { s = await api('/api/ai/state', { session, since }); } catch (e) { line.textContent = e.message; clearInterval(polling); return; }
      if (s.image) { ctx.show(s.image); since = s.version; }
      const p = s.progress;
      bar.style.width = (s.status === 'done' ? 100 : (p.of ? 100 * p.done / p.of : 0)) + '%';
      line.textContent = s.status === 'running'
        ? t('a.running', { i: p.done + 1, n: p.of, name: p.region || '…', s: fmt(s.seconds, 0) })
        : s.status === 'done' ? t('a.done', { s: fmt(s.seconds, 0) }) : `${t('status.' + s.status)}: ${s.error || ''}`;
      if (s.status === 'running') return;
      clearInterval(polling);
      stop.hidden = true;
      if (s.report) {
        const skipped = s.report.filter(r => r.skipped);
        if (skipped.length) status.append(h('ul', { class: 'small muted' }, skipped.map(r => h('li', { text: `${r.region}: ${r.skipped}` }))));
      }
      if (s.version > 0) {
        after.append(
          h('button', { type: 'button', class: 'primary small', text: t('a.use'), onclick: async () => {
            try { const r = await api('/api/ai/save', { session }); ctx.use(r.path, key); toast(t('a.used'), 'ok'); }
            catch (e) { toast(e.message, 'bad'); } } }),
          h('button', { type: 'button', class: 'small', text: t('a.back'), onclick: () => ctx.restore() }));
      }
    }, 1000);
  }

  return card;
}
