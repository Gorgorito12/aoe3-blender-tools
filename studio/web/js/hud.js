// SPDX-License-Identifier: GPL-3.0-or-later
// The game interface screen: a game copy's in-game HUD (the main screen and its panels, normal or
// minimised) drawn as the game draws it, at a chosen screen size and culture; its gadgets as a
// tree; the one under the mouse or chosen in the tree outlined, with everything it says.
import { api, clear, confirmDialog, dialog, fetchBlob, h, pick, storeGet, storeSet, t, toast } from './core.js';
import { ASSUMED, HudRenderer, displayText, fontAt } from './hud_render.js';

const SIZES = ['1024x768', '1280x720', '1280x768', '1280x800', '1280x1024', '1366x768', '1600x900', '1680x1050', '1920x1080'];

export async function hudScreen(main, app) {
  clear(main);
  const saved = storeGet('hud', { variant: 'min', culture: 'Eur', size: '1280x720', showHidden: false, outlines: false });
  const moments = storeGet('hud.moments', {}), oneOf = storeGet('hud.oneOf', {});
  const momentsBox = h('details', { class: 'hud-moments small' }, h('summary', { text: t('h.moments') }));
  let scene = null, renderer = null, list = [], selected = null, hover = null, frame = null;
  const images = new Map(), faces = new Map(), ratios = new Map();
  // textures are fetched a few at a time: a scene names over a hundred
  const queue = []; let active = 0;
  function fetchSoon(url, done) { queue.push([url, done]); pump(); }
  function pump() {
    while (active < 6 && queue.length) {
      const [url, done] = queue.shift();
      active++;
      fetchBlob(url).then(b => (b ? createImageBitmap(b) : null)).catch(() => null)
        .then(img => { active--; done(img); pump(); });
    }
  }
  let view = { zoom: 1, x: 0, y: 0, fitted: false };

  const variant = h('select', { onchange: () => { keep(); open(); } },
    [['min', t('h.min')], ['normal', t('h.normal')]].map(([v, l]) => h('option', { value: v, selected: v === saved.variant, text: l })));
  const culture = h('select', { onchange: () => { keep(); redraw(); } },
    [['Eur', t('h.eur')], ['Nat', t('h.nat')], ['Asi', t('h.asi')]].map(([v, l]) => h('option', { value: v, selected: v === saved.culture, text: l })));
  const size = h('select', { onchange: () => { keep(); view.fitted = false; redraw(); } },
    SIZES.map(s => h('option', { value: s, selected: s === saved.size, text: s.replace('x', ' × ') })));
  const showHidden = h('input', { type: 'checkbox', checked: saved.showHidden, onchange: () => { keep(); redraw(); } });
  const outlines = h('input', { type: 'checkbox', checked: saved.outlines, onchange: () => { keep(); redraw(); } });
  const search = h('input', { type: 'search', class: 'grow', placeholder: t('h.search'), oninput: () => drawTree() });
  const tree = h('div', { class: 'hud-tree' });
  const stage = h('div', { class: 'viewport hud-stage' });
  const canvas = h('canvas', { tabindex: 0, 'aria-label': t('h.stage') });
  stage.append(canvas);
  const details = h('div', { class: 'hud-details stack' });
  const status = h('span', { class: 'small muted' });
  // editing: undo, redo, what changed, the check, save
  const undoBtn = h('button', { type: 'button', class: 'small', text: '↶ ' + t('h.undo'), title: 'Ctrl+Z', onclick: () => undo(false) });
  const redoBtn = h('button', { type: 'button', class: 'small', text: '↷ ' + t('h.redo'), title: 'Ctrl+Y', onclick: () => undo(true) });
  const changesBtn = h('button', { type: 'button', class: 'small', onclick: () => showChanges() });
  const grid = h('input', { type: 'checkbox', checked: storeGet('hud.grid', false), onchange: e => { storeSet('hud.grid', e.target.checked); paint(); } });
  const arrangeBox = h('details', { class: 'hud-moments small' }, h('summary', { text: t('h.arrange') }),
    h('div', { class: 'stack' }, h('p', { class: 'muted', text: t('h.arrangehelp') }),
      ...[['left', 'h.a.left'], ['right', 'h.a.right'], ['top', 'h.a.top'], ['bottom', 'h.a.bottom'], ['hcentre', 'h.a.hcentre'],
        ['vcentre', 'h.a.vcentre'], ['hspread', 'h.a.hspread'], ['vspread', 'h.a.vspread'], ['samew', 'h.a.samew'], ['sameh', 'h.a.sameh']]
        .map(([k, key]) => h('button', { type: 'button', class: 'small', text: t(key), onclick: () => arrange(k) }))));
  const editBar = h('div', { class: 'card row hud-bar' }, undoBtn, redoBtn, changesBtn, arrangeBox,
    h('label', { class: 'small row' }, grid, t('h.grid')),
    h('button', { type: 'button', class: 'small', text: t('h.staticons'), title: t('h.staticons.help'), onclick: () => app.go('tool/make_stat_icon') }),
    h('button', { type: 'button', class: 'small', text: t('h.check'), onclick: () => runCheck() }),
    h('button', { type: 'button', class: 'small primary', text: t('h.save'), onclick: () => save() }),
    h('label', { class: 'small row' }, h('input', { type: 'checkbox', checked: storeGet('hud.original', false),
      onchange: e => { storeSet('hud.original', e.target.checked); showOriginal = e.target.checked; redraw(); } }), t('h.original')),
    h('span', { class: 'small muted', text: t('h.edithelp') }));
  let showOriginal = storeGet('hud.original', false), originalRenderer = null;
  const notes = h('details', { class: 'small' }, h('summary', { text: t('h.assumed') }),
    h('ul', {}, Object.values(ASSUMED).map(s => h('li', { text: s }))));

  main.append(h('div', { class: 'head' }, h('div', {},
    h('button', { type: 'button', class: 'ghost small', text: '← ' + t('nav.art'), onclick: () => app.go('art') }),
    h('h1', { text: t('h.title') }), h('p', { class: 'muted', text: t('h.intro') }))),
    h('div', { class: 'card row hud-bar' },
      h('label', { class: 'small' }, t('h.variant') + ' ', variant),
      h('label', { class: 'small' }, t('h.culture') + ' ', culture),
      h('label', { class: 'small' }, t('h.size') + ' ', size),
      h('label', { class: 'small row' }, showHidden, t('h.hidden')),
      h('label', { class: 'small row' }, outlines, t('h.outlines')),
      momentsBox,
      h('button', { type: 'button', class: 'small', text: t('h.fit'), onclick: () => { view.fitted = false; paint(); } }),
      h('button', { type: 'button', class: 'small', text: t('h.snapshot'), onclick: () => snapshot() }),
      status),
    editBar,
    h('div', { class: 'hud-body' },
      h('div', { class: 'card stack hud-left' }, h('div', { class: 'row' }, search), tree),
      h('div', { class: 'stack' }, stage, notes),
      h('div', { class: 'card hud-right' }, details)));

  function keep() {
    storeSet('hud', { variant: variant.value, culture: culture.value, size: size.value, showHidden: showHidden.checked, outlines: outlines.checked });
  }
  function dims() { const [w, hh] = size.value.split('x').map(Number); return [w, hh]; }
  function opts() {
    return { variant: scene.variant, culture: culture.value, showHidden: showHidden.checked, backdrop: '#3a4a2a',
      moments: Object.fromEntries(scene.rules.moments.map(m => [m.id, moments[m.id] ?? m.on])),
      oneOf: Object.fromEntries(scene.rules.oneOf.map(o => [o.re, oneOf[o.re] || o.show])),
      // the unit's simulation: what the game writes into the gadgets it fills, and the live texts
      live: sim && !sim.error && (moments.selected ?? true) ? sim.gadgets : null,
      liveTexts: sim && !sim.error ? sim.live : {} };
  }

  // ---- assets: textures as bitmaps, the copy's typefaces as fonts of the page
  const assets = {
    image(path) {
      const key = path.toLowerCase();
      if (!images.has(key)) {
        images.set(key, undefined);
        fetchSoon(`/api/hud/texture?s=${scene.session}&path=${encodeURIComponent(path)}`,
          img => { images.set(key, img); redrawSoon(); });
      }
      return images.get(key);
    },
    face(face) { return faces.get((face || '').toLowerCase()) || face; },
    // [ascent, descent] of a typeface per pixel of em, from the font itself
    metrics(family) {
      if (!ratios.has(family)) {
        const c = document.createElement('canvas').getContext('2d');
        c.font = `100px "${family}", Arial`;
        const m = c.measureText('Hg');
        ratios.set(family, [(m.fontBoundingBoxAscent || 90) / 100, (m.fontBoundingBoxDescent || 21) / 100]);
      }
      return ratios.get(family);
    },
  };

  async function loadFaces() {
    for (const face of scene.faces) {
      if (faces.has(face)) continue;
      try {
        const blob = await fetchBlob(`/api/hud/font?s=${scene.session}&face=${encodeURIComponent(face)}`);
        if (!blob) continue;
        const family = 'aoe3 ' + face;
        const ff = new FontFace(family, await blob.arrayBuffer());
        await ff.load();
        document.fonts.add(ff);
        faces.set(face, family);
        ratios.delete(family);
      } catch { /* a typeface the page cannot load: the system font stands in */ }
    }
  }

  async function open() {
    if (!app.state.settings.paths.game) {          // nothing to read yet: say where to set it
      clear(details).append(h('p', { class: 'notice', text: t('h.nogame') }),
        h('button', { type: 'button', class: 'primary', text: t('nav.settings'), onclick: () => app.go('settings') }));
      return;
    }
    status.textContent = t('b.working');
    try {
      scene = await api('/api/hud/open', { variant: variant.value });
      images.clear();
      renderer = new HudRenderer(scene, assets);
      originalRenderer = new HudRenderer(scene, assets);
      drawMoments();
      drawEditBar();
      selected = hover = null;
      await loadFaces();
      view.fitted = false;
      sim = null;
      drawTree();
      redraw();
      drawDetails();
      runSim();
    } catch (e) {
      status.textContent = '';
      clear(details).append(h('p', { class: 'notice bad', text: e.message }));
      toast(e.message, 'bad');
    }
  }

  // ---- edits: the server applies them to the files as read and answers the scene again
  function drawEditBar() {
    undoBtn.disabled = !scene || !scene.undo;
    redoBtn.disabled = !scene || !scene.redo;
    changesBtn.textContent = t('h.changes', { n: scene ? scene.changed : 0 });
  }
  function refresh(r, focus) {
    const keepName = selected ? [selected.file, selected.name] : null;
    scene = r;
    renderer = new HudRenderer(scene, assets);
    if (focus !== undefined && focus !== null) selected = scene.gadgets[focus] || null;
    else if (keepName) selected = scene.gadgets.find(g => g.file === keepName[0] && g.name === keepName[1]) || null;
    hover = null;
    drawEditBar();
    drawTree();
    redraw();
    drawDetails();
    runSim();
  }
  async function op(ops, label) {
    try {
      const r = await api('/api/hud/op', { session: scene.session, ops, label: label || '' });
      refresh(r, r.focus);
    } catch (e) { toast(e.message, 'bad'); }
  }

  // several gadgets chosen with Shift: align, distribute, same size (one step of Undo)
  const multi = new Set();
  function chosen() { return [...multi].map(id => scene.gadgets[id]).filter(g => g && g.rect.length === 4); }
  function arrange(kind) {
    const gs = chosen();
    if (gs.length < 2) { toast(t('h.pickmore'), 'bad'); return; }
    const anchor = selected && multi.has(selected.id) ? selected : gs[0];
    const ops = [];
    const shift = (g, dx, dy) => { if (dx || dy) ops.push({ op: 'shift', id: g.id, dx, dy, children: true }); };
    const [ax1, ay1, ax2, ay2] = anchor.rect;
    if (kind === 'left') gs.forEach(g => shift(g, ax1 - g.rect[0], 0));
    if (kind === 'right') gs.forEach(g => shift(g, ax2 - g.rect[2], 0));
    if (kind === 'top') gs.forEach(g => shift(g, 0, ay1 - g.rect[1]));
    if (kind === 'bottom') gs.forEach(g => shift(g, 0, ay2 - g.rect[3]));
    if (kind === 'hcentre') gs.forEach(g => shift(g, Math.round((ax1 + ax2) / 2 - (g.rect[0] + g.rect[2]) / 2), 0));
    if (kind === 'vcentre') gs.forEach(g => shift(g, 0, Math.round((ay1 + ay2) / 2 - (g.rect[1] + g.rect[3]) / 2)));
    if (kind === 'hspread' || kind === 'vspread') {
      const k = kind === 'hspread' ? 0 : 1;
      const sorted = [...gs].sort((a, b) => a.rect[k] - b.rect[k]);
      const total = sorted.reduce((s, g) => s + g.rect[k + 2] - g.rect[k], 0);
      const span = sorted[sorted.length - 1].rect[k + 2] - sorted[0].rect[k];
      const gap = (span - total) / (sorted.length - 1);
      let at = sorted[0].rect[k];
      for (const g of sorted) {
        const d = Math.round(at - g.rect[k]);
        shift(g, k === 0 ? d : 0, k === 1 ? d : 0);
        at += g.rect[k + 2] - g.rect[k] + gap;
      }
    }
    if (kind === 'samew' || kind === 'sameh') {
      for (const g of gs) {
        const [x1, y1, x2, y2] = g.rect;
        const r = kind === 'samew' ? [x1, y1, x1 + (ax2 - ax1), y2] : [x1, y1, x2, y1 + (ay2 - ay1)];
        ops.push({ op: 'set', id: g.id, attrs: { size1024: r.join(' ') } });
      }
    }
    if (ops.length) op(ops, kind);
  }
  async function undo(again) {
    try {
      const r = await api('/api/hud/undo', { session: scene.session, redo: !!again });
      if (r.done) refresh(r);
    } catch (e) { toast(e.message, 'bad'); }
  }
  async function showChanges() {
    const r = await api('/api/hud/changes', { session: scene.session }).catch(e => { toast(e.message, 'bad'); return null; });
    if (!r) return;
    const body = h('div', { class: 'stack hud-diff' }, r.changes.length ? r.changes.map(c => h('div', {},
      h('h4', { text: c.stem }), h('pre', { class: 'log' }, c.lines.map(l => h('span', { class: l.startsWith('+') ? 'ok' : l.startsWith('-') ? 'bad' : '', text: l + String.fromCharCode(10) }))),
      c.more ? h('p', { class: 'small muted', text: t('h.more', { n: c.more }) }) : null)) : [h('p', { text: t('h.nochanges') })]);
    dialog(t('h.changes', { n: r.changes.length }), body, [{ value: 'ok', label: t('close') }]);
  }
  function findingsList(findings) {
    return findings.length ? h('ul', { class: 'small' }, findings.map(f => h('li', { class: f.level === 'error' ? 'bad' : f.level === 'warning' ? 'warn' : 'muted' },
      t('h.f.' + f.code, f) + (f.stem ? ` (${f.stem})` : '')))) : h('p', { class: 'ok', text: t('h.f.none') });
  }
  async function runCheck() {
    const r = await api('/api/hud/check', { session: scene.session, width: dims()[0] }).catch(e => { toast(e.message, 'bad'); return null; });
    if (r) dialog(t('h.check'), findingsList(r.findings), [{ value: 'ok', label: t('close') }]);
  }
  async function save(force) {
    const name = storeGet('hud.project', 'interface');
    try {
      const r = await api('/api/hud/save', { session: scene.session, name, width: dims()[0], force: !!force });
      if (r.refused) {
        const go = await confirmDialog(t('h.save'), t('h.saverefused'), t('h.saveanyway'));
        if (go) save(true);
        return;
      }
      const copy = app.state.settings.paths.test_copy;
      const deployBtn = r.written.length && copy ? h('button', { type: 'button', class: 'primary', text: t('h.deploy', { copy }),
        onclick: async () => {
          if (!await confirmDialog(t('h.deploy', { copy }), t('h.deploysure', { copy }), t('h.deploy.go'))) return;
          try {
            const j = await api('/api/tools/deploy_files', { values: { install: copy, files: r.folder } });
            toast(t('h.deploying'), 'ok');
            app.go('jobs');
            void j;
          } catch (e) { toast(e.message, 'bad'); }
        } }) : null;
      const body = h('div', { class: 'stack small' },
        r.written.length ? h('p', { text: t('h.saved', { path: r.folder }) }) : h('p', { text: t('h.nochanges') }),
        deployBtn, r.written.length && !copy ? h('p', { class: 'muted', text: t('h.nocopy') }) : null,
        r.written.length && copy ? h('p', { class: 'muted', text: t('h.undohint') }) : null,
        h('ul', {}, r.written.map(w => h('li', { class: 'mono', text: `${w.path}  ← ${w.from}` }))),
        r.findings.length ? h('h4', { text: t('h.check') }) : null, r.findings.length ? findingsList(r.findings) : null);
      dialog(t('h.save'), body, [{ value: 'open', label: t('open.folder') }, { value: 'ok', label: t('close') }])
        .then(v => { if (v === 'open' && r.folder) api('/api/open', { path: r.folder }).catch(() => {}); });
    } catch (e) { toast(e.message, 'bad'); }
  }

  // ---- drawing: the frame at the screen's pixels, then shown zoomed in the stage
  let pending = 0;
  function redrawSoon() { if (!pending) pending = requestAnimationFrame(() => { pending = 0; redraw(); }); }
  function redraw() {
    if (!scene) return;
    const [w, hh] = dims();
    frame = frame || document.createElement('canvas');
    frame.width = w; frame.height = hh;
    const r = (showOriginal && originalRenderer ? originalRenderer : renderer).draw(frame.getContext('2d'), w, hh, opts());
    list = r.list;
    const loading = [...images.values()].filter(v => v === undefined).length;
    status.textContent = t('h.status', { n: list.length, files: scene.files.length })
      + (r.missing.textures.size ? ' · ' + t('h.missingtex', { n: r.missing.textures.size }) : '')
      + (r.missing.fonts.size ? ' · ' + t('h.missingfont', { list: [...r.missing.fonts].join(', ') }) : '')
      + (loading ? ' · ' + t('h.loading', { n: loading }) : '');
    paint();
  }

  const ctx = canvas.getContext('2d');
  function fit() {
    const [w, hh] = dims();
    const cw = stage.clientWidth, ch = stage.clientHeight;
    view.zoom = Math.min(cw / w, ch / hh) * 0.98;
    view.x = (cw - w * view.zoom) / 2; view.y = (ch - hh * view.zoom) / 2;
    view.fitted = true;
  }
  function paint() {
    const dpr = window.devicePixelRatio || 1;
    const cw = stage.clientWidth, ch = stage.clientHeight;
    if (!cw || !ch) return;
    canvas.width = Math.round(cw * dpr); canvas.height = Math.round(ch * dpr);
    canvas.style.width = cw + 'px'; canvas.style.height = ch + 'px';
    if (!view.fitted) fit();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);
    if (!frame) return;
    ctx.imageSmoothingEnabled = view.zoom < 1;
    ctx.drawImage(frame, view.x, view.y, frame.width * view.zoom, frame.height * view.zoom);
    const box = (g, colour, width) => {
      const hit = list.find(e => e[0] === g);
      if (!hit) return;
      const [, x, y, w, hh] = hit;
      ctx.strokeStyle = colour; ctx.lineWidth = width;
      ctx.strokeRect(view.x + x * view.zoom, view.y + y * view.zoom, w * view.zoom, hh * view.zoom);
    };
    if (outlines.checked) for (const [g] of list) box(g, 'rgba(120,200,255,0.35)', 1);
    if (hover && hover !== selected) box(hover, 'rgba(255,255,255,0.8)', 1);
    for (const id of multi) if (!selected || id !== selected.id) box(scene.gadgets[id], '#55aaff', 2);
    for (const gd of guides) {
      ctx.strokeStyle = '#ff44cc'; ctx.lineWidth = 1; ctx.setLineDash([4, 3]);
      const [w0, h0] = dims();
      ctx.beginPath();
      if (gd.x !== undefined) { const X = view.x + gd.x * w0 / 1024 * view.zoom; ctx.moveTo(X, view.y); ctx.lineTo(X, view.y + h0 * view.zoom); }
      else { const Y = view.y + gd.y * h0 / 768 * view.zoom; ctx.moveTo(view.x, Y); ctx.lineTo(view.x + w0 * view.zoom, Y); }
      ctx.stroke(); ctx.setLineDash([]);
    }
    if (grid.checked) {
      const [w0, h0] = dims();
      ctx.strokeStyle = 'rgba(255,255,255,0.08)'; ctx.lineWidth = 1;
      ctx.beginPath();
      for (let gx = 0; gx <= 1024; gx += GRID) { const X = view.x + gx * w0 / 1024 * view.zoom; ctx.moveTo(X, view.y); ctx.lineTo(X, view.y + h0 * view.zoom); }
      for (let gy = 0; gy <= 768; gy += GRID) { const Y = view.y + gy * h0 / 768 * view.zoom; ctx.moveTo(view.x, Y); ctx.lineTo(view.x + w0 * view.zoom, Y); }
      ctx.stroke();
    }
    if (selected) {
      box(selected, '#ffcc33', 2);
      const b = list.find(e => e[0] === selected);
      if (b && !showOriginal) {
        const [, x, y, w, hh] = b;
        const sx = view.x + x * view.zoom, sy = view.y + y * view.zoom, sw = w * view.zoom, sh = hh * view.zoom;
        ctx.fillStyle = '#ffcc33';
        for (const [hx, hy] of [[sx, sy], [sx + sw, sy], [sx, sy + sh], [sx + sw, sy + sh]]) ctx.fillRect(hx - 4, hy - 4, 8, 8);
        if (edit && (edit.dx || edit.dy)) {
          const [w0, h0] = dims();
          const kx = w0 / 1024 * view.zoom, ky = h0 / 768 * view.zoom;
          let [gx, gy, gw, gh] = [sx, sy, sw, sh];
          if (edit.mode === 'move') { gx += edit.dx * kx; gy += edit.dy * ky; }
          else {
            if (edit.handle.includes('w')) { gx += edit.dx * kx; gw -= edit.dx * kx; } else gw += edit.dx * kx;
            if (edit.handle.includes('n')) { gy += edit.dy * ky; gh -= edit.dy * ky; } else gh += edit.dy * ky;
          }
          ctx.setLineDash([5, 4]); ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.5;
          ctx.strokeRect(gx, gy, gw, gh); ctx.setLineDash([]);
          ctx.fillStyle = 'rgba(0,0,0,0.7)'; ctx.fillRect(gx, gy - 18, 120, 16);
          ctx.fillStyle = '#fff'; ctx.font = '11px sans-serif';
          ctx.fillText(edit.mode === 'move' ? `Δ ${edit.dx}, ${edit.dy}` : `${edit.handle} ${edit.dx}, ${edit.dy}`, gx + 4, gy - 6);
        }
      }
    }
  }
  const resizer = new ResizeObserver(() => { view.fitted = false; paint(); });
  resizer.observe(stage);
  app.onLeave(() => resizer.disconnect());

  const toFrame = e => { const b = canvas.getBoundingClientRect(); return [(e.clientX - b.left - view.x) / view.zoom, (e.clientY - b.top - view.y) / view.zoom]; };
  // the screen pixels of a frame point, and the layout units of a frame distance
  const units = () => { const [w, hh] = dims(); return [1024 / w, 768 / hh]; };
  const selBox = () => (selected ? list.find(e => e[0] === selected) : null);
  function handleAt(fx, fy) {
    const b = selBox();
    if (!b) return null;
    const [, x, y, w, hh] = b;
    const r = 6 / view.zoom;
    for (const [name, hx, hy] of [['nw', x, y], ['ne', x + w, y], ['sw', x, y + hh], ['se', x + w, y + hh]]) {
      if (Math.abs(fx - hx) <= r && Math.abs(fy - hy) <= r) return name;
    }
    return null;
  }
  let drag = null, edit = null, guides = [];
  const GRID = 8;
  // the move snaps to an edge or centre of a gadget drawn (not inside the one moved), within a few
  // screen pixels; with the grid on, to the grid; Ctrl holds it free
  function snapMove(ux) {
    const [x1, y1, x2, y2] = selected.rect;
    const inside = new Set([selected.id]);
    for (const g of scene.gadgets) { for (let p = g.parent; p !== null && p !== undefined; p = scene.gadgets[p].parent) if (inside.has(p)) { inside.add(g.id); break; } }
    const tol = 6 / view.zoom * ux;
    let best = [null, null];
    for (const [g] of list) {
      if (inside.has(g.id) || g.rect.length !== 4) continue;
      const [ox1, oy1, ox2, oy2] = g.rect;
      for (const [k, mine, theirs] of [[0, [x1, x2, (x1 + x2) / 2], [ox1, ox2, (ox1 + ox2) / 2]], [1, [y1, y2, (y1 + y2) / 2], [oy1, oy2, (oy1 + oy2) / 2]]]) {
        const d = k === 0 ? edit.dx : edit.dy;
        for (const m of mine) for (const o of theirs) {
          const diff = o - (m + d);
          if (Math.abs(diff) <= tol && (!best[k] || Math.abs(diff) < Math.abs(best[k].diff))) best[k] = { diff, at: o };
        }
      }
    }
    if (best[0]) { edit.dx = Math.round(edit.dx + best[0].diff); guides.push({ x: best[0].at }); }
    if (best[1]) { edit.dy = Math.round(edit.dy + best[1].diff); guides.push({ y: best[1].at }); }
    if (grid.checked) {
      if (!best[0]) edit.dx = Math.round((x1 + edit.dx) / GRID) * GRID - x1;
      if (!best[1]) edit.dy = Math.round((y1 + edit.dy) / GRID) * GRID - y1;
    }
  }
  canvas.addEventListener('pointermove', e => {
    if (drag) { view.x = drag.vx + e.clientX - drag.x; view.y = drag.vy + e.clientY - drag.y; view.fitted = true; paint(); return; }
    if (!renderer) return;
    const [x, y] = toFrame(e);
    if (edit) {
      const [ux, uy] = units();
      edit.dx = Math.round((x - edit.fx) * ux);
      edit.dy = Math.round((y - edit.fy) * uy);
      guides = [];
      if (edit.mode === 'move' && selected && !e.ctrlKey) snapMove(ux, uy);
      paint();
      return;
    }
    const hd = handleAt(x, y);
    canvas.style.cursor = hd ? (hd === 'nw' || hd === 'se' ? 'nwse-resize' : 'nesw-resize') : 'crosshair';
    const g = renderer.hit(list, x, y);
    if (g !== hover) { hover = g; paint(); canvas.title = g ? g.name : ''; }
  });
  canvas.addEventListener('pointerdown', e => {
    if (e.button === 1 || e.button === 2) { drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; canvas.setPointerCapture(e.pointerId); return; }
    if (!renderer || showOriginal) return;
    const [x, y] = toFrame(e);
    const hd = handleAt(x, y);
    if (hd) { edit = { mode: 'resize', handle: hd, fx: x, fy: y, dx: 0, dy: 0 }; canvas.setPointerCapture(e.pointerId); return; }
    const g = renderer.hit(list, x, y);
    if (e.shiftKey) { select(g, true); return; }
    if (g !== selected) select(g);
    if (g && g.rect.length === 4) { edit = { mode: 'move', fx: x, fy: y, dx: 0, dy: 0, alone: e.altKey }; canvas.setPointerCapture(e.pointerId); }
  });
  canvas.addEventListener('pointerup', () => {
    drag = null;
    guides = [];
    if (!edit) return;
    const done = edit; edit = null;
    if (!selected || (!done.dx && !done.dy)) { paint(); return; }
    if (done.mode === 'move') op([{ op: 'shift', id: selected.id, dx: done.dx, dy: done.dy, children: !done.alone }], 'move');
    else {
      let [x1, y1, x2, y2] = selected.rect;
      if (done.handle.includes('w')) x1 += done.dx; else x2 += done.dx;
      if (done.handle.includes('n')) y1 += done.dy; else y2 += done.dy;
      const r = [Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)];
      op([{ op: 'set', id: selected.id, attrs: { size1024: r.join(' ') } }], 'resize');
    }
  });
  canvas.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'z' || e.key === 'Z')) { e.preventDefault(); undo(e.shiftKey); return; }
    if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || e.key === 'Y')) { e.preventDefault(); undo(true); return; }
    if (!selected || showOriginal) return;
    const step = e.shiftKey ? 10 : 1;
    const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (moves[e.key]) {
      e.preventDefault();
      op([{ op: 'shift', id: selected.id, dx: moves[e.key][0], dy: moves[e.key][1], children: !e.altKey }], 'nudge');
    } else if (e.key === 'Delete') {
      e.preventDefault();
      confirmDialog(t('h.del'), t('h.delsure', { name: selected.name || selected.type }), t('h.del'))
        .then(ok => { if (ok) op([{ op: 'del', id: selected.id }], 'del'); });
    } else if ((e.ctrlKey || e.metaKey) && (e.key === 'd' || e.key === 'D')) {
      e.preventDefault();
      op([{ op: 'dup', id: selected.id }], 'dup');
    }
  });
  canvas.addEventListener('contextmenu', e => e.preventDefault());
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    const b = canvas.getBoundingClientRect();
    const mx = e.clientX - b.left, my = e.clientY - b.top;
    const k = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    view.x = mx - (mx - view.x) * k; view.y = my - (my - view.y) * k; view.zoom *= k; view.fitted = true;
    paint();
  }, { passive: false });

  function select(g, add) {
    if (!add) multi.clear();
    if (g) { if (add && multi.has(g.id)) multi.delete(g.id); else multi.add(g.id); }
    selected = g;
    paint();
    drawDetails();
    drawTree();
    if (g) tree.querySelector(`[data-id="${g.id}"]`)?.scrollIntoView({ block: 'nearest' });
  }

  // ---- the tree: each file, its gadgets nested as the game reads them
  function drawTree() {
    clear(tree);
    if (!scene) return;
    const word = search.value.trim().toLowerCase();
    const shown = new Set(list.map(e => e[0].id));
    scene.files.forEach((f, i) => {
      const items = scene.gadgets.filter(g => g.file === i && (!word || g.name.toLowerCase().includes(word)));
      const depth = g => { let d = 0; for (let p = g.parent; p !== null && p !== undefined; p = scene.gadgets[p].parent) d++; return d; };
      tree.append(h('div', { class: 'hud-file small', title: f.where, text: `${f.stem} · ${items.length}` }),
        ...items.slice(0, word ? 400 : 2000).map(g => h('button', {
          type: 'button', 'data-id': g.id,
          class: 'hud-node' + (g === selected ? ' on' : '') + (shown.has(g.id) ? '' : ' off'),
          style: { paddingLeft: (6 + (word ? 0 : depth(g) * 10)) + 'px' },
          title: g.type, onclick: () => select(g),
        }, g.name || '(' + g.type + ')')));
    });
  }

  // ---- the moments of a game the engine shows gadgets for (aoe3game/uidata/hud_scene.json)
  function drawMoments() {
    clear(momentsBox).append(h('summary', { text: t('h.moments') }));
    const lang = document.documentElement.lang === 'es' ? 'es' : 'en';
    const box = h('div', { class: 'stack' });
    for (const m of scene.rules.moments) {
      box.append(h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: moments[m.id] ?? m.on,
        onchange: e => { moments[m.id] = e.target.checked; storeSet('hud.moments', moments); redraw(); } }), m[lang] || m.en));
    }
    for (const o of scene.rules.oneOf) {
      box.append(h('label', { class: 'row' }, (o[lang] || o.en) + ' ', h('select', { onchange: e => { oneOf[o.re] = e.target.value; storeSet('hud.oneOf', oneOf); redraw(); } },
        o.choices.map(c => h('option', { value: c, selected: c === (oneOf[o.re] || o.show), text: c })))));
    }
    momentsBox.append(box);
  }

  // ---- the unit the panels are filled for (aoe3game/unitpanel.py on the server)
  let sim = null;
  const unitSaved = storeGet('hud.unit', { name: 'Musketeer', state: {}, keys: [], rows: '' });
  const KEYS = ['minUIStats', 'overhealHitpointBars', 'damageOverTime', 'veterancyBonus', 'randomCost', 'shipmentCounts',
    'showGatherRate', 'buildingWorkRateAuras', 'resourceGatherAuras', 'unitResourceAuras'];
  async function runSim() {
    if (!scene) return;
    // a unit of this copy: the one asked if the copy has it, else its first
    const found = await api('/api/hud/units', { session: scene.session, q: unitSaved.name || '' }).catch(() => ({ units: [] }));
    if (!found.units.some(u => u.name.toLowerCase() === (unitSaved.name || '').toLowerCase())) {
      const first = found.units[0] || (await api('/api/hud/units', { session: scene.session, q: '' }).catch(() => ({ units: [] }))).units[0];
      if (!first) { sim = { error: t('h.u.nounits') }; if (tab === 'unit') drawDetails(); return; }
      unitSaved.name = first.name;
    }
    try {
      sim = await api('/api/hud/sim', { session: scene.session, unit: unitSaved.name, state: unitSaved.state,
        keys: unitSaved.keys, rows: unitSaved.rows || null });
    } catch (e) { sim = { error: e.message }; }
    storeSet('hud.unit', unitSaved);
    redraw();
    if (tab === 'unit') drawDetails();
  }

  // ---- what the chosen gadget says: its properties, or where each thing it names leads; the unit
  let tab = storeGet('hud.tab', 'unit');
  function drawDetails() {
    clear(details);
    if (!scene) return;
    const tabs = h('div', { class: 'row' }, [['unit', t('h.unit')], ['refs', t('h.refs')], ['props', t('h.props')]].map(([k, l]) =>
      h('button', { type: 'button', class: 'small' + (tab === k ? ' primary' : ''), text: l,
        onclick: () => { tab = k; storeSet('hud.tab', k); drawDetails(); } })));
    details.append(tabs);
    if (tab === 'unit') { drawUnit(); return; }
    if (!selected) { details.append(h('p', { class: 'small muted', text: t('h.pick') })); return; }
    const g = selected;
    details.append(h('h3', { text: g.name || '(' + g.type + ')' }));
    if (tab === 'refs') drawRefs(g); else drawProps(g);
  }

  function drawUnit() {
    const lang = document.documentElement.lang === 'es' ? 'es' : 'en';
    const box = h('div', { class: 'stack small hud-unit' });
    details.append(box);
    // the unit
    const results = h('div', { class: 'hud-units' });
    const q = h('input', { type: 'search', class: 'grow', placeholder: t('h.u.search'), oninput: async () => {
      const r = await api('/api/hud/units', { session: scene.session, q: q.value }).catch(() => ({ units: [] }));
      clear(results).append(...r.units.map(u => h('button', { type: 'button', class: 'hud-node', title: u.name,
        text: u.display && u.display !== u.name ? `${u.display} · ${u.name}` : u.name,
        onclick: () => { unitSaved.name = u.name; q.value = ''; clear(results); runSim(); } })));
    } });
    box.append(h('div', { class: 'row' }, q), results);
    if (!sim) { box.append(h('p', { class: 'muted', text: t('b.working') })); return; }
    if (sim.error) { box.append(h('p', { class: 'bad', text: sim.error })); return; }
    const u = sim.unit;
    box.append(h('p', {}, h('strong', { text: u.name }), ` · ${u.hp} HP · LOS ${u.los} · ${t('h.u.attacks', { list: sim.attacks.join(', ') || '—' })}`),
      h('p', { class: 'muted', text: t('h.u.types', { n: u.types.length }) + ' ' + u.types.slice(0, 12).join(', ') + (u.types.length > 12 ? '…' : '') }));
    // what it is doing
    const st = unitSaved.state;
    const num = (key, label, attrs = {}) => h('label', { class: 'row' }, h('span', { class: 'grow', text: label }),
      h('input', { type: 'number', value: st[key] ?? '', style: { width: '76px' }, ...attrs,
        onchange: e => { st[key] = e.target.value === '' ? null : Number(e.target.value); runSim(); } }));
    const flag = (key, label) => h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: !!st[key],
      onchange: e => { st[key] = e.target.checked; runSim(); } }), label);
    box.append(h('details', { open: true }, h('summary', { text: t('h.u.state') }),
      h('div', { class: 'stack' },
        num('hp', t('h.u.hp'), { placeholder: String(u.hp), min: 0 }), num('hp_bonus', t('h.u.hpbonus'), { min: 0 }),
        num('overheal', t('h.u.overheal'), { min: 0 }), num('garrison', t('h.u.garrison'), { min: 0 }),
        num('construction', t('h.u.construction'), { min: 0, max: 100, placeholder: '—' }), num('regen', t('h.u.regen'), { min: 0 }),
        num('player', t('h.u.player'), { min: 1, max: 8, placeholder: '1' }),
        h('label', { class: 'row' }, h('span', { class: 'grow', text: t('h.u.civ') }),
          h('input', { type: 'text', value: st.civ || '', style: { width: '120px' }, onchange: e => { st.civ = e.target.value; runSim(); } })),
        flag('poison', t('h.u.poison')), flag('gathering', t('h.u.gathering')), flag('building', t('h.u.building')),
        flag('veterancy', t('h.u.veterancy')), flag('aura', t('h.u.aura')))));
    // the DLL's keys
    box.append(h('details', {}, h('summary', { text: t('h.u.keys', { n: Object.keys(sim.keys).length }) }),
      h('p', { class: 'muted', text: sim.dll ? t('h.u.dll', { files: sim.files.cfg.join(', ') }) : t('h.u.nodll') }),
      h('div', { class: 'stack' }, KEYS.map(k => {
        const inFile = k.toLowerCase() in sim.keys && !unitSaved.keys.includes(k);
        return h('label', { class: 'row' }, h('input', { type: 'checkbox', checked: inFile || unitSaved.keys.includes(k), disabled: inFile,
          onchange: e => { unitSaved.keys = e.target.checked ? [...new Set([...unitSaved.keys, k])] : unitSaved.keys.filter(x => x !== k); runSim(); } }),
          h('span', { class: 'mono', text: k }), inFile ? h('span', { class: 'pill', text: t('h.u.infile') }) : null);
      }))));
    // the rows file
    const rowsPath = h('input', { type: 'text', class: 'grow', value: unitSaved.rows || '', placeholder: sim.files.rows_asked });
    box.append(h('details', { open: !sim.files.rows }, h('summary', { text: t('h.u.rows') }),
      h('p', { class: sim.files.rows ? 'muted' : 'warn', text: sim.files.rows ? t('h.u.rowsfrom', { path: sim.files.rows }) : t('h.u.norows', { path: sim.files.rows_asked }) }),
      h('div', { class: 'row' }, rowsPath,
        h('button', { type: 'button', class: 'small', text: t('browse'), onclick: async () => { const p = await pick('file', { title: t('h.u.rows'), filters: [['XML', '*.xml']] }); if (p) { rowsPath.value = p; unitSaved.rows = p; runSim(); } } }),
        h('button', { type: 'button', class: 'small', text: t('h.u.use'), onclick: () => { unitSaved.rows = rowsPath.value.trim(); runSim(); } }))));
    // what the DLL shows
    if (sim.rows.length) {
      box.append(h('h4', { text: t('h.u.dllrows') }), ...sim.rows.map(r => h('p', {},
        h('span', { class: 'mono', text: r.gadget.replace(/^unitselectionpanel-/, '') + ': ' }),
        r.text ? h('span', { text: r.text.replace(/<[^>]*>/g, '◆') }) : h('span', { class: 'muted', text: t('h.why.' + r.why, { gadget: r.gadget, types: (r.types || []).join(', ') }) }))));
    }
    // what exists and this unit does not show: the game's items, then the DLL's; a reason every DLL
    // item shares (the key off, no rows file) is said once, above them
    const why = r => h('li', {}, t('h.why.' + r.code, { ...r, keys: r.keys || (r.enable && r.enable.keys || []).join(', ') }), enabler(r.enable));
    const item = (a, reasons) => h('div', { class: 'hud-absent' },
      h('p', {}, h('strong', { text: a.item }), a.ref ? h('span', { class: 'mono muted', text: ` {${a.ref}}` }) : null,
        a.value ? h('span', { class: 'muted', text: ' = ' + a.value.replace(/<[^>]*>/g, '◆') }) : null),
      a[lang] ? h('p', { class: 'muted', text: a[lang] }) : null,
      h('ul', {}, reasons.map(why)));
    const stock = sim.absent.filter(a => a.kind !== 'dll'), dll = sim.absent.filter(a => a.kind === 'dll');
    const codes = dll.length ? dll[0].reasons.map(r => r.code).filter(c => dll.every(a => a.reasons.some(r => r.code === c))) : [];
    const common = dll.length ? dll[0].reasons.filter(r => codes.includes(r.code)) : [];
    box.append(h('h4', { text: t('h.u.absent', { n: sim.absent.length }) }),
      h('h5', { text: t('h.u.ofgame', { n: stock.length }) }), ...stock.map(a => item(a, a.reasons)));
    if (dll.length) {
      const own = dll.map(a => [a, a.reasons.filter(r => !codes.includes(r.code))]);
      own.sort((x, y) => (y[0].value ? 1 : 0) - (x[0].value ? 1 : 0));
      box.append(h('h5', { text: t('h.u.ofdll', { n: dll.length }) }),
        common.length ? h('div', { class: 'notice small' }, h('p', { text: t('h.u.allof') }), h('ul', {}, common.map(why))) : null,
        h('details', { open: dll.length <= 10 }, h('summary', { text: t('h.u.items', { n: dll.length }) }),
          ...own.map(([a, reasons]) => item(a, reasons.length ? reasons : [{ code: 'only_common' }]))));
    }
  }

  // a row of the DLL for an item: a formatText gadget at the top level of the selection panel (as the
  // DLL's own proposal places them) and its line in the rows file, as one step of Undo
  function addRow(gadget, item) {
    const panel = scene.gadgets.find(g => g.name.toLowerCase() === 'unitselectionpanel-unit')
      || scene.gadgets.find(g => g.name.toLowerCase() === 'unitselectionpanel');
    if (!panel) { toast(t('h.nopanel'), 'bad'); return; }
    const names = new Set(scene.gadgets.map(g => g.name.toLowerCase()));
    let name = gadget;
    if (!name) { let k = 0; while (names.has(`unitselectionpanel-uhcrow${k}`)) k++; name = `unitselectionpanel-uhcRow${k}`; }
    const rows = scene.gadgets.filter(g => /uhcrow|uhc/i.test(g.name) && g.rect.length === 4);
    const y = rows.length ? Math.max(...rows.map(g => g.rect[3])) + 2 : 712;
    const ops = [];
    if (item) {
      const label = item.charAt(0).toUpperCase() + item.slice(1).replace(/([A-Z])/g, ' $1').toLowerCase();
      ops.push({ op: 'row', gadget: name, text: `${label}: {${item}}`, rows: unitSaved.rows || null });
    }
    if (!names.has(name.toLowerCase())) {
      ops.push({ op: 'add', parent: panel.id, xml: `<gadget name="${name}" type="formatText" size1024="507 ${y} 700 ${y + 14}" textfont="StatText" textfontsize="10" textcolor="255 255 255" textmarkup="" formattextusedatareplace="" z="107"/>` });
    }
    if (ops.length) op(ops, 'row').then(() => { tab = 'unit'; drawDetails(); });
  }

  // a button that makes an absent item appear: a state, keys, the other UI
  function enabler(en) {
    if (!en) return null;
    const b = (text, fn) => h('button', { type: 'button', class: 'small ghost', text: text, onclick: fn });
    if (en.state) return b(t('h.en.state'), () => {
      const st = unitSaved.state;
      ({ overheal: () => { st.overheal = 30; }, garrison: () => { st.garrison = 2; }, poison: () => { st.poison = true; },
        construction: () => { st.construction = 40; }, building: () => { st.building = true; }, gathering: () => { st.gathering = true; },
        veterancy: () => { st.veterancy = true; }, aura: () => { st.aura = true; }, regen: () => { st.regen = 1; },
        lifespan: () => { st.lifespan = 30; } }[en.state] || (() => {}))();
      runSim();
    });
    if (en.keys) return b(t('h.en.keys', { keys: en.keys.join(', ') }), () => { unitSaved.keys = [...new Set([...unitSaved.keys, ...en.keys])]; runSim(); });
    if (en.variant) return b(t('h.en.variant'), () => { variant.value = en.variant; keep(); open(); });
    if (en.gadget || en.row) return b(t('h.en.addrow'), () => addRow(en.gadget, en.row));
    return null;
  }

  async function drawRefs(g) {
    const box = h('div', { class: 'stack hud-refs small' }, h('p', { class: 'muted', text: t('b.working') }));
    details.append(box);
    let r;
    try { r = await api('/api/hud/refs', { session: scene.session, id: g.id, width: dims()[0] }); }
    catch (e) { clear(box).append(h('p', { class: 'bad', text: e.message })); return; }
    if (selected !== g) return;
    const lang = document.documentElement.lang === 'es' ? 'es' : 'en';
    const short = p => String(p).replace(/^.*[\\/](data|art)[\\/]/i, '$1\\');
    const sec = (title, ...items) => h('section', {}, h('h4', { text: title }), ...items);
    clear(box);
    box.append(sec(t('h.r.file'), h('p', { class: 'mono', text: `${short(r.file.where)} · ${t('h.line')} ${r.file.line}` }),
      r.file.hidden.length ? h('p', { class: 'muted', text: t('h.r.hides', { list: r.file.hidden.map(short).join(', ') }) }) : null));
    if (r.engine.length) {
      box.append(sec(t('h.r.engine'), ...r.engine.map(e => h('div', {}, h('p', { text: e[lang] }),
        h('p', { class: 'muted', text: t('h.r.when') + ' ' + e.when[lang] })))));
    }
    if (r.strings.length) {
      box.append(sec(t('h.r.strings'), ...r.strings.map(s => h('p', {},
        h('span', { class: 'mono', text: `$$${s.id}$$ ` }), t('h.r.in.' + s.in) + ': ',
        s.found ? h('strong', { text: `“${s.text}”` }) : h('span', { class: 'bad', text: t('h.r.nostring', { fallback: s.fallback }) }),
        s.symbol ? h('span', { class: 'muted mono', text: ` (${s.symbol})` }) : null))));
    }
    if (r.textures.length) {
      box.append(sec(t('h.r.textures'), ...r.textures.map(x => {
        const img = h('img', { class: 'hud-thumb', alt: x.path });
        if (x.found.length) fetchBlob(`/api/hud/texture?s=${scene.session}&path=${encodeURIComponent(x.path)}`).then(b => { if (b && b.size) img.src = URL.createObjectURL(b); });
        return h('div', { class: 'row', style: { alignItems: 'flex-start' } }, img, h('div', { class: 'grow' },
          h('p', {}, h('strong', { text: t('h.r.role.' + x.role.split(' ')[0], null, x.role) + (x.role.includes(' ') ? ' ' + x.role.split(' ')[1] : '') + ': ' }), h('span', { class: 'mono', text: x.path })),
          x.found.length ? h('p', { class: 'muted mono', text: '→ ' + short(x.found[0]) + (x.size ? ` · ${x.size[0]} × ${x.size[1]}` : '') + (x.crop ? ` · texturecoords ${x.crop}` : '') })
            : h('p', { class: 'bad', text: t('h.r.notex') }),
          x.hidden.length ? h('p', { class: 'muted', text: t('h.r.hides', { list: x.hidden.map(short).join(', ') }) }) : null));
      })));
    }
    if (r.font) {
      const f = r.font;
      box.append(sec(t('h.r.font'),
        h('p', {}, h('span', { class: 'mono', text: f.asked }), ' → ',
          f.found ? h('span', { text: `${f.entry}` }) : h('span', { class: 'warn', text: t('h.r.nofont', { entry: f.entry }) })),
        h('p', { class: 'muted', text: t('h.r.face', { face: f.typeface, file: f.file ? short(f.file) : t('h.r.system'), cell: f.cell, resx: f.resx }) + (f.bold ? ' · bold' : '') })));
    }
    if (r.live.length) {
      box.append(sec(t('h.r.live'), ...r.live.map(l => h('div', {},
        h('p', {}, h('span', { class: 'mono', text: l.text }), ' ', !l.known ? h('span', { class: 'warn', text: t('h.r.unknownfn') })
          : l.works ? h('span', { text: l[lang] }) : h('span', { class: 'bad', text: t('h.r.stub') + ' ' + l[lang] })),
        l.proto ? h('p', { class: 'muted', text: t('h.r.reads', { field: l.proto }) }) : null))));
    }
    if (r.commands.length) box.append(sec(t('h.r.commands'), ...r.commands.map(c => h('p', { class: 'mono', text: c }))));
    if (r.parents.length) {
      box.append(sec(t('h.r.parents'), h('p', { text: r.parents.map(p => p.name + (p.hidden ? ' (' + t('h.r.hiddenp') + ')' : '')).join(' ‹ ') }),
        r.outside ? h('p', { class: 'warn', text: t('h.r.outside') }) : null));
    }
  }

  function drawProps(g) {
    const f = scene.files[g.file];
    const [w] = dims();
    const font = g.attrs.textfont ? fontAt(scene.fonts, g.attrs.textfont, g.attrs.textfontsize || '12', w, dims()[1]) : null;
    const row = (k, v) => h('tr', {}, h('th', { text: k }), h('td', { class: 'mono', text: v }));
    // what it is, then every attribute editable (Enter or leaving the field applies it)
    const set = (k, v) => op([{ op: 'set', id: g.id, attrs: { [k]: v } }], k);
    const edit = (k, v) => {
      const input = h('input', { type: 'text', class: 'mono', value: v,
        onkeydown: e => { if (e.key === 'Enter') e.target.blur(); },
        onchange: e => set(k, e.target.value) });
      return h('tr', {}, h('th', { text: k }), h('td', {}, h('div', { class: 'row' }, input, picker(k, v, set),
        h('button', { type: 'button', class: 'ghost small', text: '×', title: t('h.delattr'), onclick: () => op([{ op: 'set', id: g.id, attrs: { [k]: null } }], `-${k}`) }))));
    };
    const newKey = h('input', { type: 'text', class: 'mono', placeholder: t('h.attrname'), style: { width: '120px' } });
    const newVal = h('input', { type: 'text', class: 'mono grow', placeholder: t('h.attrvalue') });
    const text = h('textarea', { class: 'mono', rows: 2, value: g.text,
      onchange: e => op([{ op: 'text', id: g.id, text: e.target.value }], 'text') });
    const others = scene.gadgets.filter(o => o.file === g.file && o.id !== g.id);
    const into = h('select', {}, [h('option', { value: '', text: t('h.toplevel') }),
      ...others.slice(0, 1500).map(o => h('option', { value: o.id, selected: o.id === g.parent, text: o.name || '(' + o.type + ')' }))]);
    details.append(
      h('div', { class: 'row hud-actions' },
        h('button', { type: 'button', class: 'small', text: t('h.dup'), onclick: () => op([{ op: 'dup', id: g.id }], 'dup') }),
        h('button', { type: 'button', class: 'small', text: 'hidden' in g.attrs ? t('h.show') : t('h.hide'),
          onclick: () => op([{ op: 'set', id: g.id, attrs: { hidden: 'hidden' in g.attrs ? null : '' } }], 'hidden') }),
        h('button', { type: 'button', class: 'small', text: t('h.addchild'), onclick: () => {
          const [x1, y1] = g.rect.length ? g.rect : [0, 0];
          op([{ op: 'add', parent: g.id, xml: `<gadget name="${(g.name || 'gadget')}-new" type="formatText" size1024="${x1} ${y1} ${x1 + 100} ${y1 + 16}" textfont="StatText" textfontsize="12" textcolor="255 255 255">Text</gadget>` }], 'add');
        } }),
        h('button', { type: 'button', class: 'small danger', text: t('h.del'), onclick: async () => {
          if (await confirmDialog(t('h.del'), t('h.delsure', { name: g.name || g.type }), t('h.del'))) op([{ op: 'del', id: g.id }], 'del');
        } })),
      h('div', { class: 'row small' }, t('h.into') + ' ', into,
        h('button', { type: 'button', class: 'small', text: t('h.move'), onclick: () => op([{ op: 'move', id: g.id, parent: into.value === '' ? null : Number(into.value), file: g.file }], 'move') })),
      h('table', { class: 'hud-props small' },
        row(t('h.type'), g.type),
        row(t('h.file'), `${f.stem} (${f.where.split(/[\/]/).pop()}), ${t('h.line')} ${g.line}`),
        g.attrs.textfont ? row(t('h.font'), font && !font.Fallback ? `${font.Name} → ${font.TypeFace}, ${font.AscentHeight} px`
          : t('h.nofont', { f: `${g.attrs.textfont} ${g.attrs.textfontsize || ''}` }) + (font ? ` (${font.Name}, ${Number(font.AscentHeight).toFixed(1)} px)` : '')) : null,
        g.text ? row(t('h.shows'), displayText(g.text, scene.strings)) : null,
        g.states.length ? row(t('h.states'), g.states.join(' · ')) : null,
        g.commands.length ? row(t('h.commands'), g.commands.join(' · ')) : null),
      font ? h('p', { class: 'hud-sample', text: displayText(g.text, scene.strings) || 'Aa Bb 123', style: {
        fontFamily: `"${assets.face(font.TypeFace)}", Arial`, fontWeight: font.Bold ? 'bold' : 'normal',
        fontSize: (Number(font.AscentHeight) / assets.metrics(assets.face(font.TypeFace)).reduce((a, b) => a + b, 0)).toFixed(1) + 'px',
        color: `rgb(${(g.attrs.textcolor || '255 255 255').split(/\s+/).join(',')})` } }) : null,
      h('h4', { text: t('h.text') }), text,
      h('h4', { text: t('h.attrs') }),
      h('table', { class: 'hud-props hud-edit small' }, Object.entries(g.attrs).map(([k, v]) => edit(k, v))),
      h('div', { class: 'row' }, newKey, newVal, h('button', { type: 'button', class: 'small', text: t('h.addattr'), onclick: () => {
        if (newKey.value.trim()) op([{ op: 'set', id: g.id, attrs: { [newKey.value.trim()]: newVal.value } }], 'attr');
      } })));
  }

  // a picker beside an attribute: a colour, a font of fonts3.xml with a sample, a texture of the copy
  function picker(k, v, set) {
    if (k === 'textcolor' || k === 'backgroundcolor') {
      const [r, gg, b] = (v || '255 255 255').split(/[\s,]+/).map(Number);
      const hex = '#' + [r, gg, b].map(n => Math.max(0, Math.min(255, n || 0)).toString(16).padStart(2, '0')).join('');
      return h('input', { type: 'color', value: hex, title: t('h.pickcolour'),
        onchange: e => { const x = e.target.value; set(k, [1, 3, 5].map(i => parseInt(x.slice(i, i + 2), 16)).join(' ')); } });
    }
    if (k === 'textfont') {
      const names = [...new Set(Object.values(scene.fonts).map(f => f.name.replace(/\s+\d+$/, '')))].sort();
      return h('select', { title: t('h.pickfont'), onchange: e => set(k, e.target.value) },
        names.map(n => h('option', { value: n, selected: n.toLowerCase() === (v || '').toLowerCase(), text: n })));
    }
    if (['background', 'foreground', 'progressbarbackground', 'progressbarmask'].includes(k)) {
      return h('button', { type: 'button', class: 'small', text: '…', title: t('h.picktex'), onclick: () => texturePicker(v, path => set(k, path)) });
    }
    return null;
  }

  // the copy's interface textures, found by a word, shown as thumbnails
  function texturePicker(current, done) {
    const q = h('input', { type: 'search', class: 'grow', value: (current || '').split(/[\\/]/).pop(), placeholder: t('h.texsearch') });
    const gridBox = h('div', { class: 'hud-texgrid' });
    const find = async () => {
      const r = await api('/api/hud/textures', { session: scene.session, q: q.value }).catch(() => ({ textures: [] }));
      clear(gridBox).append(...r.textures.map(path => {
        const img = h('img', { alt: path });
        fetchSoon(`/api/hud/texture?s=${scene.session}&path=${encodeURIComponent(path)}`, bmp => {
          if (!bmp) return;
          const c = document.createElement('canvas'); c.width = bmp.width; c.height = bmp.height;
          c.getContext('2d').drawImage(bmp, 0, 0); img.src = c.toDataURL();
        });
        return h('button', { type: 'button', class: 'hud-tex', title: path, onclick: () => { document.getElementById('dialog').close(); done(path); } },
          img, h('span', { text: path.split('\\').pop() }));
      }));
    };
    q.addEventListener('input', () => { clearTimeout(q.timer); q.timer = setTimeout(find, 250); });
    find();
    dialog(t('h.picktex'), h('div', { class: 'stack' }, h('div', { class: 'row' }, q), gridBox), [{ value: 'no', label: t('cancel') }]);
  }

  async function snapshot() {
    if (!frame) return;
    try {
      const r = await api('/api/hud/snapshot', { picture: frame.toDataURL('image/png'), name: `${scene.variant}-${size.value}-${culture.value}` });
      toast(t('h.saved', { path: r.path }), 'ok');
    } catch (e) { toast(e.message, 'bad'); }
  }

  details.append(h('p', { class: 'small muted', text: t('h.pick') }));
  open();
}
