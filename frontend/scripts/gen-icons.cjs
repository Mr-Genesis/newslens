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

const FG = "#E4E4E7"; // brackets
const LINE_DIM = "#3F3F46"; // top/bottom story lines
const LINE_MID = "#52525B"; // brighter middle story line
const DOT = "#F97316"; // lens
const BG = "#0C0C0E"; // ground
const MARK_W = 193; // intrinsic painted mark width (bracket outer span incl. stroke)

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
    <path d="M-54 -77 H-89 V77 H-54" fill="none" stroke="${FG}" stroke-width="15" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M54 -77 H89 V77 H54" fill="none" stroke="${FG}" stroke-width="15" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M-55 -29 H-19" stroke="${LINE_DIM}" stroke-width="11" stroke-linecap="round"/>
    <path d="M-68 0 H-29" stroke="${LINE_MID}" stroke-width="11" stroke-linecap="round"/>
    <path d="M-55 29 H-19" stroke="${LINE_DIM}" stroke-width="11" stroke-linecap="round"/>
    <circle cx="0" cy="0" r="21.5" fill="${DOT}"/>
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
