import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const root = fileURLToPath(new URL("../", import.meta.url));
const publicJS = join(root, "dist", "assets", "js");
const pkg = JSON.parse(await readFile(join(root, "package.json"), "utf8"));
const version = pkg.version;
const policy = await readFile(join(publicJS,"policy.mjs"), "utf8");
const index = await readFile(join(root,"dist","index.html"), "utf8");
const templateLoader = await readFile(
  join(publicJS,"ui","templates.mjs"), "utf8");
if (!policy.includes('export const MODEL_VERSION = "' + version + '"'))
  throw new Error("Model version differs from package.json");
if (!index.includes("app.mjs?v=" + version) ||
    !index.includes("styles.css?v=" + version))
  throw new Error("index.html loads a different application version");
if (!templateLoader.includes(".html?v=" + version))
  throw new Error("HTML templates use stale cache version");
const layout = await readFile(join(root, "dist", "templates", "layout.html"), "utf8");
if (!layout.includes("v{{modelVersion}}") ||
    /\bv\d+\.\d+\.\d+\b/.test(layout))
  throw new Error("Footer version must come from the engine; fixed version labels are forbidden");


async function checkDirectory(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      await checkDirectory(path);
      continue;
    }
    if (!entry.name.endsWith(".mjs")) continue;
    const content = await readFile(path, "utf8");
    for (const match of content.matchAll(/\?v=(\d+\.\d+\.\d+)/g))
      if (match[1] !== version)
        throw new Error("ESM version " + match[1] + " incompatible in " + path);
    const result = spawnSync(process.execPath, ["--check", path],
      { stdio: "inherit" });
    if (result.status !== 0) process.exit(result.status || 1);
  }
}
await checkDirectory(publicJS);
console.log("Source versions consistent: " + version);
