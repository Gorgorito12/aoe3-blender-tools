// SPDX-License-Identifier: GPL-3.0-or-later
// The 3D view of a building: its mesh with its texture (or in clay, or with its wires), its
// attach points and its collision boxes, on a ground grid. Blender's Z-up metres are turned to
// three.js's Y-up.
import * as THREE from '../vendor/three.module.min.js';
import { OrbitControls } from '../vendor/OrbitControls.js';

export class Viewer {
  constructor(container) {
    this.container = container;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.prepend(this.renderer.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(35, 1, 0.1, 2000);
    this.camera.position.set(-22, 18, 30);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.addEventListener('change', () => this.draw());
    this.scene.add(new THREE.HemisphereLight(0xdfe9f3, 0x5a5040, 1.4));
    const sun = new THREE.DirectionalLight(0xffffff, 1.8);
    sun.position.set(-30, 50, 25);
    this.scene.add(sun);
    this.grid = new THREE.GridHelper(80, 80, 0x8a8a8a, 0xb0b0b0);
    this.grid.material.transparent = true;
    this.grid.material.opacity = 0.35;
    this.scene.add(this.grid);
    this.root = new THREE.Group();
    this.root.rotation.x = -Math.PI / 2;             // Blender Z up -> three Y up
    this.scene.add(this.root);
    this.mode = 'texture';
    this.show = { wire: false, attach: false, boxes: false, grid: true };
    this.textureMat = new THREE.MeshLambertMaterial({ side: THREE.FrontSide });
    this.clayMat = new THREE.MeshLambertMaterial({ color: 0xc9c4bb });
    this.wireMat = new THREE.LineBasicMaterial({ color: 0x1b1b1b, transparent: true, opacity: 0.55 });
    this.mesh = null;
    this.resizer = new ResizeObserver(() => this.resize());
    this.resizer.observe(container);
    this.resize();
    const loop = () => { this.frame = requestAnimationFrame(loop); if (this.controls.update()) this.draw(); };
    loop();
  }

  resize() {
    const w = this.container.clientWidth, hgt = this.container.clientHeight;
    if (!w || !hgt) return;
    this.renderer.setSize(w, hgt, false);
    this.camera.aspect = w / hgt;
    this.camera.updateProjectionMatrix();
    this.draw();
  }

  draw() { this.renderer.render(this.scene, this.camera); }

  setModel(data, textureUrl, frame) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(data.mesh.positions, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(data.mesh.uvs, 2));
    g.setIndex(data.mesh.indices);
    if (data.mesh.normals) g.setAttribute('normal', new THREE.Float32BufferAttribute(data.mesh.normals, 3));
    else g.computeVertexNormals();                   // a game model read without its normals
    g.computeBoundingBox();
    for (const child of [...this.root.children]) {
      this.root.remove(child);
      child.geometry?.dispose();
    }
    this.mesh = new THREE.Mesh(g, this.mode === 'clay' ? this.clayMat : this.textureMat);
    this.root.add(this.mesh);
    this.wires = new THREE.LineSegments(new THREE.WireframeGeometry(g), this.wireMat);
    this.root.add(this.wires);
    this.attach = new THREE.Group();
    for (const [, p] of Object.entries(data.attach || {})) {
      const s = new THREE.Mesh(new THREE.SphereGeometry(0.25, 12, 8), new THREE.MeshBasicMaterial({ color: 0x3f8fd8 }));
      s.position.set(p[0], p[1], p[2]);
      this.attach.add(s);
    }
    this.root.add(this.attach);
    this.boxes = new THREE.Group();
    for (const [x0, x1, y0, y1, z0, z1] of data.boxes || []) {
      const box = new THREE.Box3(new THREE.Vector3(x0, y0, z0), new THREE.Vector3(x1, y1, z1));
      this.boxes.add(new THREE.Box3Helper(box, 0xd23c3c));
    }
    this.root.add(this.boxes);
    if (textureUrl) this.setTexture(textureUrl);
    else if (textureUrl === null) { this.textureMat.map?.dispose(); this.textureMat.map = null; this.textureMat.needsUpdate = true; }
    this.apply();
    if (frame) this.frame_model();
    this.draw();
  }

  setTexture(url) {
    new THREE.TextureLoader().load(url, tex => {
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = this.renderer.capabilities.getMaxAnisotropy();
      this.textureMat.map?.dispose();
      this.textureMat.map = tex;
      this.textureMat.needsUpdate = true;
      this.draw();
    });
  }

  setMode(mode) {
    this.mode = mode;
    if (this.mesh) this.mesh.material = mode === 'clay' ? this.clayMat : this.textureMat;
    this.draw();
  }

  toggle(what, on) {
    this.show[what] = on;
    this.apply();
    this.draw();
  }

  apply() {
    if (this.wires) this.wires.visible = this.show.wire;
    if (this.attach) this.attach.visible = this.show.attach;
    if (this.boxes) this.boxes.visible = this.show.boxes;
    this.grid.visible = this.show.grid;
  }

  frame_model() {
    if (!this.mesh) return;
    const b = this.mesh.geometry.boundingBox;
    const size = new THREE.Vector3();
    b.getSize(size);
    const r = Math.max(size.length() / 2, 1);              // the bounding sphere
    const target = new THREE.Vector3(0, size.z * 0.4, 0);   // Blender's Z is three's Y
    const vfov = THREE.MathUtils.degToRad(this.camera.fov);
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * this.camera.aspect);
    const dist = r / Math.sin(Math.min(vfov, hfov) / 2) * 1.05;
    const dir = new THREE.Vector3(-0.55, 0.5, 0.85).normalize();
    this.controls.target.copy(target);
    this.camera.position.copy(target).addScaledVector(dir, dist);
    this.camera.near = dist / 100;
    this.camera.far = dist * 20;
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  view(name) {
    if (!this.mesh) return;
    const t = this.controls.target, d = this.camera.position.distanceTo(t);
    const dirs = { front: [0, 0.25, 1], back: [0, 0.25, -1], left: [-1, 0.25, 0], right: [1, 0.25, 0],
      top: [0, 1, 0.001], three: [-0.6, 0.55, 0.85] };
    const v = new THREE.Vector3(...dirs[name]).normalize().multiplyScalar(d);
    // Blender's front is -Y, which becomes +Z here
    this.camera.position.copy(t).add(v);
    this.controls.update();
    this.draw();
  }

  snapshot() { this.draw(); return this.renderer.domElement.toDataURL('image/png'); }

  dispose() {
    cancelAnimationFrame(this.frame);
    this.resizer.disconnect();
    this.controls.dispose();
    this.renderer.dispose();
  }
}
