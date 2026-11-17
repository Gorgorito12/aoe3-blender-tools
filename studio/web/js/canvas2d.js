// SPDX-License-Identifier: GPL-3.0-or-later
// A picture to work on: zoom with the wheel, move it by dragging, click a pixel, or draw a box
// with Shift held. An overlay (an ImageData of the same size) is drawn over it.

export class ImageView {
  constructor(container, { onPick, onBox, onHover } = {}) {
    this.container = container;
    this.canvas = document.createElement('canvas');
    this.canvas.className = 'imageview';
    this.canvas.tabIndex = 0;
    container.append(this.canvas);
    this.ctx = this.canvas.getContext('2d');
    this.image = null;               // an ImageBitmap or a canvas
    this.overlay = null;             // a canvas of the image's size
    this.zoom = 1; this.x = 0; this.y = 0;
    this.onPick = onPick; this.onBox = onBox; this.onHover = onHover;
    this.box = null;
    this.smooth = false;
    this.bind();
    this.resizer = new ResizeObserver(() => this.resize());
    this.resizer.observe(container);
  }

  async setImage(url, keepView) {
    const img = new Image();
    img.src = url;
    await img.decode();
    const first = !this.image || this.image.width !== img.width || this.image.height !== img.height;
    this.image = img;
    if (first || !keepView) this.fit();
    this.draw();
  }

  setOverlay(imageData) {
    if (!imageData) { this.overlay = null; this.draw(); return; }
    const c = this.overlay instanceof HTMLCanvasElement ? this.overlay : document.createElement('canvas');
    c.width = imageData.width; c.height = imageData.height;
    c.getContext('2d').putImageData(imageData, 0, 0);
    this.overlay = c;
    this.draw();
  }

  resize() {
    const w = this.container.clientWidth, h = this.container.clientHeight;
    if (!w || !h) return;
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = Math.round(w * dpr); this.canvas.height = Math.round(h * dpr);
    this.canvas.style.width = w + 'px'; this.canvas.style.height = h + 'px';
    if (this.image && !this.fitted) this.fit();
    this.draw();
  }

  fit() {
    if (!this.image) return;
    const w = this.canvas.width, h = this.canvas.height;
    if (!w || !h) return;
    this.zoom = Math.min(w / this.image.width, h / this.image.height) * 0.95;
    this.x = (w - this.image.width * this.zoom) / 2;
    this.y = (h - this.image.height * this.zoom) / 2;
    this.fitted = true;
  }

  draw() {
    const c = this.ctx;
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (!this.image) return;
    c.imageSmoothingEnabled = this.smooth || this.zoom < 1;
    // a checkerboard under the picture: its transparent (player colour) pixels show
    const w = this.image.width * this.zoom, h = this.image.height * this.zoom;
    c.fillStyle = '#7a7a7a'; c.fillRect(this.x, this.y, w, h);
    c.fillStyle = '#9a9a9a';
    const cell = 12;
    for (let yy = 0; yy < h; yy += cell) for (let xx = (yy / cell) % 2 ? cell : 0; xx < w; xx += 2 * cell) {
      c.fillRect(this.x + xx, this.y + yy, Math.min(cell, w - xx), Math.min(cell, h - yy));
    }
    c.setTransform(this.zoom, 0, 0, this.zoom, this.x, this.y);
    c.drawImage(this.image, 0, 0);
    if (this.overlay) c.drawImage(this.overlay, 0, 0);
    if (this.box) {
      const [x0, y0, x1, y1] = this.box;
      c.lineWidth = 2 / this.zoom; c.strokeStyle = '#ffde59'; c.setLineDash([6 / this.zoom, 4 / this.zoom]);
      c.strokeRect(x0, y0, x1 - x0, y1 - y0); c.setLineDash([]);
    }
  }

  // canvas pixels -> image pixels
  at(ev) {
    const r = this.canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    return [((ev.clientX - r.left) * dpr - this.x) / this.zoom, ((ev.clientY - r.top) * dpr - this.y) / this.zoom];
  }

  inside([x, y]) { return this.image && x >= 0 && y >= 0 && x < this.image.width && y < this.image.height; }

  bind() {
    const cv = this.canvas;
    let drag = null;
    cv.addEventListener('wheel', ev => {
      ev.preventDefault();
      const r = cv.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
      const mx = (ev.clientX - r.left) * dpr, my = (ev.clientY - r.top) * dpr;
      const k = Math.exp(-ev.deltaY * 0.0015);
      const z = Math.min(64, Math.max(0.05, this.zoom * k));
      this.x = mx - (mx - this.x) * z / this.zoom; this.y = my - (my - this.y) * z / this.zoom;
      this.zoom = z;
      this.draw();
    }, { passive: false });
    cv.addEventListener('pointerdown', ev => {
      cv.setPointerCapture(ev.pointerId);
      const p = this.at(ev);
      drag = { sx: ev.clientX, sy: ev.clientY, x: this.x, y: this.y, start: p, box: ev.shiftKey && this.onBox, moved: false,
        add: ev.shiftKey, sub: ev.altKey || ev.ctrlKey };
    });
    cv.addEventListener('pointermove', ev => {
      const p = this.at(ev);
      if (this.onHover) this.onHover(this.inside(p) ? p : null);
      if (!drag) return;
      const dx = ev.clientX - drag.sx, dy = ev.clientY - drag.sy;
      if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true;
      if (drag.box) {
        const [x0, y0] = drag.start;
        const cx = v => Math.max(0, Math.min(this.image.width, v));
        const cy = v => Math.max(0, Math.min(this.image.height, v));
        this.box = [cx(Math.min(x0, p[0])), cy(Math.min(y0, p[1])), cx(Math.max(x0, p[0])), cy(Math.max(y0, p[1]))];
      } else if (drag.moved) {
        const dpr = window.devicePixelRatio || 1;
        this.x = drag.x + dx * dpr; this.y = drag.y + dy * dpr;
      }
      this.draw();
    });
    cv.addEventListener('pointerup', ev => {
      if (!drag) return;
      const d = drag; drag = null;
      if (d.box && d.moved && this.box) {
        const [x0, y0, x1, y1] = this.box;
        this.onBox?.([x0 / this.image.width, y0 / this.image.height, x1 / this.image.width, y1 / this.image.height]);
        return;
      }
      if (!d.moved) {
        this.box = null; this.draw();
        const p = this.at(ev);
        if (this.inside(p)) this.onPick?.(Math.floor(p[0]), Math.floor(p[1]), { subtract: d.sub });
      }
    });
    cv.addEventListener('dblclick', () => { this.fit(); this.draw(); });
  }

  dispose() { this.resizer.disconnect(); }
}

// pixels of an image (by URL) as ImageData
export async function pixels(url) {
  const img = new Image();
  img.src = url;
  await img.decode();
  const c = document.createElement('canvas');
  c.width = img.width; c.height = img.height;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(img, 0, 0);
  return ctx.getImageData(0, 0, img.width, img.height);
}

// a picture file the user chose, as a PNG data URL the server reads (JPEG included: the
// browser decodes it, the studio needs no image library); `side` bounds its larger side
export async function fileToPng(file, side = 4096) {
  const bmp = await createImageBitmap(file);
  const k = Math.min(1, side / Math.max(bmp.width, bmp.height));
  const c = document.createElement('canvas');
  c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
  c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
  return c.toDataURL('image/png');
}
