// SPDX-License-Identifier: GPL-3.0-or-later
// The settlement composer: units laid round a socket as the mod's own settlements are (distances,
// counts and a free lane, measured), seen from above, moved and turned by hand, then written as a
// grouping file and deployed with the grouping form. Which way the game's x and z run on screen is
// still to verify in game: the screen says so.
import { api, clear, h, pick, storeGet, storeSet, t, toast } from './core.js';

const CLASSES = ['building', 'prop', 'plant', 'nature'];
const COLOURS = { socket: '#e0b040', building: '#d07050', prop: '#8090c0', plant: '#70b060', nature: '#3f8f50',
  obstruction: '#888', unit: '#b080c0' };
const STEP = Math.PI / 12;                  // a turn of 15 degrees

export async function settlementScreen(main, app) {
  clear(main);
  const saved = storeGet('settlement', { socket: 'SocketTradeRoute', obstruction: '', seed: 1, name: 'MySettlement',
    rows: [{ class: 'building', proto: '', variations: 1, radius: 3 }], counts: {} });
  let units = [], meta = null, selected = -1, measured = null, lastPath = '';

  const socket = h('input', { type: 'text', value: saved.socket, placeholder: 'SocketTradeRoute' });
  const obstruction = h('input', { type: 'text', value: saved.obstruction, placeholder: t('se.obstruction.none') });
  const seed = h('input', { type: 'number', min: 1, max: 99999, value: saved.seed, style: { width: '90px' } });
  const rowsBox = h('div', { class: 'stack' });
  const countsBox = h('div', { class: 'row small' });
  const plan = h('div', { class: 'viewport settlement-plan' });
  const canvas = h('canvas', { tabindex: 0, 'aria-label': t('se.plan') });
  plan.append(canvas);
  const info = h('div', { class: 'small muted' });
  const fields = h('div', { class: 'stack' });
  const name = h('input', { type: 'text', value: saved.name, class: 'grow' });
  const savedBox = h('div', { class: 'stack small' });

  main.append(h('div', { class: 'head' }, h('div', {},
    h('button', { type: 'button', class: 'ghost small', text: '← ' + t('nav.buildings'), onclick: () => app.go('buildtools') }),
    h('h1', { text: t('se.title') }), h('p', { class: 'muted', text: t('se.intro') }))),
    h('div', { class: 'notice warn small', text: t('se.verify') }),
    h('div', { class: 'settlement' },
      h('div', { class: 'stack' },
        h('div', { class: 'card stack' },
          h('strong', { text: t('se.units') }), h('p', { class: 'small muted', text: t('se.units.help') }), rowsBox,
          h('button', { type: 'button', class: 'small', text: '+ ' + t('se.add'), onclick: () => { saved.rows.push({ class: 'prop', proto: '', variations: 1, radius: 1 }); drawRows(); } }),
          h('div', { class: 'row small' }, t('se.socket'), socket),
          h('div', { class: 'row small' }, t('se.obstruction'), obstruction),
          h('div', {}, h('div', { class: 'small', text: t('se.counts') }), countsBox),
          h('div', { class: 'row' },
            h('button', { type: 'button', class: 'primary', text: t('se.compose'), onclick: () => compose() }),
            h('button', { type: 'button', text: t('se.another'), onclick: () => { seed.value = Number(seed.value || 1) + 1; compose(); } }),
            h('span', { class: 'small' }, t('se.seed'), ' ', seed))),
        h('div', { class: 'card stack' },
          h('div', { class: 'row' }, h('strong', { class: 'grow', text: t('se.file') }),
            h('button', { type: 'button', text: t('se.open'), onclick: () => openFile() })),
          h('div', { class: 'row small' }, t('se.name'), name, '.xml'),
          h('div', { class: 'row' },
            h('button', { type: 'button', class: 'primary', text: t('se.save'), onclick: () => save() }),
            h('button', { type: 'button', text: t('se.deploy'), title: t('se.deploy.help'), onclick: () => deploy() })),
          savedBox)),
      h('div', { class: 'stack' }, plan, info, h('div', { class: 'card' }, fields))));

  try { measured = await api('/api/settlement/measured', {}); } catch (e) { toast(e.message, 'bad'); }
  drawRows();
  drawCounts();

  function keep() {
    storeSet('settlement', { ...saved, socket: socket.value, obstruction: obstruction.value, seed: Number(seed.value || 1), name: name.value });
  }

  function drawRows() {
    clear(rowsBox);
    saved.rows.forEach((r, i) => {
      const cls = h('select', { onchange: e => { r.class = e.target.value; keep(); } },
        CLASSES.map(c => h('option', { value: c, selected: c === r.class, text: t('se.class.' + c) })));
      const proto = h('input', { type: 'text', class: 'grow', value: r.proto, placeholder: t('se.proto'), oninput: e => { r.proto = e.target.value; keep(); } });
      const vars = h('input', { type: 'number', min: 1, max: 50, value: r.variations, title: t('se.variations'), style: { width: '60px' },
        oninput: e => { r.variations = Number(e.target.value); keep(); } });
      const rad = h('input', { type: 'number', min: 0.1, max: 30, step: 0.1, value: r.radius, title: t('se.radius'), style: { width: '70px' },
        oninput: e => { r.radius = Number(e.target.value); keep(); } });
      rowsBox.append(h('div', { class: 'row small' }, cls, proto, vars, rad,
        h('button', { type: 'button', class: 'ghost small', text: '×', title: t('se.remove'), onclick: () => { saved.rows.splice(i, 1); keep(); drawRows(); } })));
    });
    rowsBox.append(h('div', { class: 'row small muted' }, h('span', { class: 'grow', text: t('se.proto') }),
      h('span', { text: t('se.variations') }), h('span', { text: t('se.radius') })));
  }

  function drawCounts() {
    clear(countsBox);
    for (const c of CLASSES) {
      const median = measured?.counts?.[c] ?? '';
      countsBox.append(h('label', {}, t('se.class.' + c) + ' ',
        h('input', { type: 'number', min: 0, max: 60, value: saved.counts[c] ?? '', placeholder: String(median), style: { width: '64px' },
          oninput: e => { saved.counts[c] = e.target.value; keep(); } })));
    }
  }

  async function compose() {
    keep();
    try {
      const r = await api('/api/settlement/compose', { units: saved.rows, socket: socket.value, obstruction: obstruction.value,
        seed: Number(seed.value || 1), counts: saved.counts });
      units = r.units; meta = null; selected = -1;
      draw(); drawFields();
    } catch (e) { toast(e.message, 'bad'); }
  }

  async function openFile() {
    const p = await pick('file', { title: t('se.open'), filters: [['Grouping', '*.xml']] });
    if (!p) return;
    try {
      const r = await api('/api/settlement/open', { path: p });
      units = r.units; meta = r.meta; selected = -1; lastPath = r.path;
      name.value = p.split(/[\\/]/).pop().replace(/\.xml$/i, '');
      draw(); drawFields();
      toast(t('se.opened', { n: units.length }));
    } catch (e) { toast(e.message, 'bad'); }
  }

  async function save() {
    keep();
    if (!units.length) { toast(t('se.empty'), 'bad'); return; }
    try {
      const r = await api('/api/settlement/save', { name: name.value, units, meta });
      lastPath = r.path;
      clear(savedBox).append(h('div', { class: 'row' }, h('span', { class: 'mono grow', text: r.path }),
        h('button', { type: 'button', class: 'small', text: t('open.folder'), onclick: () => api('/api/open', { path: r.path }).catch(e => toast(e.message, 'bad')) })));
      toast(t('se.saved'));
    } catch (e) { toast(e.message, 'bad'); }
  }

  function deploy() {
    if (!lastPath) { toast(t('se.save.first'), 'bad'); return; }
    storeSet('tool.deploy_grouping', { install: app.state.settings.paths.test_copy || '', grouping: [lastPath] });
    app.go('tool/deploy_grouping');
  }

  // ---- the plan, seen from above: game x to the right, game z up (to verify in game)
  const ctx = canvas.getContext('2d');
  let scale = 10, cx = 0, cy = 0, drag = null;
  const toScreen = (x, z) => [cx + x * scale, cy - z * scale];
  const toGame = (px, py) => [(px - cx) / scale, (cy - py) / scale];

  function fit() {
    const w = plan.clientWidth, hgt = plan.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(hgt * dpr);
    canvas.style.width = w + 'px'; canvas.style.height = hgt + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const reach = Math.max(25, ...units.map(u => Math.hypot(u.x, u.z) + (u.r || 1)));
    scale = Math.min(w, hgt) / (2 * reach * 1.08);
    cx = w / 2; cy = hgt / 2;
  }

  function draw() {
    fit();
    const w = plan.clientWidth, hgt = plan.clientHeight;
    ctx.clearRect(0, 0, w, hgt);
    const sock = units.find(u => u.class === 'socket');
    if (measured && sock && !meta) {
      // the clear ground and the free lane the composer kept
      ctx.strokeStyle = 'rgba(255,255,255,.25)'; ctx.setLineDash([4, 4]);
      ctx.beginPath(); ctx.arc(cx, cy, measured.clear * scale, 0, 2 * Math.PI); ctx.stroke();
      ctx.setLineDash([]);
      const a = sock.turn, half = measured.lane / 2, far = 2 * Math.max(w, hgt) / scale;
      const along = [Math.sin(a), Math.cos(a)], across = [Math.cos(a), -Math.sin(a)];
      const corner = (s, d) => toScreen(across[0] * s * half + along[0] * d, across[1] * s * half + along[1] * d);
      ctx.fillStyle = 'rgba(224,176,64,.10)';
      ctx.beginPath();
      for (const [s, d] of [[-1, 0], [1, 0], [1, far], [-1, far]]) ctx.lineTo(...corner(s, d));
      ctx.fill();
    }
    units.forEach((u, i) => {
      const [x, y] = toScreen(u.x, u.z);
      const r = Math.max(3, (u.r || 1) * scale);
      ctx.fillStyle = COLOURS[u.class] || COLOURS.unit;
      ctx.globalAlpha = u.class === 'obstruction' ? 0.35 : 0.8;
      ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fill();
      ctx.globalAlpha = 1;
      ctx.strokeStyle = i === selected ? '#fff' : 'rgba(0,0,0,.5)'; ctx.lineWidth = i === selected ? 2 : 1;
      ctx.stroke();
      // its facing: the turn's direction (orient = sin, cos)
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + Math.sin(u.turn) * r, y - Math.cos(u.turn) * r); ctx.stroke();
    });
    ctx.lineWidth = 1;
    const by = {};
    for (const u of units) by[u.class] = (by[u.class] || 0) + 1;
    info.textContent = units.length
      ? t('se.info', { n: units.length }) + ' · ' + Object.entries(by).map(([c, n]) => `${t('se.class.' + c, null, c)} ${n}`).join(', ')
      : t('se.none');
  }

  function hit(px, py) {
    let best = -1, bestD = Infinity;
    units.forEach((u, i) => {
      const [x, y] = toScreen(u.x, u.z);
      const d = Math.hypot(px - x, py - y);
      if (d <= Math.max(6, (u.r || 1) * scale) && d < bestD) { best = i; bestD = d; }
    });
    return best;
  }

  canvas.addEventListener('pointerdown', e => {
    const b = canvas.getBoundingClientRect();
    selected = hit(e.clientX - b.left, e.clientY - b.top);
    if (selected >= 0) { drag = { id: e.pointerId }; canvas.setPointerCapture(e.pointerId); }
    draw(); drawFields();
  });
  canvas.addEventListener('pointermove', e => {
    if (!drag || selected < 0) return;
    const b = canvas.getBoundingClientRect();
    const [x, z] = toGame(e.clientX - b.left, e.clientY - b.top);
    const u = units[selected];
    u.x = Math.round(x * 1e4) / 1e4; u.z = Math.round(z * 1e4) / 1e4;
    const keepScale = scale, keepX = cx, keepY = cy;
    draw(); scale = keepScale; cx = keepX; cy = keepY;      // the view stays while dragging
  });
  canvas.addEventListener('pointerup', () => { if (drag) { drag = null; draw(); drawFields(); } });
  canvas.addEventListener('wheel', e => {
    if (selected < 0) return;
    e.preventDefault();
    turn(e.deltaY > 0 ? STEP : -STEP);
  }, { passive: false });
  canvas.addEventListener('keydown', e => {
    if (selected < 0) return;
    if (e.key === 'q' || e.key === 'Q') turn(-STEP);
    else if (e.key === 'e' || e.key === 'E') turn(STEP);
    else if (e.key === 'Delete') { units.splice(selected, 1); selected = -1; draw(); drawFields(); }
  });
  const resizer = new ResizeObserver(() => draw());
  resizer.observe(plan);
  app.onLeave(() => resizer.disconnect());

  function turn(by) {
    const u = units[selected];
    u.turn = Math.round((((u.turn + by) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI) * 1e4) / 1e4;
    draw(); drawFields();
  }

  function drawFields() {
    clear(fields);
    if (selected < 0 || !units[selected]) {
      fields.append(h('p', { class: 'small muted', text: t('se.select') }));
      return;
    }
    const u = units[selected];
    const num = (key, value, set) => h('label', { class: 'small' }, t(key) + ' ',
      h('input', { type: 'number', step: 'any', value, style: { width: '90px' }, onchange: e => { set(Number(e.target.value)); draw(); } }));
    fields.append(
      h('div', { class: 'row small' }, t('se.proto'), h('input', { type: 'text', class: 'grow', value: u.proto, onchange: e => { u.proto = e.target.value; } })),
      h('div', { class: 'row' },
        num('se.variation', u.variation, v => { u.variation = Math.max(0, Math.round(v)); }),
        num('se.x', u.x, v => { u.x = v; }), num('se.z', u.z, v => { u.z = v; }),
        num('se.turn', Math.round(u.turn * 180 / Math.PI * 10) / 10, v => { u.turn = v * Math.PI / 180; })),
      h('div', { class: 'row' },
        h('button', { type: 'button', class: 'small', text: '⟲ 15°', onclick: () => turn(-STEP) }),
        h('button', { type: 'button', class: 'small', text: '⟳ 15°', onclick: () => turn(STEP) }),
        h('button', { type: 'button', class: 'small', text: t('se.remove'), onclick: () => { units.splice(selected, 1); selected = -1; draw(); drawFields(); } })),
      h('p', { class: 'small muted', text: t('se.keys') }));
  }
  drawFields();
  draw();
}
