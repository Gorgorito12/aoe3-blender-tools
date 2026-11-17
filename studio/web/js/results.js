// SPDX-License-Identifier: GPL-3.0-or-later
// A survey's results as a table: its groups with their quartiles drawn as bars, its shares, its
// palettes; sorted by any column, filtered by a word. Opened from a finished survey, from a file,
// or on the profiles this program is calibrated on.
import { api, clear, fmt, h, language, pick, storeGet, storeSet, t, toast } from './core.js';

export async function resultsScreen(main, app) {
  clear(main);
  const filter = h('input', { type: 'search', class: 'grow', placeholder: t('rs.filter') });
  const facts = h('p', { class: 'small muted' });
  const help = h('p', { class: 'small muted' });
  const box = h('div', { class: 'results-box' });
  main.append(h('div', { class: 'head' }, h('div', {},
    h('button', { type: 'button', class: 'ghost small', text: '← ' + t('nav.survey'), onclick: () => app.go('survey') }),
    h('h1', { text: t('rs.title') }), h('p', { class: 'muted', text: t('rs.intro') }))),
    h('div', { class: 'card stack' },
      h('div', { class: 'row' },
        h('button', { type: 'button', class: 'primary', text: t('rs.open'), onclick: () => openFile() }),
        h('button', { type: 'button', text: t('rs.profile.textures'), onclick: () => load({ profile: 'textures' }) }),
        h('button', { type: 'button', text: t('rs.profile.models'), onclick: () => load({ profile: 'models' }) })),
      h('div', { class: 'row' }, filter), facts, help),
    box);

  let data = null, sortKey = null, sortUp = false;
  filter.addEventListener('input', () => draw());

  async function openFile() {
    const p = await pick('file', { title: t('rs.open'), filters: [['JSON', '*.json']] });
    if (p) load({ path: p });
  }

  async function load(body) {
    clear(box).append(h('p', { class: 'small muted', text: t('b.working') }));
    try {
      data = await api('/api/results', body);
      storeSet('results.last', body);
      sortKey = null;
      const f = data.facts;
      facts.textContent = [data.path,
        f.textures != null ? t('rs.textures', { n: fmt(f.textures), d: fmt(f.distinct) }) : t('rs.files', { n: fmt(f.files), d: fmt(f.distinct) }),
        t('rs.groups', { n: data.rows.length }),
        Object.keys(f.unread || {}).length ? t('rs.unread', { n: fmt(Object.values(f.unread).reduce((a, b) => a + b, 0)) }) : ''].filter(Boolean).join(' · ');
      help.textContent = data.help[language()] || data.help.en;
      draw();
    } catch (e) {
      clear(box);
      toast(e.message, 'bad');
    }
  }

  // each quartile column on its own scale (logarithmic when it spans a lot), so bars compare
  function scales() {
    const out = {};
    for (const c of data.columns.filter(c => c.kind === 'q')) {
      const vals = data.rows.flatMap(r => r[c.key] ? [r[c.key][0], r[c.key][2]] : []);
      if (!vals.length) continue;
      const lo = Math.min(...vals), hi = Math.max(...vals);
      const log = lo > 0 && hi / lo > 50;
      const f = log ? v => Math.log(Math.max(v, lo)) : v => v;
      out[c.key] = v => (hi === lo ? 0.5 : (f(v) - f(lo)) / (f(hi) - f(lo)));
    }
    return out;
  }

  function sortValue(r, c) {
    const v = r[c.key];
    if (v == null) return -Infinity;
    if (c.kind === 'q') return v[1];
    if (c.kind === 'top' || c.kind === 'palette') return v.length ? (c.kind === 'top' ? v[0][1] : v[0][3]) : 0;
    return v;
  }

  function draw() {
    if (!data) return;
    const scale = scales();
    const word = filter.value.trim().toLowerCase();
    let rows = data.rows.filter(r => !word || data.columns.some(c => c.kind === 'text' && String(r[c.key] ?? '').toLowerCase().includes(word)));
    if (sortKey) {
      const c = data.columns.find(x => x.key === sortKey);
      rows = [...rows].sort((a, b) => {
        const x = sortValue(a, c), y = sortValue(b, c);
        return (x < y ? -1 : x > y ? 1 : 0) * (sortUp ? 1 : -1);
      });
    }
    const head = h('tr', {}, data.columns.map(c => h('th', {
      class: 'sortable', title: t('rs.sort'), 'aria-sort': sortKey === c.key ? (sortUp ? 'ascending' : 'descending') : null,
      onclick: () => { if (sortKey === c.key) sortUp = !sortUp; else { sortKey = c.key; sortUp = c.kind === 'text'; } draw(); },
    }, (c.label[language()] || c.label.en) + (sortKey === c.key ? (sortUp ? ' ▲' : ' ▼') : ''))));
    const body = rows.map(r => h('tr', {}, data.columns.map(c => h('td', {}, cell(c, r[c.key], scale[c.key])))));
    clear(box).append(h('table', { class: 'results' }, h('thead', {}, head), h('tbody', {}, body)));
    if (!rows.length) box.append(h('p', { class: 'small muted', text: t('rs.none') }));
  }

  function num(v) {
    return Number.isInteger(v) || Math.abs(v) >= 100 ? fmt(v) : Math.abs(v) >= 10 ? fmt(v, 1) : fmt(v, 2);
  }

  function cell(c, v, at) {
    if (v == null) return h('span', { class: 'muted', text: '–' });
    if (c.kind === 'text') return v;
    if (c.kind === 'int') return fmt(v);
    if (c.kind === 'share') {
      return h('div', { class: 'share', title: fmt(v * 100, 1) + ' %' },
        h('span', { class: 'bar', style: { width: Math.round(v * 100) + '%' } }), h('span', { text: fmt(v * 100, 0) + ' %' }));
    }
    if (c.kind === 'q') {
      const [a, m, b] = v;
      const x0 = at(a) * 100, x1 = at(b) * 100, xm = at(m) * 100;
      return h('div', { class: 'quart', title: `${num(a)} · ${num(m)} · ${num(b)}` },
        h('div', { class: 'track' },
          h('span', { class: 'band', style: { left: x0 + '%', width: Math.max(1, x1 - x0) + '%' } }),
          h('span', { class: 'median', style: { left: xm + '%' } })),
        h('span', { class: 'small', text: num(m) }));
    }
    if (c.kind === 'palette') {
      return h('div', { class: 'swatches' }, v.slice(0, 6).map(([r, g, b, s]) =>
        h('span', { title: `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)}) · ${fmt(s * 100, 0)} %`,
          style: { background: `rgb(${r},${g},${b})`, flexGrow: String(Math.max(0.05, s)) } })));
    }
    if (c.kind === 'top') {
      return h('span', { class: 'small nowrap', title: v.map(([k, n]) => `${k} (${fmt(n)})`).join(', '),
        text: v.slice(0, 2).map(([k, n]) => `${k} ${fmt(n)}`).join(' · ') + (v.length > 2 ? ' …' : '') });
    }
    return String(v);
  }

  const asked = storeGet('results.open', null);
  if (asked) { storeSet('results.open', null); load(asked); }
}
