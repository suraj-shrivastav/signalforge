import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const RULES = [
  { rule: "hex-color", re: /#[0-9a-fA-F]{3,8}\b/ },
  { rule: "arbitrary-value", re: /\b[a-z-]+-\[[^\]]+\]/ },
  { rule: "inline-style", re: /\bstyle=/ },
];
const EXT = /\.(ts|tsx|css)$/;

function walk(dir, out) {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules") continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, out);
    // opengraph-image files render to PNG with Satori, which needs inline styles and
    // literal colours; they are not themed UI.
    else if (
      EXT.test(name) &&
      name !== "globals.css" &&
      !name.startsWith("opengraph-image")
    )
      out.push(full);
  }
}

export function checkTokens(rootDir) {
  const src = join(rootDir, "src");
  const files = [];
  try {
    walk(src, files);
  } catch {
    return [];
  }
  const found = [];
  for (const file of files) {
    readFileSync(file, "utf8")
      .split("\n")
      .forEach((text, i) => {
        for (const { rule, re } of RULES) {
          if (re.test(text)) found.push({ file, line: i + 1, rule });
        }
      });
  }
  return found;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = process.cwd();
  const found = checkTokens(root);
  if (found.length) {
    console.error("Token violations:");
    for (const v of found) {
      console.error(`  ${relative(root, v.file)}:${v.line}  ${v.rule}`);
    }
    process.exit(1);
  }
  console.log("check-tokens: ok");
}
