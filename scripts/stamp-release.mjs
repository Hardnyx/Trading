import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// Unique cache identity for every published Git commit.
export function stampRelease(root, version, sha) {
  if (!/^\d+\.\d+\.\d+$/.test(version) || !/^[a-f0-9]{7,40}$/i.test(sha))
    throw new Error("Version or commit invalid");
  const suffix = sha.slice(0, 12).toLowerCase();
  const pattern = new RegExp("\\?v=" + version.replaceAll(".", "\\.") +
    "(?![\\w.-])", "g");
  const changed = [];
  function scan(directory) {
    for (const item of readdirSync(directory, { withFileTypes: true })) {
      const file = join(directory, item.name);
      if (item.isDirectory()) { scan(file); continue; }
      if (!item.name.endsWith(".mjs") && !item.name.endsWith(".html")) continue;
      const input = readFileSync(file, "utf8");
      const output = input.replace(pattern, "?v=" + version + "-" + suffix);
      if (output !== input) {
        writeFileSync(file, output, "utf8");
        changed.push(file);
      }
    }
  }
  scan(root);
  if (!changed.some(path => path.endsWith("/index.html")))
    throw new Error("Could not stamp index.html with deployment commit");
  writeFileSync(join(root, "build.json"), JSON.stringify({
    model_version: version,
    commit: sha,
    module_query: "v=" + version + "-" + suffix,
  }, null, 2) + "\n");
  return changed;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const version = JSON.parse(readFileSync(
    new URL("../package.json", import.meta.url), "utf8",
  )).version;
  const sha = process.argv[2];
  const root = fileURLToPath(new URL("../dist", import.meta.url));
  const changed = stampRelease(root, version, sha);
  console.log("Stamped " + changed.length + " files for " +
    version + "-" + sha.slice(0,12) + ".");
}
