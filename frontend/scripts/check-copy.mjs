#!/usr/bin/env node
/**
 * Copy guard — fails the build if internal jargon reaches user-facing strings.
 * Reads the banned list from docs/content/terminology.json and scans
 * frontend/src for offending text. See docs/content/COPY-GUIDELINES.md.
 *
 * Only inspects user-facing text: quoted string literals + JSX text nodes.
 * Code identifiers, imports, and type declarations are ignored, so a prop
 * named `coherence` or a field `embedding_status` won't trip it.
 *
 * Suppress a single line with a trailing  // copy-lint-ignore
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, relative } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..");
const srcDir = join(here, "..", "src");
const terms = JSON.parse(
  readFileSync(join(repoRoot, "docs", "content", "terminology.json"), "utf8")
).banned;

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const s = statSync(p);
    if (s.isDirectory()) out.push(...walk(p));
    else if (/\.(ts|tsx)$/.test(name)) out.push(p);
  }
  return out;
}

/** Pull the user-facing slices out of one line: quoted strings + JSX text. */
function userFacing(line) {
  const strings = [...line.matchAll(/(['"`])((?:\\.|(?!\1).)*)\1/g)].map((m) => m[2]);
  const jsxText = [...line.matchAll(/>([^<>{}]*[A-Za-z][^<>{}]*)</g)].map((m) => m[1]);
  // Bare prose line = multi-line JSX text (e.g. text sitting alone between <p> … </p>).
  // It has letters but none of the structural code characters.
  const trimmed = line.trim();
  // Require a space → real prose, not a lone identifier like `coherence,`.
  if (trimmed && /\s/.test(trimmed) && /[A-Za-z]/.test(trimmed) && !/[<>{}=;()"'`]/.test(trimmed)) {
    jsxText.push(trimmed);
  }
  return { strings, jsxText, all: [...strings, ...jsxText] };
}

const isCodeLine = (l) =>
  /^\s*(import |export (type|interface|default type)|\/\/|\*|\/\*)/.test(l) ||
  /^\s*(type|interface)\s+\w/.test(l);

const findings = [];
for (const file of walk(srcDir)) {
  const rel = relative(repoRoot, file).replace(/\\/g, "/");
  const lines = readFileSync(file, "utf8").split(/\r?\n/);
  lines.forEach((line, i) => {
    if (isCodeLine(line) || /\/\/\s*copy-lint-ignore/.test(line)) return;
    const seg = userFacing(line);
    for (const b of terms) {
      const haystacks =
        b.scope === "jsx-text" ? seg.jsxText : seg.all;
      let hit = false;
      if (b.kind === "pattern") {
        hit = haystacks.some((s) => s.includes(b.term));
      } else {
        const re = new RegExp(`\\b${b.term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i");
        hit = haystacks.some((s) => re.test(s));
      }
      if (hit) {
        findings.push({
          severity: b.severity, file: rel, line: i + 1,
          term: b.term, text: line.trim().slice(0, 100), use: b.useInstead,
        });
      }
    }
  });
}

const errors = findings.filter((f) => f.severity === "error");
const warns = findings.filter((f) => f.severity === "warn");

for (const f of [...errors, ...warns]) {
  const tag = f.severity === "error" ? "ERROR" : "warn ";
  console.log(`${tag}  ${f.file}:${f.line}  "${f.term}" → ${f.use}`);
  console.log(`        ${f.text}`);
}

console.log(
  `\ncopy-lint: ${errors.length} error(s), ${warns.length} warning(s) across user-facing strings.`
);
if (errors.length) {
  console.log("Fix the ERROR lines (see docs/content/COPY-GUIDELINES.md) or run with care.");
  process.exit(1);
}
