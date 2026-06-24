#!/usr/bin/env node
/**
 * Generates all raster app icons from the NewsLens mark ( [ ● ] ) using sharp.
 * Web: src/app/icon.png, src/app/apple-icon.png, public/icons/icon-192/512.png
 * Android: mipmap density folders -> ic_launcher, ic_launcher_round, ic_launcher_foreground
 * Android splash: drawable splash.png (regenerated at each file's existing size)
 *
 * Re-run after changing the mark:  node scripts/gen-icons.cjs
 */
const fs = require("fs");
const path = require("path");
const sharp = require("sharp");

const FG = "#E4E4E7"; // "bar" — brackets + bright middle line
const GHOST = "#3F3F46"; // "ghost" — dim top/bottom lines
const DOT = "#F97316"; // lens
const BG = "#0C0C0E"; // ground
const MARK_W = 61; // intrinsic painted mark width (bracket outer span incl. stroke, units of 100)

/** Build an SVG string of the mark on a chosen ground. */
function svg({ w, h = w, frac = 0.62, ground = "rounded", radiusFrac = 0.16 }) {
  const min = Math.min(w, h);
  const k = (frac * min) / MARK_W;
  let bg = "";
  if (ground === "rounded")
    bg = `<rect width="${w}" height="${h}" rx="${Math.round(min * radiusFrac)}" fill="${BG}"/>`;
  else if (ground === "square") bg = `<rect width="${w}" height="${h}" fill="${BG}"/>`;
  else if (ground === "circle")
    bg = `<circle cx="${w / 2}" cy="${h / 2}" r="${min / 2}" fill="${BG}"/>`;
  // ground === "none" → transparent (adaptive foreground)
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
  ${bg}
  <g transform="translate(${w / 2},${h / 2}) scale(${k})">
    <path d="M-15 -24 H-28 V24 H-15" fill="none" stroke="${FG}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M15 -24 H28 V24 H15" fill="none" stroke="${FG}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
    <line x1="-17" y1="-9" x2="-6" y2="-9" stroke="${GHOST}" stroke-width="4" stroke-linecap="round"/>
    <line x1="-21" y1="0" x2="-7" y2="0" stroke="${FG}" stroke-width="4" stroke-linecap="round"/>
    <line x1="-17" y1="9" x2="-6" y2="9" stroke="${GHOST}" stroke-width="4" stroke-linecap="round"/>
    <circle cx="0" cy="0" r="7" fill="${DOT}"/>
  </g>
</svg>`;
}

async function write(file, svgStr) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  await sharp(Buffer.from(svgStr)).png().toFile(file);
  console.log("✓", path.relative(process.cwd(), file));
}

function writeSvg(file, svgStr) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, svgStr + "\n");
  console.log("✓", path.relative(process.cwd(), file));
}

const ROOT = path.resolve(__dirname, "..");
const RES = path.join(ROOT, "android/app/src/main/res");

const DENSITIES = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 };

(async () => {
  // ── Web ──
  await write(path.join(ROOT, "src/app/icon.png"), svg({ w: 512, frac: 0.62, ground: "rounded" }));
  await write(path.join(ROOT, "src/app/apple-icon.png"), svg({ w: 180, frac: 0.62, ground: "square" }));
  await write(path.join(ROOT, "public/icons/icon-192.png"), svg({ w: 192, frac: 0.5, ground: "square" }));
  await write(path.join(ROOT, "public/icons/icon-512.png"), svg({ w: 512, frac: 0.5, ground: "square" }));
  writeSvg(path.join(ROOT, "public/favicon.svg"), svg({ w: 64, frac: 0.62, ground: "rounded", radiusFrac: 0.19 }));

  // ── @capacitor/assets sources (1024²) — keep on the bracket mark so a future
  //    `npx @capacitor/assets generate` can't revert the launcher to another mark. ──
  await write(path.join(ROOT, "assets/icon-only.png"), svg({ w: 1024, frac: 0.6, ground: "square" }));
  await write(path.join(ROOT, "assets/icon-foreground.png"), svg({ w: 1024, frac: 0.5, ground: "none" }));
  await write(path.join(ROOT, "assets/logo.png"), svg({ w: 1024, frac: 0.6, ground: "square" }));

  // ── Android launcher ──
  for (const [d, m] of Object.entries(DENSITIES)) {
    const legacy = Math.round(48 * m); // 48,72,96,144,192
    const fg = Math.round(108 * m); // 108,162,216,324,432
    await write(path.join(RES, `mipmap-${d}/ic_launcher.png`), svg({ w: legacy, frac: 0.66, ground: "rounded" }));
    await write(path.join(RES, `mipmap-${d}/ic_launcher_round.png`), svg({ w: legacy, frac: 0.6, ground: "circle" }));
    await write(path.join(RES, `mipmap-${d}/ic_launcher_foreground.png`), svg({ w: fg, frac: 0.52, ground: "none" }));
  }

  // ── Android splash (regenerate at each file's existing dimensions) ──
  const splashFiles = [];
  for (const name of fs.readdirSync(RES)) {
    const p = path.join(RES, name, "splash.png");
    if (fs.existsSync(p)) splashFiles.push(p);
  }
  for (const p of splashFiles) {
    const meta = await sharp(p).metadata();
    await write(p, svg({ w: meta.width, h: meta.height, frac: 0.4, ground: "square" }));
  }

  console.log("\nAll icons generated.");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
