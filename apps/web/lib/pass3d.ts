import {
  AmbientLight, BoxGeometry, BufferAttribute, BufferGeometry, CanvasTexture, DirectionalLight, DoubleSide,
  ExtrudeGeometry, Group, Material, Mesh, MeshBasicMaterial, MeshPhysicalMaterial, MeshStandardMaterial, Path,
  PerspectiveCamera, Plane, PlaneGeometry, PMREMGenerator, Raycaster, RepeatWrapping, Scene, Shape, ShapeGeometry,
  SRGBColorSpace, Texture, TorusGeometry, Vector2, Vector3, WebGLRenderer,
} from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { glyphs, type Glyph } from "./brand";

export type PassScene = {
  index: number;
  low: number;
  high: number;
  heats: number[];
  glyph: Glyph;
  mrz: [string, string];
  stamp: { word: string; sub: string; date: string };
  text: { kind: string; print: string; title: string; range: string; fields: [string, string][]; caution: string; keep: string; footer: string };
};

const C = {
  paper: "#faf8f4", ink: "#171512", lilac50: "#f4f1fc", lilac100: "#e9e6f2", lilac300: "#c8bcf6", lilac700: "#54409a",
  lime: "#d8ff3e", royal: "#2b3bea", magenta: "#d3006f", magenta500: "#ff3ea5",
};
const HOLO: [string, number][] = [["#e9fb98", 0], ["#c8bcf6", 0.32], ["#ffa8d6", 0.56], ["#a9b2ff", 0.8], ["#e9fb98", 1]];
const DISPLAY = "'Clash Display', 'Noto Sans HK Variable', sans-serif";
const MONO = "'JetBrains Mono Variable', 'Noto Sans HK Variable', monospace";
const BODY = "'Instrument Sans Variable', 'Noto Sans HK Variable', sans-serif";
const TAU = Math.PI * 2;
const W = 2.56;
const H = 4.0;
const TW = 1024;
const TH = 1600;
const ux = (px: number) => (px / TW - 0.5) * W;
const uy = (py: number) => (0.5 - py / TH) * H;
const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);
const easeBack = (t: number) => 1 + 2.4 * Math.pow(t - 1, 3) + 1.4 * Math.pow(t - 1, 2);

function prng(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function sheet(w: number, h: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const cv = document.createElement("canvas");
  cv.width = w;
  cv.height = h;
  return [cv, cv.getContext("2d")!];
}

type TextOptions = { align?: CanvasTextAlign; spacing?: number };
function text(g: CanvasRenderingContext2D, str: string, x: number, y: number, font: string, color: string, { align = "left", spacing = 0 }: TextOptions = {}) {
  g.font = font;
  g.fillStyle = color;
  g.textAlign = align;
  g.textBaseline = "alphabetic";
  g.letterSpacing = `${spacing}px`;
  g.fillText(str, x, y);
  const width = g.measureText(str).width;
  g.letterSpacing = "0px";
  return width;
}

function wrap(g: CanvasRenderingContext2D, str: string, font: string, width: number) {
  g.font = font;
  const words = /\s/.test(str) ? str.split(/(?<=\s)/) : [...str];
  const lines = [""];
  for (const word of words) {
    const next = lines[lines.length - 1] + word;
    if (g.measureText(next.trimEnd()).width > width && lines[lines.length - 1]) lines.push(word.trimStart());
    else lines[lines.length - 1] = next;
  }
  return lines.map((line) => line.trim());
}

function stampMark(size: number, color: string) {
  const [cv, g] = sheet(size, size);
  g.scale(size / 43, size / 43);
  g.translate(-1.5, -4.2);
  g.strokeStyle = color;
  g.lineCap = "round";
  g.lineJoin = "round";
  for (const [r, w] of [[19.4, 2.6], [15.6, 1]]) {
    g.lineWidth = w;
    g.beginPath();
    g.arc(23, 25.4, r, 0, TAU);
    g.stroke();
  }
  const tick = new Path2D("M12.5 24.8L20.6 33.2L40.6 7.6");
  g.globalCompositeOperation = "destination-out";
  g.lineWidth = 10.5;
  g.stroke(tick);
  g.globalCompositeOperation = "source-over";
  g.lineWidth = 5.4;
  g.stroke(tick);
  return cv;
}

function glyphSeal(g: CanvasRenderingContext2D, cx: number, cy: number, R: number, name: Glyph) {
  const shape = glyphs[name];
  g.save();
  g.translate(cx, cy);
  g.scale(R / 20.6, R / 20.6);
  g.translate(-23, -25.4);
  const gr = g.createLinearGradient(2.4, 4.8, 43.6, 46);
  HOLO.forEach(([c, at]) => gr.addColorStop(at, c));
  g.beginPath();
  g.arc(23, 25.4, 20.6, 0, TAU);
  g.fillStyle = gr;
  g.fill();
  g.strokeStyle = C.ink;
  g.lineWidth = 1.4;
  g.stroke();
  g.globalAlpha = 0.45;
  g.lineWidth = 0.8;
  g.beginPath();
  g.arc(23, 25.4, 16.4, 0, TAU);
  g.stroke();
  g.globalAlpha = 1;
  g.translate(12.92, 15.32);
  g.scale(0.84, 0.84);
  g.fillStyle = C.ink;
  g.lineCap = "round";
  g.lineJoin = "round";
  if (shape.f) {
    const p = new Path2D(shape.f);
    g.fill(p);
    g.lineWidth = 1;
    g.stroke(p);
  }
  if (shape.s) {
    g.lineWidth = 2.4;
    g.stroke(new Path2D(shape.s));
  }
  g.restore();
}

function guilloche(g: CanvasRenderingContext2D, color: string, rand: () => number) {
  g.save();
  g.lineWidth = 1.3;
  g.strokeStyle = color;
  for (let k = 0; k < 46; k++) {
    const y0 = (k * TH) / 46 + 18;
    g.beginPath();
    for (let x = 0; x <= TW; x += 6) {
      const y = y0 + 9 * Math.sin(x / 118 + k * 0.36) + 3.6 * Math.sin(x / 47 - k * 0.6);
      if (x) g.lineTo(x, y);
      else g.moveTo(x, y);
    }
    g.stroke();
  }
  g.lineWidth = 1;
  g.beginPath();
  const [R, r, d] = [260, 94, 130 + rand() * 4];
  for (let i = 0; i <= 7000; i++) {
    const t = (i / 7000) * TAU * 47;
    const x = 690 + (R - r) * Math.cos(t) + d * Math.cos(((R - r) / r) * t);
    const y = 980 + (R - r) * Math.sin(t) - d * Math.sin(((R - r) / r) * t);
    if (i) g.lineTo(x, y);
    else g.moveTo(x, y);
  }
  g.stroke();
  g.restore();
}

function drawFace(d: PassScene) {
  const [cv, g] = sheet(TW, TH);
  g.fillStyle = C.lilac50;
  g.fillRect(0, 0, TW, TH);
  const sheen = g.createLinearGradient(0, 0, TW * 0.7, TH * 0.45);
  sheen.addColorStop(0, "rgba(255,255,255,.75)");
  sheen.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = sheen;
  g.fillRect(0, 0, TW, TH);
  guilloche(g, "rgba(43,59,234,.11)", prng(7));

  const brand = `600 66px ${DISPLAY}`;
  g.font = brand;
  g.letterSpacing = "-2.3px";
  const wm = g.measureText("vibechecker").width;
  g.letterSpacing = "0px";
  g.drawImage(stampMark(100, C.magenta), 64 + wm - 8, 143, 50, 50);
  text(g, "vibechecker", 64, 190, brand, C.ink, { spacing: -2.3 });
  text(g, d.text.kind.toUpperCase(), TW - 64, 182, `500 25px ${MONO}`, C.lilac700, { align: "right", spacing: 4 });

  g.beginPath();
  g.roundRect(64, 240, 356, 500, 28);
  g.fillStyle = C.lilac100;
  g.fill();
  g.lineWidth = 2;
  g.strokeStyle = "rgba(23,21,18,.55)";
  g.stroke();
  if (d.heats.length) {
    const rowH = 420 / d.heats.length;
    g.fillStyle = C.royal;
    d.heats.forEach((v, i) => {
      g.globalAlpha = 0.3 + v * 0.62;
      g.beginPath();
      g.roundRect(92, 270 + i * rowH, 40 + v * 250, rowH * 0.62, rowH * 0.31);
      g.fill();
    });
    g.globalAlpha = 1;
    text(g, d.text.print.toUpperCase(), 92, 720, `500 19px ${MONO}`, C.lilac700, { spacing: 3 });
  }

  text(g, d.text.title.toUpperCase(), 468, 272, `500 25px ${MONO}`, C.lilac700, { spacing: 4 });
  const iw = text(g, String(d.index), 456, 532, `600 292px ${DISPLAY}`, C.ink, { spacing: -13 });
  text(g, "/100", 456 + iw + 8, 532, `500 36px ${MONO}`, C.lilac700);
  text(g, d.text.range.toUpperCase(), 468, 614, `500 25px ${MONO}`, C.lilac700, { spacing: 4 });
  text(g, `${d.low}–${d.high}`, 466, 690, `600 72px ${DISPLAY}`, C.ink, { spacing: -1.5 });
  const [bx, by, bw, bh] = [468, 718, 492, 34];
  g.lineWidth = 2;
  g.strokeStyle = "rgba(23,21,18,.7)";
  g.beginPath();
  g.roundRect(bx, by, bw, bh, 17);
  g.fillStyle = C.paper;
  g.fill();
  g.stroke();
  g.beginPath();
  g.roundRect(bx + (bw * d.low) / 100, by, Math.max(bh, (bw * (d.high - d.low)) / 100), bh, 17);
  g.fillStyle = C.lime;
  g.fill();
  g.stroke();
  g.beginPath();
  g.roundRect(bx + (bw * d.index) / 100 - 5, by - 12, 10, bh + 24, 5);
  g.fillStyle = C.ink;
  g.fill();

  const cols = [64, 432, 752];
  const row = (y: number, items: [string, string][]) =>
    items.forEach(([label, value], i) => {
      text(g, label.toUpperCase(), cols[i], y, `500 23px ${MONO}`, C.lilac700, { spacing: 3.5 });
      text(g, value, cols[i], y + 56, `600 42px ${BODY}`, C.ink);
    });
  row(872, d.text.fields.slice(0, 3));
  row(1012, d.text.fields.slice(3));

  g.save();
  g.setLineDash([10, 9]);
  g.lineWidth = 2.4;
  g.strokeStyle = "rgba(23,21,18,.3)";
  g.beginPath();
  g.moveTo(64, 1126);
  g.lineTo(TW - 64, 1126);
  g.stroke();
  g.restore();
  d.mrz.forEach((line, i) => text(g, line.padEnd(33, "<").slice(0, 33), 64, 1214 + i * 56, `500 33px ${MONO}`, "rgba(23,21,18,.86)", { spacing: 7 }));

  const foil = g.createLinearGradient(64, 0, TW - 64, 0);
  ["#e9fb98", "#c8bcf6", "#ffa8d6", "#a9b2ff", "#e9fb98"].forEach((c, i) => foil.addColorStop(i / 4, c));
  g.beginPath();
  g.roundRect(64, 1318, TW - 128, 70, 14);
  g.fillStyle = foil;
  g.fill();
  text(g, "VIBECHECKER · 已檢 · VIBECHECKER · 已檢 · VIBECHECKER", TW / 2, 1362, `600 19px ${MONO}`, "rgba(43,59,234,.45)", { align: "center", spacing: 6 });
  text(g, d.text.footer.toUpperCase(), TW / 2, 1478, `500 21px ${MONO}`, C.lilac700, { align: "center", spacing: 4 });
  return cv;
}

function drawBack(d: PassScene) {
  const [cv, g] = sheet(TW, TH);
  g.fillStyle = C.ink;
  g.fillRect(0, 0, TW, TH);
  guilloche(g, "rgba(200,188,246,.13)", prng(3));
  g.drawImage(stampMark(680, C.magenta500), TW / 2 - 170, 390, 340, 340);
  text(g, "vibechecker", TW / 2, 900, `600 104px ${DISPLAY}`, C.paper, { align: "center", spacing: -3.5 });
  const font = `600 52px ${DISPLAY}`;
  const lines = wrap(g, d.text.caution, font, TW - 200).slice(0, 3);
  lines.forEach((line, i) => text(g, line, TW / 2, 1080 + i * 66, font, C.lime, { align: "center", spacing: -0.5 }));
  text(g, d.text.keep.toUpperCase(), TW / 2, 1150 + lines.length * 66, `500 22px ${MONO}`, C.lilac300, { align: "center", spacing: 4 });
  return cv;
}

function drawSeal(glyph: Glyph) {
  const [cv, g] = sheet(512, 512);
  glyphSeal(g, 256, 256, 230, glyph);
  return cv;
}

function drawStamp({ word, sub, date }: PassScene["stamp"]) {
  const S = 512;
  const c = S / 2;
  const [cv, g] = sheet(S, S);
  const rand = prng(11);
  g.strokeStyle = C.magenta;
  g.fillStyle = C.magenta;
  g.lineWidth = 13;
  g.beginPath();
  g.arc(c, c, 238, 0, TAU);
  g.stroke();
  g.lineWidth = 5;
  g.beginPath();
  g.arc(c, c, 168, 0, TAU);
  g.stroke();
  const label = [...`VIBE CHECKED · ${date} · 氛圍檢查 · VIBECHECKER · `];
  g.font = `600 33px ${DISPLAY}`;
  g.textAlign = "center";
  g.textBaseline = "middle";
  const widths = label.map((ch) => g.measureText(ch).width);
  const radius = 203;
  const gap = (TAU * radius - widths.reduce((a, b) => a + b, 0)) / label.length;
  let a = -Math.PI / 2;
  label.forEach((ch, i) => {
    const w = widths[i] + gap;
    const mid = a + w / 2 / radius;
    g.save();
    g.translate(c + radius * Math.cos(mid), c + radius * Math.sin(mid));
    g.rotate(mid + Math.PI / 2);
    g.fillText(ch, 0, 0);
    g.restore();
    a += w / radius;
  });
  g.lineWidth = 4.5;
  g.beginPath();
  g.moveTo(c - 112, c - 62);
  g.lineTo(c + 112, c - 62);
  g.moveTo(c - 112, c + 96);
  g.lineTo(c + 112, c + 96);
  g.stroke();
  g.textBaseline = "alphabetic";
  g.font = `600 ${[...word].length > 5 ? 80 : 96}px ${DISPLAY}`;
  g.fillText(word, c, c + 32, 300);
  g.font = `700 29px ${MONO}`;
  g.letterSpacing = "10px";
  g.fillText(sub, c + 5, c + 76, 300);
  g.letterSpacing = "0px";
  g.globalCompositeOperation = "destination-out";
  for (let i = 0; i < 3200; i++) {
    g.globalAlpha = rand() * 0.85;
    g.beginPath();
    g.arc(rand() * S, rand() * S, rand() * 2.8, 0, TAU);
    g.fill();
  }
  g.globalAlpha = 1;
  g.globalCompositeOperation = "source-over";
  return cv;
}

function drawStrap(color: string) {
  const [cv, g] = sheet(128, 1024);
  const rand = prng(5);
  g.fillStyle = color;
  g.fillRect(0, 0, 128, 1024);
  for (let y = 0; y < 1024; y += 3) {
    g.fillStyle = `rgba(23,21,18,${0.025 + rand() * 0.045})`;
    g.fillRect(0, y, 128, 1);
  }
  g.strokeStyle = "rgba(23,21,18,.5)";
  g.lineWidth = 3;
  g.setLineDash([14, 10]);
  g.beginPath();
  g.moveTo(12, 0);
  g.lineTo(12, 1024);
  g.moveTo(116, 0);
  g.lineTo(116, 1024);
  g.stroke();
  g.save();
  g.translate(64, 0);
  g.rotate(Math.PI / 2);
  g.font = `600 46px ${DISPLAY}`;
  g.fillStyle = C.ink;
  g.textBaseline = "middle";
  g.letterSpacing = "-1px";
  for (let x = 40; x < 1024; x += 512) g.fillText("vibechecker", x, 0);
  g.restore();
  return cv;
}

function drawShadow() {
  const [cv, g] = sheet(256, 256);
  const gr = g.createRadialGradient(128, 128, 10, 128, 128, 128);
  gr.addColorStop(0, "rgba(84,64,154,.42)");
  gr.addColorStop(0.55, "rgba(84,64,154,.16)");
  gr.addColorStop(1, "rgba(84,64,154,0)");
  g.fillStyle = gr;
  g.fillRect(0, 0, 256, 256);
  return cv;
}

function cardShape() {
  const s = new Shape();
  const [x, y, r] = [-W / 2, -H / 2, 0.17];
  s.moveTo(x + r, y);
  s.lineTo(x + W - r, y);
  s.quadraticCurveTo(x + W, y, x + W, y + r);
  s.lineTo(x + W, y + H - r);
  s.quadraticCurveTo(x + W, y + H, x + W - r, y + H);
  s.lineTo(x + r, y + H);
  s.quadraticCurveTo(x, y + H, x, y + H - r);
  s.lineTo(x, y + r);
  s.quadraticCurveTo(x, y, x + r, y);
  const hole = new Path();
  const hw = ux(TW / 2 + 86);
  const top = uy(46);
  const bot = uy(82);
  const hr = (top - bot) / 2;
  hole.moveTo(-hw + hr, bot);
  hole.lineTo(hw - hr, bot);
  hole.absarc(hw - hr, bot + hr, hr, -Math.PI / 2, Math.PI / 2, false);
  hole.lineTo(-hw + hr, top);
  hole.absarc(-hw + hr, bot + hr, hr, Math.PI / 2, (3 * Math.PI) / 2, false);
  s.holes.push(hole);
  return s;
}

function sceneText(d: PassScene) {
  return [d.text.kind, d.text.title, d.text.range, d.text.caution, d.text.keep, d.text.footer, d.stamp.word, d.stamp.sub,
    ...d.text.fields.flat(), "已檢氛圍檢查"].join("");
}

// Returns a disposer once the lanyard is live, or null when the flat pass should stay.
export async function mount(stage: HTMLElement, data: PassScene): Promise<(() => void) | null> {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  try {
    await Promise.all([
      ...[`600 64px ${DISPLAY}`, `500 24px ${MONO}`, `700 24px ${MONO}`, `600 24px ${BODY}`].map((font) => document.fonts.load(font)),
      document.fonts.load("500 24px 'Noto Sans HK Variable'", sceneText(data)),
    ]);
  } catch {
    // Canvas text falls back to system fonts.
  }
  if (!stage.isConnected) return null;

  let renderer: WebGLRenderer;
  try {
    renderer = new WebGLRenderer({ antialias: true, alpha: true });
  } catch {
    return null;
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  const view = renderer.domElement;
  view.className = "stage-canvas";
  view.setAttribute("aria-hidden", "true");
  stage.prepend(view);

  const scene = new Scene();
  const pmrem = new PMREMGenerator(renderer);
  const room = new RoomEnvironment();
  const environment = pmrem.fromScene(room, 0.04).texture;
  room.dispose();
  scene.environment = environment;
  scene.add(new AmbientLight(0xffffff, 0.45));
  const key = new DirectionalLight(0xffffff, 0.9);
  key.position.set(3, 5, 7);
  scene.add(key);
  const camera = new PerspectiveCamera(28, 1, 0.1, 100);
  const texture = (cv: HTMLCanvasElement) => {
    const t = new CanvasTexture(cv);
    t.colorSpace = SRGBColorSpace;
    t.anisotropy = renderer.capabilities.getMaxAnisotropy();
    return t;
  };

  const shape = cardShape();
  const faceGeo = new ShapeGeometry(shape, 12);
  const pos = faceGeo.attributes.position;
  const uv = faceGeo.attributes.uv;
  for (let i = 0; i < uv.count; i++) uv.setXY(i, pos.getX(i) / W + 0.5, pos.getY(i) / H + 0.5);
  uv.needsUpdate = true;

  const holder = new Group();
  const body = new Mesh(new ExtrudeGeometry(shape, { depth: 0.04, bevelEnabled: false, curveSegments: 12 }), new MeshStandardMaterial({ color: 0xded9ee, roughness: 0.45 }));
  body.position.z = -0.02;
  const laminate = { roughness: 0.6, envMapIntensity: 0.3, specularIntensity: 0.35, clearcoat: 0.3, clearcoatRoughness: 0.35 };
  const front = new Mesh(faceGeo, new MeshPhysicalMaterial({ map: texture(drawFace(data)), ...laminate }));
  front.position.z = 0.0206;
  const back = new Mesh(faceGeo, new MeshPhysicalMaterial({ map: texture(drawBack(data)), ...laminate }));
  back.position.z = -0.0206;
  back.rotation.y = Math.PI;
  const foil = new Mesh(
    new PlaneGeometry(ux(TW - 64) - ux(64), (70 / TH) * H),
    new MeshPhysicalMaterial({ color: 0xffffff, metalness: 0.7, roughness: 0.22, iridescence: 1, iridescenceIOR: 1.45, iridescenceThicknessRange: [160, 900], transparent: true, opacity: 0.5 }),
  );
  foil.position.set(0, uy(1353), 0.0215);
  const seal = new Mesh(
    new PlaneGeometry(0.4, 0.4),
    new MeshPhysicalMaterial({ map: texture(drawSeal(data.glyph)), transparent: true, roughness: 0.3, metalness: 0.25, iridescence: 0.85, iridescenceIOR: 1.4, iridescenceThicknessRange: [200, 700], clearcoat: 1 }),
  );
  seal.position.set(ux(372), uy(755), 0.024);
  seal.rotation.z = (6 * Math.PI) / 180;
  const stampMaterial = new MeshBasicMaterial({ map: texture(drawStamp(data.stamp)), transparent: true, opacity: reduce ? 0.92 : 0, depthWrite: false });
  const stamp = new Mesh(new PlaneGeometry(1.28, 1.28), stampMaterial);
  stamp.position.set(ux(770), uy(1168), 0.027);
  stamp.rotation.z = (13 * Math.PI) / 180;
  holder.add(body, front, back, foil, seal, stamp);
  holder.position.y = -uy(64);

  const metal = new MeshStandardMaterial({ color: 0xdcd9e8, metalness: 1, roughness: 0.32 });
  const clipBody = new Mesh(new BoxGeometry(0.34, 0.2, 0.09), metal);
  clipBody.position.y = 0.33;
  const tongue = new Mesh(new BoxGeometry(0.24, 0.3, 0.018), metal);
  tongue.position.y = 0.14;
  const ring = new Mesh(new TorusGeometry(0.085, 0.022, 12, 32), metal);
  ring.position.y = 0.5;
  const card = new Group();
  card.add(holder, clipBody, tongue, ring);
  scene.add(card);

  const shadow = new Mesh(new PlaneGeometry(W * 1.5, H * 1.3), new MeshBasicMaterial({ map: texture(drawShadow()), transparent: true, depthWrite: false }));
  scene.add(shadow);

  const strapTex = texture(drawStrap(C.lime));
  strapTex.wrapT = RepeatWrapping;
  const N = 10;
  const strapGeo = new BufferGeometry();
  const strapPos = new BufferAttribute(new Float32Array((N + 1) * 2 * 3), 3);
  const strapUv = new BufferAttribute(new Float32Array((N + 1) * 2 * 2), 2);
  strapGeo.setAttribute("position", strapPos);
  strapGeo.setAttribute("uv", strapUv);
  strapGeo.setAttribute("normal", new BufferAttribute(new Float32Array((N + 1) * 2 * 3).map((_, i) => (i % 3 === 2 ? 1 : 0)), 3));
  const index: number[] = [];
  for (let i = 0; i < N; i++) index.push(i * 2, i * 2 + 1, i * 2 + 2, i * 2 + 1, i * 2 + 3, i * 2 + 2);
  strapGeo.setIndex(index);
  const strap = new Mesh(strapGeo, new MeshStandardMaterial({ map: strapTex, roughness: 0.85, side: DoubleSide }));
  strap.frustumCulled = false;
  scene.add(strap);

  type Point = { x: number; y: number; px: number; py: number; w: number };
  let half = 3.1;
  let anchorRest = 4.2;
  let pivotRest = 1.55;
  const RING = 0.5;
  const toCenter = -holder.position.y;
  const pts: Point[] = [];
  const links: [number, number, number][] = [];
  function layout() {
    const seg = (anchorRest - (pivotRest + RING)) / N;
    pts.length = 0;
    links.length = 0;
    for (let i = 0; i <= N; i++) pts.push({ x: 0, y: anchorRest - i * seg, px: 0, py: anchorRest - i * seg, w: i ? 1 : 0 });
    pts.push({ x: 0, y: pivotRest, px: 0, py: pivotRest, w: 1 });
    pts.push({ x: 0, y: pivotRest - toCenter, px: 0, py: pivotRest - toCenter, w: 0.3 });
    for (let i = 0; i < N; i++) links.push([i, i + 1, seg]);
    links.push([N, N + 1, RING]);
    links.push([N + 1, N + 2, toCenter]);
  }
  const pivot = () => pts[N + 1];
  const center = () => pts[N + 2];

  function resize() {
    const sw = stage.clientWidth;
    const sh = stage.clientHeight;
    const cw = view.clientWidth;
    const ch = view.clientHeight;
    if (!sw || !sh || !cw || !ch) return;
    renderer.setSize(cw, ch, false);
    camera.aspect = cw / ch;
    const fit = Math.max(2.9, (1.95 * sh) / sw);
    half = (fit * ch) / sh;
    camera.position.set(0, 0, half / Math.tan((14 * Math.PI) / 180));
    camera.updateProjectionMatrix();
    anchorRest = half + 1.1;
    pivotRest = fit - 1.55;
  }
  resize();
  layout();
  if (!reduce) {
    for (const p of pts) {
      p.y += 4.2;
      p.py += 4.2;
    }
    center().x += 0.35;
    center().px += 0.35;
  }

  const STEP = 1 / 120;
  const G = -22;
  let dragging = false;
  let hover = false;
  const pointer = { x: 0, y: 0 };
  const grab = { x: 0, y: 0 };
  let yaw = 0.32;
  let yawV = 0;

  function step(dt: number, anchorY: number) {
    pts[0].x = 0;
    pts[0].y = anchorY;
    let motion = 0;
    for (const p of pts) {
      if (!p.w) continue;
      const vx = (p.x - p.px) * 0.99;
      const vy = (p.y - p.py) * 0.99;
      p.px = p.x;
      p.py = p.y;
      p.x += vx;
      p.y += vy + G * dt * dt;
    }
    const c = center();
    if (dragging) {
      c.px = c.x;
      c.py = c.y;
      c.x += (pointer.x + grab.x - c.x) * 0.35;
      c.y += (pointer.y + grab.y - c.y) * 0.35;
    }
    for (let k = 0; k < 16; k++) {
      for (const [ia, ib, len] of links) {
        const a = pts[ia];
        const b = pts[ib];
        const wa = dragging && ia === N + 2 ? 0 : a.w;
        const wb = dragging && ib === N + 2 ? 0 : b.w;
        const sum = wa + wb;
        if (!sum) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.hypot(dx, dy) || 1e-6;
        const diff = (dist - len) / dist;
        a.x += (dx * diff * wa) / sum;
        a.y += (dy * diff * wa) / sum;
        b.x -= (dx * diff * wb) / sum;
        b.y -= (dy * diff * wb) / sum;
      }
    }
    if (!Number.isFinite(c.x + c.y + pivot().x + pivot().y)) {
      dragging = false;
      layout();
      return 1;
    }
    for (const p of pts) motion = Math.max(motion, Math.abs(p.x - p.px) + Math.abs(p.y - p.py));
    const target = dragging || hover ? clamp((pointer.x - c.x) * 0.4, -0.7, 0.7) + 0.12 : 0.32;
    yawV += (target - yaw) * 0.02 - yawV * 0.06;
    yaw += yawV;
    return Math.max(motion, Math.abs(yawV), Math.abs(target - yaw) * 0.01);
  }

  function pose(t: number) {
    const p = pivot();
    const c = center();
    const roll = Math.atan2(-(p.x - c.x), p.y - c.y);
    const vx = (c.x - c.px) / STEP;
    const vy = (c.y - c.py) / STEP;
    card.position.set(p.x, p.y, 0);
    card.rotation.set(clamp(-vy * 0.03, -0.25, 0.25) - 0.06, yaw + clamp(vx * 0.04, -0.4, 0.4), roll, "ZXY");
    shadow.position.set(c.x + 0.3, c.y - 0.32, -1.6);
    shadow.rotation.z = roll;
    const ringAt = { x: p.x - RING * Math.sin(roll), y: p.y + RING * Math.cos(roll) };
    const at = (i: number) => (i === N ? ringAt : pts[i]);
    let run = 0;
    for (let i = 0; i <= N; i++) {
      const a = at(Math.max(0, i - 1));
      const b = at(Math.min(N, i + 1));
      const tx = b.x - a.x;
      const ty = b.y - a.y;
      const tl = Math.hypot(tx, ty) || 1;
      const nx = (-ty / tl) * 0.15;
      const ny = (tx / tl) * 0.15;
      const q = at(i);
      strapPos.array.set([q.x + nx, q.y + ny, -0.03, q.x - nx, q.y - ny, -0.03], i * 6);
      if (i) run += Math.hypot(q.x - at(i - 1).x, q.y - at(i - 1).y);
      strapUv.array.set([1, -run / 2.4, 0, -run / 2.4], i * 4);
    }
    strapPos.needsUpdate = true;
    strapUv.needsUpdate = true;
    if (!reduce) {
      const k = clamp((t - 1.35) / 0.42, 0, 1);
      stampMaterial.opacity = Math.min(0.92, k * 2.2);
      stamp.scale.setScalar(1.5 - 0.5 * easeBack(k));
    }
  }

  const ray = new Raycaster();
  const ndc = new Vector2();
  const plane = new Plane(new Vector3(0, 0, 1), 0);
  const hit = new Vector3();
  function aim(e: PointerEvent) {
    const r = view.getBoundingClientRect();
    ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    ray.ray.intersectPlane(plane, hit);
    pointer.x = hit.x;
    pointer.y = hit.y;
  }
  const touching = () => ray.intersectObjects([front, back, body], false).length > 0;

  const t0 = performance.now();
  let last = t0;
  let acc = 0;
  let raf = 0;
  let still = 0;
  let visible = true;
  const draw = (t: number) => {
    pose(t);
    renderer.render(scene, camera);
  };
  function frame(now: number) {
    raf = 0;
    if (!visible) return;
    const dt = Math.min(0.1, (now - last) / 1000);
    last = now;
    acc += dt;
    const t = (now - t0) / 1000;
    const anchorY = anchorRest + 4.2 * (1 - easeOut(clamp(t / 0.85, 0, 1)));
    let motion = 0;
    while (acc >= STEP) {
      motion = Math.max(motion, step(STEP, anchorY));
      acc -= STEP;
    }
    draw(t);
    still = motion < 2e-5 && !dragging && !hover && t > 2.4 ? still + 1 : 0;
    if (still < 30) raf = requestAnimationFrame(frame);
  }
  function wake() {
    still = 0;
    if (reduce || raf || !visible) return;
    last = performance.now();
    acc = 0;
    raf = requestAnimationFrame(frame);
  }

  const down = (e: PointerEvent) => {
    aim(e);
    if (!touching()) return;
    dragging = true;
    grab.x = center().x - pointer.x;
    grab.y = center().y - pointer.y;
    stage.setPointerCapture(e.pointerId);
    stage.dataset.dragging = "";
    e.preventDefault();
    wake();
  };
  const move = (e: PointerEvent) => {
    aim(e);
    hover = touching();
    stage.style.cursor = dragging ? "grabbing" : hover ? "grab" : "";
    if (dragging || hover) wake();
  };
  const release = () => {
    dragging = false;
    delete stage.dataset.dragging;
    wake();
  };
  const leave = () => {
    hover = false;
    stage.style.cursor = "";
  };
  if (!reduce) {
    stage.addEventListener("pointerdown", down);
    stage.addEventListener("pointermove", move);
    stage.addEventListener("pointerup", release);
    stage.addEventListener("pointercancel", release);
    stage.addEventListener("pointerleave", leave);
  }

  const seen = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    if (visible) wake();
  });
  seen.observe(stage);
  let size = `${stage.clientWidth}x${stage.clientHeight}`;
  const sized = new ResizeObserver(() => {
    const next = `${stage.clientWidth}x${stage.clientHeight}`;
    if (next === size) return;
    size = next;
    resize();
    layout();
    if (reduce) draw(9);
    else wake();
  });
  sized.observe(stage);

  if (reduce) draw(9);
  else raf = requestAnimationFrame(frame);

  return () => {
    cancelAnimationFrame(raf);
    seen.disconnect();
    sized.disconnect();
    stage.removeEventListener("pointerdown", down);
    stage.removeEventListener("pointermove", move);
    stage.removeEventListener("pointerup", release);
    stage.removeEventListener("pointercancel", release);
    stage.removeEventListener("pointerleave", leave);
    delete stage.dataset.dragging;
    stage.style.cursor = "";
    scene.traverse((node) => {
      if (!(node instanceof Mesh)) return;
      node.geometry.dispose();
      for (const material of ([] as Material[]).concat(node.material)) {
        for (const value of Object.values(material)) if (value instanceof Texture) value.dispose();
        material.dispose();
      }
    });
    environment.dispose();
    pmrem.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
    view.remove();
  };
}
