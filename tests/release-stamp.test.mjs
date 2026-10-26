import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { stampRelease } from "../scripts/stamp-release.mjs";

test("deploy stamping creates distinct cache keys for each commit", () => {
  const root = mkdtempSync(join(tmpdir(), "trading-release-"));
  try {
    mkdirSync(join(root, "assets", "js"), { recursive: true });
    writeFileSync(join(root, "index.html"),
      '<script type="module" src="./assets/js/app.mjs?v=0.11.0"></script>');
    writeFileSync(join(root, "assets", "js", "app.mjs"),
      'import "./composer.mjs?v=0.11.0";');
    const sha = "1abcdecaf123456789012345678901234567890";
    const changed = stampRelease(root, "0.11.0", sha);
    assert.equal(changed.length, 2);
    assert.match(readFileSync(join(root, "index.html"), "utf8"),
      /app\.mjs\?v=0\.11\.0-1abcdecaf123/);
    assert.match(readFileSync(join(root, "assets","js","app.mjs"),"utf8"),
      /composer\.mjs\?v=0\.11\.0-1abcdecaf123/);
    const build = JSON.parse(readFileSync(join(root, "build.json"), "utf8"));
    assert.equal(build.model_version, "0.11.0");
    assert.equal(build.commit, sha);
    assert.throws(() => stampRelease(root, "0.11.0", "notasha"), /invalid/);
  } finally {
    rmSync(root, {recursive:true,force:true});
  }
});
