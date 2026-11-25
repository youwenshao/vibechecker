import { spawnSync } from "node:child_process";
import { mkdir, stat, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { crc32, deflateSync } from "node:zlib";
import { Resvg } from "@resvg/resvg-js";
import { openSync } from "fontkit";

// Rebuilds the public brand masters from the live stamp and Clash Display wordmark.
const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const brand = join(web, "public", "brand");
const fontFile = join(web, "public", "fonts", "clash-display-semibold.woff2");

const PAPER = "#faf8f4";
const INK = "#171512";
const NIGHT = "#14123a";
const MAGENTA = "#d3006f";
const MAGENTA_500 = "#ff3ea5";
const LIME = "#d8ff3e";
const ROYAL = "#2b3bea";
const CREAM = PAPER;

const TICK = "M12.5 24.8L20.6 33.2L40.6 7.6";
const TIGHT = { x: 1.5, y: 4.2, w: 43, h: 43 };
const EM = 1000;
const TRACKING = -0.035;
const STAMP = 0.74;
const STAMP_PULL = 0.12;
const STAMP_DROP = 0.1;
const PX_PER_EM = 180;

const r2 = (n) => Math.round(n * 100) / 100;

function prepareFont() {
  const result = spawnSync(process.execPath, [join(web, "scripts", "prepare-font.mjs")], {
    stdio: "inherit",
  });
  if (result.status !== 0) throw new Error("Could not prepare Clash Display.");
}

function iconSvg(field, mark) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
  <defs>
    <mask id="cut" maskUnits="userSpaceOnUse" x="-4" y="-4" width="56" height="56">
      <rect x="-4" y="-4" width="56" height="56" fill="#fff"/>
      <path d="${TICK}" fill="none" stroke="#000" stroke-width="10.5" stroke-linecap="round" stroke-linejoin="round"/>
    </mask>
  </defs>
  <rect width="48" height="48" rx="11" fill="${field}"/>
  <g transform="translate(24 24) scale(.8) translate(-23 -25.7)" fill="none" stroke="${mark}">
    <g mask="url(#cut)">
      <circle cx="23" cy="25.4" r="19.4" stroke-width="3.4"/>
      <circle cx="23" cy="25.4" r="15.6" stroke-width="1.6"/>
    </g>
    <path d="${TICK}" stroke-width="5.6" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
</svg>`;
}

function stampSvg(color) {
  const { x, y, w, h } = TIGHT;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${x} ${y} ${w} ${h}">
  ${stampDefs()}
  ${stampBody(color)}
</svg>`;
}

function stampDefs() {
  return `<defs>
    <mask id="cut" maskUnits="userSpaceOnUse" x="-4" y="-4" width="56" height="56">
      <rect x="-4" y="-4" width="56" height="56" fill="#fff"/>
      <path d="${TICK}" fill="none" stroke="#000" stroke-width="10.5" stroke-linecap="round" stroke-linejoin="round"/>
    </mask>
  </defs>`;
}

function stampBody(color) {
  return `<g fill="none" stroke="${color}">
    <g mask="url(#cut)">
      <circle cx="23" cy="25.4" r="19.4" stroke-width="2.6"/>
      <circle cx="23" cy="25.4" r="15.6" stroke-width="1"/>
    </g>
    <path d="${TICK}" stroke-width="5.4" stroke-linecap="round" stroke-linejoin="round"/>
  </g>`;
}

function baselineFromTop(font) {
  const ascent = font.ascent / font.unitsPerEm;
  const descent = Math.abs(font.descent) / font.unitsPerEm;
  const halfLeading = (1 - (ascent + descent)) / 2;
  return halfLeading + ascent;
}

function wordmark(font, { fill, stamp, background }) {
  const run = font.layout("vibechecker");
  const scale = EM / font.unitsPerEm;
  const baseline = baselineFromTop(font) * EM;
  let x = 0;
  const glyphs = [];
  let minX = 0;
  let minY = 0;
  let maxX = 0;
  let maxY = EM;
  const grow = (bx, by, bw, bh) => {
    minX = Math.min(minX, bx);
    minY = Math.min(minY, by);
    maxX = Math.max(maxX, bx + bw);
    maxY = Math.max(maxY, by + bh);
  };
  for (let i = 0; i < run.glyphs.length; i++) {
    const glyph = run.glyphs[i];
    const pos = run.positions[i];
    const gx = x + pos.xOffset * scale;
    const gy = baseline - pos.yOffset * scale;
    const path = glyph.path.scale(scale, -scale).translate(gx, gy);
    if (path.commands.length > 0) {
      const box = path.bbox;
      grow(box.minX, box.minY, box.maxX - box.minX, box.maxY - box.minY);
      glyphs.push(`<path d="${path.toSVG()}" fill="${fill}"/>`);
    }
    x += pos.xAdvance * scale + TRACKING * EM;
  }
  const stampSize = STAMP * EM;
  const stampX = x - STAMP_PULL * EM;
  const stampY = (EM - stampSize) / 2 + STAMP_DROP * EM;
  grow(stampX, stampY, stampSize, stampSize);
  const pad = 16;
  const vx = r2(minX - pad);
  const vy = r2(minY - pad);
  const vw = r2(maxX - minX + pad * 2);
  const vh = r2(maxY - minY + pad * 2);
  const plate = background ? `<rect x="${vx}" y="${vy}" width="${vw}" height="${vh}" fill="${background}"/>` : "";
  const mark = `<svg x="${r2(stampX)}" y="${r2(stampY)}" width="${r2(stampSize)}" height="${r2(stampSize)}" viewBox="${TIGHT.x} ${TIGHT.y} ${TIGHT.w} ${TIGHT.h}" overflow="visible">
    ${stampDefs()}
    ${stampBody(stamp)}
  </svg>`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${vx} ${vy} ${vw} ${vh}">
  ${plate}
  ${mark}
  ${glyphs.join("\n  ")}
</svg>`;
  return { svg, width: vw };
}

function glyphRun(font, text, pixelSize) {
  const run = font.layout(text);
  const scale = pixelSize / font.unitsPerEm;
  const tracking = TRACKING * pixelSize;
  let x = 0;
  const commands = [];
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (let i = 0; i < run.glyphs.length; i++) {
    const glyph = run.glyphs[i];
    const pos = run.positions[i];
    const path = glyph.path.scale(scale, -scale).translate(x + pos.xOffset * scale, -pos.yOffset * scale);
    if (path.commands.length > 0) {
      const box = path.bbox;
      minX = Math.min(minX, box.minX);
      minY = Math.min(minY, box.minY);
      maxX = Math.max(maxX, box.maxX);
      maxY = Math.max(maxY, box.maxY);
      commands.push(path.toSVG());
    }
    x += pos.xAdvance * scale + tracking;
  }
  return { commands, minX, minY, maxX, maxY };
}

function placeLine(run, top, fill) {
  const x = (120 - (run.maxX - run.minX)) / 2 - run.minX;
  const y = top - run.minY;
  return run.commands
    .map((d) => `<path d="${d}" transform="translate(${r2(x)} ${r2(y)})" fill="${fill}"/>`)
    .join("\n  ");
}

// Square consent-screen mark: the name is readable at 120px, and the stamp is only the accent.
function oauthSvg(font) {
  const probe = glyphRun(font, "Checker", 100);
  const pixelSize = 100 * (100 / (probe.maxX - probe.minX));
  const vibe = glyphRun(font, "Vibe", pixelSize);
  const checker = glyphRun(font, "Checker", pixelSize);
  const gap = 2;
  const stampSize = 22;
  const stampGap = 5;
  const block = vibe.maxY - vibe.minY + gap + (checker.maxY - checker.minY) + stampGap + stampSize;
  let top = (120 - block) / 2;
  const vibePaths = placeLine(vibe, top, INK);
  top += vibe.maxY - vibe.minY + gap;
  const checkerPaths = placeLine(checker, top, INK);
  top += checker.maxY - checker.minY + stampGap;
  const { x, y, w, h } = TIGHT;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">
  <rect width="120" height="120" fill="${PAPER}"/>
  ${vibePaths}
  ${checkerPaths}
  <svg x="${r2((120 - stampSize) / 2)}" y="${r2(top)}" width="${stampSize}" height="${stampSize}" viewBox="${x} ${y} ${w} ${h}">
    ${stampDefs()}
    ${stampBody(MAGENTA)}
  </svg>
</svg>`;
}

function raster(svg, width, background) {
  const rendered = new Resvg(svg, {
    fitTo: { mode: "width", value: width },
    background,
    shapeRendering: 2,
    font: { loadSystemFonts: false },
  }).render();
  return { png: rendered.asPng(), width: rendered.width, height: rendered.height, pixels: rendered.pixels };
}

function minAlpha(pixels) {
  let min = 255;
  for (let i = 3; i < pixels.length; i += 4) if (pixels[i] < min) min = pixels[i];
  return min;
}

function pngChunk(type, data) {
  const name = Buffer.from(type);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(Buffer.concat([name, data])) >>> 0);
  return Buffer.concat([length, name, data, checksum]);
}

function opaquePng(pixels, width, height) {
  const raw = Buffer.alloc((width * 3 + 1) * height);
  let offset = 0;
  for (let y = 0; y < height; y++) {
    raw[offset++] = 0;
    const row = y * width * 4;
    for (let x = 0; x < width; x++) {
      const index = row + x * 4;
      raw[offset++] = pixels[index];
      raw[offset++] = pixels[index + 1];
      raw[offset++] = pixels[index + 2];
    }
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8;
  header[9] = 2;
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    pngChunk("IHDR", header),
    pngChunk("IDAT", deflateSync(raw)),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

async function writeAssets() {
  prepareFont();
  const font = openSync(fontFile);
  await mkdir(join(brand, "google"), { recursive: true });

  const icons = [
    ["icon-magenta-cream", MAGENTA, CREAM],
    ["icon-paper-magenta", PAPER, MAGENTA],
    ["icon-night-cream", NIGHT, CREAM],
    ["icon-night-magenta", NIGHT, MAGENTA_500],
    ["icon-lime-ink", LIME, INK],
    ["icon-royal-cream", ROYAL, CREAM],
  ];
  const iconSources = new Map();
  for (const [name, field, mark] of icons) {
    const svg = iconSvg(field, mark);
    iconSources.set(name, svg);
    await writeFile(join(brand, `${name}.svg`), svg);
    const image = raster(svg, 1024);
    if (image.width !== 1024 || image.height !== 1024) throw new Error(`${name} is not 1024 square.`);
    await writeFile(join(brand, `${name}.png`), image.png);
  }

  for (const [name, color] of [
    ["stamp-magenta", MAGENTA],
    ["stamp-cream", CREAM],
    ["stamp-ink", INK],
    ["stamp-lime", LIME],
  ]) {
    const svg = stampSvg(color);
    await writeFile(join(brand, `${name}.svg`), svg);
    const image = raster(svg, 1024);
    if (image.width !== 1024 || image.height !== 1024) throw new Error(`${name} is not 1024 square.`);
    await writeFile(join(brand, `${name}.png`), image.png);
  }

  const wordmarks = [
    ["wordmark-light", { fill: INK, stamp: MAGENTA, background: PAPER }],
    ["wordmark-dark", { fill: PAPER, stamp: MAGENTA_500, background: NIGHT }],
    ["wordmark-light-transparent", { fill: INK, stamp: MAGENTA }],
    ["wordmark-dark-transparent", { fill: PAPER, stamp: MAGENTA_500 }],
  ];
  for (const [name, colors] of wordmarks) {
    const { svg, width } = wordmark(font, colors);
    await writeFile(join(brand, `${name}.svg`), svg);
    const image = raster(svg, Math.max(1, Math.round((width / EM) * PX_PER_EM)), colors.background);
    if (colors.background && minAlpha(image.pixels) !== 255) throw new Error(`${name} has transparent pixels.`);
    await writeFile(join(brand, `${name}.png`), image.png);
  }

  const googleSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
  <rect width="48" height="48" fill="${PAPER}"/>
  ${iconSvg(MAGENTA, CREAM).replace(/^<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "")}
</svg>`;
  const google = raster(oauthSvg(font), 120, PAPER);
  if (google.width !== 120 || google.height !== 120 || minAlpha(google.pixels) !== 255) {
    throw new Error("Google logo is not an opaque 120 square.");
  }
  const googlePng = opaquePng(google.pixels, google.width, google.height);
  const googlePath = join(brand, "google", "vibechecker-oauth-120.png");
  await writeFile(googlePath, googlePng);
  const bytes = (await stat(googlePath)).size;
  if (googlePng.readUInt32BE(16) !== 120 || googlePng.readUInt32BE(20) !== 120 || googlePng[25] !== 2) {
    throw new Error("Google logo PNG is not 120×120 RGB.");
  }
  if (bytes >= 1_000_000) throw new Error(`Google logo is ${bytes} bytes.`);

  const favicon = raster(iconSources.get("icon-magenta-cream"), 512);
  if (favicon.width !== 512 || favicon.height !== 512) throw new Error("Favicon is not 512 square.");
  await writeFile(join(web, "app", "icon.png"), favicon.png);

  const apple = raster(googleSvg, 180, PAPER);
  if (apple.width !== 180 || apple.height !== 180 || minAlpha(apple.pixels) !== 255) {
    throw new Error("Apple icon is not an opaque 180 square.");
  }
  await writeFile(join(web, "app", "apple-icon.png"), opaquePng(apple.pixels, apple.width, apple.height));

  console.log(
    `ascent ${font.ascent} descent ${font.descent} units ${font.unitsPerEm} baseline ${r2(baselineFromTop(font))}em`,
  );
  console.log(`google logo 120x120 ${bytes} bytes`);
}

await writeAssets();
