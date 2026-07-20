/* The Potter's Wheel — the Kiln fires the piece, the Wheel lets you turn it.
 *
 * A drag-to-orbit GLB viewer for the firing bench and the Curing Rack.
 * Orthographic, level-orbit start — it takes over at the exact yaw the
 * turntable strip was showing, so the piece never jumps in your hands.
 * Renders on demand only: the wheel spins while you spin it, then sleeps.
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const loader = new GLTFLoader();

export function mountWheel(container, glbUrl, { initialYaw = 0, reducedMotion = false } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.domElement.classList.add('wheel-canvas');
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  // over-the-shoulder rig: the key rides the camera (no angle unlit) but sits
  // off-axis, so the form still models — a dead-on headlamp flattens everything
  scene.add(new THREE.AmbientLight(0xffffff, 0.9));
  const key = new THREE.DirectionalLight(0xffffff, 2.6);
  scene.add(key, key.target);
  const camRight = new THREE.Vector3(), camUp = new THREE.Vector3();

  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 100);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = !reducedMotion;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minZoom = 0.5;
  controls.maxZoom = 6;

  let mag = 1, raf = null, lastActive = 0, dragging = false, disposed = false;
  const render = () => {
    const reach = camera.position.distanceTo(controls.target) || 1;
    camRight.setFromMatrixColumn(camera.matrixWorld, 0);
    camUp.setFromMatrixColumn(camera.matrixWorld, 1);
    key.position.copy(camera.position)
      .addScaledVector(camRight, reach * 0.6)
      .addScaledVector(camUp, reach * 0.5);
    key.target.position.copy(controls.target);
    renderer.render(scene, camera);
  };
  const loop = () => {
    raf = null;
    if (controls.update()) { render(); lastActive = performance.now(); }
    if (dragging || performance.now() - lastActive < 300) raf = requestAnimationFrame(loop);
  };
  const kick = () => { lastActive = performance.now(); if (!raf) raf = requestAnimationFrame(loop); };
  controls.addEventListener('start', () => { dragging = true; kick(); });
  controls.addEventListener('end', () => { dragging = false; kick(); });
  controls.addEventListener('change', () => { render(); kick(); });

  const size = () => {
    const w = container.clientWidth || 1, h = container.clientHeight || 1;
    renderer.setSize(w, h, false);
    const aspect = w / h;
    camera.left = -mag * aspect; camera.right = mag * aspect;
    camera.top = mag; camera.bottom = -mag;
    camera.updateProjectionMatrix();
    render();
  };
  const ro = new ResizeObserver(size);
  ro.observe(container);

  const ready = new Promise((resolve, reject) => {
    loader.load(glbUrl, (gltf) => {
      if (disposed) return resolve();  // the card re-dealt while the piece was loading
      // the kiln's GLBs carry POSITION only — no normals, no materials. Without
      // this pass three lights nothing (zero normals) and glTF's default
      // material is full-metal white: the piece renders as a flat gray ghost.
      gltf.scene.traverse((o) => {
        if (!o.isMesh) return;
        if (!o.geometry.getAttribute('normal')) o.geometry.computeVertexNormals();
        const m = o.material;
        if (m?.isMeshStandardMaterial) {
          m.metalness = 0; m.roughness = 0.88;
          if (!m.map && m.color.getHex() === 0xffffff) m.color.setHex(0xb9b4ac);  // bisque, like the strip
        }
      });
      scene.add(gltf.scene);
      const box = new THREE.Box3().setFromObject(gltf.scene);
      const center = box.getCenter(new THREE.Vector3());
      const span = Math.max(...box.getSize(new THREE.Vector3()).toArray()) || 1;
      mag = span * 0.72;                       // the turntable's own framing law
      camera.near = 0.01; camera.far = span * 12;
      const r = span * 2.5;
      camera.position.set(
        center.x + r * Math.sin(initialYaw),
        center.y,
        center.z + r * Math.cos(initialYaw),
      );
      controls.target.copy(center);
      controls.update();
      size();
      resolve();
    }, undefined, reject);
  });

  return {
    ready,
    dispose() {
      disposed = true;
      if (raf) cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      scene.traverse((o) => {
        o.geometry?.dispose?.();
        const mats = Array.isArray(o.material) ? o.material : [o.material];
        mats.forEach((m) => {
          if (!m) return;
          Object.values(m).forEach((v) => v?.isTexture && v.dispose());
          m.dispose?.();
        });
      });
      renderer.dispose();
      renderer.domElement.remove();
    },
  };
}
