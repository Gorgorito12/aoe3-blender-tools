// SPDX-License-Identifier: GPL-3.0-or-later
// Look inside a game file: a texture with its header, a model in 3D with its bones, a compiled
// XML as text, an archive as a searchable list whose files open the same way. Read only.
import { api, clear, fmt, h, pick, storeGet, storeSet, t, toast } from './core.js';
import { Viewer } from './viewer.js';

export async function inspectScreen(main, app) {
  clear(main);
  const path = h('input', { type: 'text', class: 'grow', value: storeGet('inspect.path', ''), placeholder: t('i.path'),
    onkeydown: e => { if (e.key === 'Enter') open(); } });
  const result = h('div', { class: 'stack' });
  main.append(h('div', { class: 'head' }, h('div', {},
    h('button', { type: 'button', class: 'ghost small', text: '← ' + t('nav.survey'), onclick: () => app.go('survey') }),
    h('h1', { text: t('i.title') }), h('p', { class: 'muted', text: t('i.intro') }))),
    h('div', { class: 'card row' }, path,
      h('button', { type: 'button', text: t('browse'), onclick: async () => {
        const p = await pick('file', { title: t('i.title'), initial: path.value,
          filters: [['Game files', '*.ddt *.gr2 *.xmb *.bar *.xml *.particle *.tactics']] }).catch(e => toast(e.message, 'bad'));
        if (p) { path.value = p; open(); }
      } }),
      h('button', { type: 'button', class: 'primary', text: t('i.open'), onclick: () => open() })),
    result);

  let viewer = null;
  app.onLeave(() => viewer?.dispose());

  async function open(entry) {
    storeSet('inspect.path', path.value);
    clear(result).append(h('p', { class: 'muted', text: t('b.working') }));
    let r;
    try { r = await api('/api/inspect', { path: path.value.trim(), entry: entry || null }); }
    catch (e) { clear(result).append(h('div', { class: 'notice bad', text: e.message })); return; }
    viewer?.dispose(); viewer = null;
    clear(result);
    const back = entry ? h('button', { type: 'button', class: 'ghost small', text: '← ' + t('i.archive'), onclick: () => open() }) : null;
    result.append(h('div', { class: 'row' }, back, h('h2', { text: r.name })));
    if (r.kind === 'bar') showBar(r);
    else if (r.kind === 'ddt') showDdt(r);
    else if (r.kind === 'gr2') showGr2(r);
    else if (r.kind === 'text') result.append(h('p', { class: 'small muted', text: r.format.toUpperCase() }),
      h('pre', { class: 'log', style: { height: '70vh' }, text: r.text }));
    else result.append(h('p', { class: 'muted', text: t('i.binary', { n: fmt(r.size) }) }), h('pre', { class: 'log mono', text: r.head }));
  }

  function showBar(r) {
    const filter = h('input', { type: 'text', placeholder: t('i.filter'), oninput: () => draw() });
    const table = h('table', { class: 'jobs-table' });
    result.append(h('div', { class: 'row' }, filter, h('span', { class: 'muted small', text: t('i.entries', { n: fmt(r.entries.length) }) })),
      h('div', { class: 'card', style: { maxHeight: '65vh', overflow: 'auto' } }, table));
    const draw = () => {
      clear(table);
      const q = filter.value.toLowerCase().replaceAll('/', '\\');
      const rows = r.entries.filter(([n]) => !q || n.toLowerCase().includes(q)).slice(0, 500);
      for (const [name, size] of rows) {
        table.append(h('tr', {}, h('td', { class: 'mono small', text: name }), h('td', { class: 'small', text: fmt(size) }),
          h('td', {}, h('button', { type: 'button', class: 'small', text: t('i.look'), onclick: () => open(name) }))));
      }
      if (rows.length === 500) table.append(h('tr', {}, h('td', { colspan: 3, class: 'muted small', text: t('i.more') })));
    };
    draw();
  }

  function showDdt(r) {
    result.append(h('p', { class: 'mono small', text: r.header }));
    if (r.error) { result.append(h('div', { class: 'notice bad', text: r.error })); return; }
    const imgs = h('div', { class: 'row', style: { alignItems: 'flex-start' } },
      h('figure', { style: { margin: 0 } }, h('img', { src: r.image, alt: r.name, class: 'checker', style: { maxWidth: '640px', width: '100%' } }),
        h('figcaption', { class: 'small muted', text: t('i.colour') })),
      r.alpha ? h('figure', { style: { margin: 0 } }, h('img', { src: r.alpha, alt: 'alpha', style: { maxWidth: '640px', width: '100%' } }),
        h('figcaption', { class: 'small muted', text: t('i.alpha', { p: fmt(r.alpha_partial * 100, 1), z: fmt(r.alpha_zero * 100, 1) }) })) : null);
    result.append(imgs);
  }

  function showGr2(r) {
    if (r.error) { result.append(h('div', { class: 'notice bad', text: r.error })); return; }
    const view = h('div', { class: 'viewport', style: { height: '62vh' } });
    const info = h('dl', { class: 'kv' },
      h('dt', { text: t('b.tris') }), h('dd', { text: fmt(r.triangles) }),
      h('dt', { text: t('b.verts') }), h('dd', { text: fmt(r.vertices) }),
      h('dt', { text: t('i.bones') }), h('dd', { text: fmt(r.bones) }),
      h('dt', { text: t('b.size') }), h('dd', { text: r.size.map(v => fmt(v, 2)).join(' × ') + ' m' }));
    const side = h('div', { class: 'card stack' }, info,
      h('h3', { text: t('i.meshes') }), h('ul', { class: 'small' }, r.meshes.map(m => h('li', { text: `${m.name}: ${fmt(m.triangles)} ${t('b.tris.short')}` }))),
      h('h3', { text: t('i.textures') }), h('ul', { class: 'small mono' }, (r.textures || []).map(x => h('li', { text: x || '—' }))),
      r.texture_name ? h('p', { class: 'small ok', text: t('i.texture.found', { name: r.texture_name }) }) : h('p', { class: 'small muted', text: t('i.texture.none') }));
    result.append(h('div', { class: 'tool' }, view, side));
    viewer = new Viewer(view);
    viewer.show.attach = true;
    viewer.setModel({ mesh: r.mesh, attach: r.attach, boxes: [] }, r.texture || null, true);
    if (!r.texture) viewer.setMode('clay');
  }

  if (path.value) open();
}
