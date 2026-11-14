"""Decide whether a validated push must republish the public Pages build.

The fast CI calls this after every check has passed. It compares the commit
served by the public site with the validated commit, so a deployment that a
newer push cancelled is still published by the next successful run, and a
commit that is no longer the tip of main never overwrites newer published data.
Any doubt about the served build resolves towards deploying.
"""
import argparse
import json
import os
import subprocess
import urllib.request

DEPLOY_PATHS = (
    "dist", "package.json", "scripts/stamp-release.mjs",
    ".github/workflows/pages.yml",
)


def git(*args):
    result = subprocess.run(("git", *args), capture_output=True, text=True)
    return result.returncode, result.stdout.strip()


def served_commit(site_url, nonce="", opener=urllib.request.urlopen):
    """Return the commit in the public build.json, or None when unknown."""
    url = site_url.rstrip("/") + "/build.json" + (f"?gate={nonce}" if nonce else "")
    try:
        with opener(url, timeout=20) as response:
            commit = json.load(response).get("commit")
    except (OSError, ValueError, AttributeError):
        return None
    if isinstance(commit, str) and len(commit) == 40 and all(
            c in "0123456789abcdef" for c in commit):
        return commit
    return None


def decide(head, tip, served, run=git):
    """Return (deploy, reason) for a validated head against main and the site."""
    if tip and tip != head:
        return False, f"main advanced to {tip[:12]}; its own workflow publishes it"
    if served is None:
        return True, "public build commit unknown"
    if served == head:
        return False, "public site already serves this commit"
    if run("cat-file", "-e", served + "^{commit}")[0] != 0:
        return True, f"served commit {served[:12]} is not in this history"
    if run("merge-base", "--is-ancestor", head, served)[0] == 0:
        return False, f"public site serves the newer descendant {served[:12]}"
    code, changed = run("diff", "--name-only", served, head, "--", *DEPLOY_PATHS)
    if code != 0:
        return True, "could not compare the served build"
    if changed:
        return True, f"{len(changed.splitlines())} published file(s) differ from {served[:12]}"
    return False, f"no published file differs from {served[:12]}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--branch", default="main")
    options = parser.parse_args()
    fetched = git("fetch", "--no-tags", "--quiet", "origin", options.branch)[0] == 0
    tip = git("rev-parse", "FETCH_HEAD")[1] if fetched else None
    deploy, reason = decide(options.head, tip, served_commit(options.site, options.head))
    print(f"deploy={str(deploy).lower()}: {reason}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"deploy={str(deploy).lower()}\n")


if __name__ == "__main__":
    main()
