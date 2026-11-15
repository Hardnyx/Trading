"""Independent RFC 3161 timestamps for prospective evidence.

Each run lists every evidence file that is new or changed since the last
stamp, writes a manifest of their SHA-256, and asks independent public time
stamping authorities to sign the manifest hash. A Git commit date is set by
whoever commits; a signed RFC 3161 token is not, and anyone can check it with
OpenSSL. The token proves the files existed no later than the signed time; it
says nothing about when they were first created or about their correctness.
"""
import argparse
import hashlib
import json
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/timestamps"
EVIDENCE = ("data/confirmatory", "data/distributions", "data/forecasts", "data/fund", "data/holdings",
            "data/risk-forecasts", "data/signal-validation", "data/simulator-validation", "data/snapshots",
            "data/validation-reviews", "data/volatility-parameters")
AUTHORITIES = {
    "digicert": {"url": "http://timestamp.digicert.com", "ca": "system"},
    "sectigo": {"url": "http://timestamp.sectigo.com", "ca": "system"},
    "freetsa": {"url": "https://freetsa.org/tsr", "ca": "data/timestamps/freetsa-cacert.pem"},
}
FREETSA_CA_SHA256 = "2151b61137ffa86bf664691ba67e7da0b19f98c758e3d228d5d8ebf27e044438"
SYSTEM_CA = "/etc/ssl/certs/ca-certificates.crt"
MINIMUM_TOKENS = 2


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def evidence_files(root=ROOT):
    files = []
    for folder in EVIDENCE:
        base = root / folder
        if base.exists():
            files += [p for p in base.rglob("*") if p.is_file()]
    return sorted(files)


def stamped_index(root=ROOT):
    """Latest stamped hash per path, rebuilt from every manifest."""
    index = {}
    for manifest in sorted((root / "data/timestamps").glob("*.manifest.json")):
        for row in json.loads(manifest.read_text(encoding="utf-8"))["files"]:
            index[row["path"]] = row["sha256"]
    return index


def pending(root=ROOT):
    index = stamped_index(root)
    rows = []
    for path in evidence_files(root):
        rel = path.relative_to(root).as_posix()
        digest = sha256(path)
        if index.get(rel) != digest:
            rows.append({"path": rel, "sha256": digest})
    return rows


def query(data_path, out_path):
    subprocess.run(["openssl", "ts", "-query", "-data", str(data_path), "-sha256", "-cert", "-out", str(out_path)],
                   check=True, capture_output=True)


def request_token(url, tsq_bytes, timeout=30):
    req = urllib.request.Request(url, data=tsq_bytes, headers={"Content-Type": "application/timestamp-query"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def ca_file(name, root=ROOT):
    ca = AUTHORITIES[name]["ca"]
    return SYSTEM_CA if ca == "system" else str(root / ca)


def verify_token(manifest_path, token_path, name, root=ROOT):
    result = subprocess.run(["openssl", "ts", "-verify", "-data", str(manifest_path), "-in", str(token_path),
                             "-CAfile", ca_file(name, root)], capture_output=True, text=True)
    return result.returncode == 0 and "Verification: OK" in result.stdout


def token_time(token_path):
    text = subprocess.run(["openssl", "ts", "-reply", "-in", str(token_path), "-text"],
                          capture_output=True, text=True, check=True).stdout
    return next((line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("Time stamp:")), None)


def stamp(root=ROOT, now=None):
    rows = pending(root)
    if not rows:
        return {"stamped": 0}
    now = now or datetime.now(timezone.utc)
    name = now.strftime("%Y-%m-%dT%H%M%SZ")
    out = root / "data/timestamps"
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / f"{name}.manifest.json"
    manifest.write_text(json.dumps({"schema": "evidence-timestamp-manifest-v1", "created_utc": now.isoformat(),
                                    "files": rows}, indent=1) + "\n", encoding="utf-8")
    tokens = {}
    with tempfile.TemporaryDirectory() as tmp:
        tsq = Path(tmp) / "q.tsq"
        query(manifest, tsq)
        for authority, spec in AUTHORITIES.items():
            token = out / f"{name}.{authority}.tsr"
            try:
                token.write_bytes(request_token(spec["url"], tsq.read_bytes()))
                if verify_token(manifest, token, authority, root):
                    tokens[authority] = token_time(token)
                else:
                    token.unlink()
            except Exception as error:  # an authority being down must not lose the others
                tokens[authority + "_error"] = f"{type(error).__name__}: {str(error)[:120]}"
                if token.exists():
                    token.unlink()
    valid = [k for k in tokens if not k.endswith("_error")]
    if len(valid) < MINIMUM_TOKENS:
        for leftover in out.glob(f"{name}.*"):
            leftover.unlink()
        raise RuntimeError(f"Only {len(valid)} valid timestamp tokens: {tokens}")
    return {"stamped": len(rows), "manifest": manifest.relative_to(root).as_posix(), "tokens": tokens}


def verify(root=ROOT):
    """Every manifest keeps at least two tokens that OpenSSL verifies against its bytes.

    Files changed after their last stamp are not errors: the next run stamps
    the new version, and the manifests keep every earlier one.
    """
    ca = root / AUTHORITIES["freetsa"]["ca"]
    if sha256(ca) != FREETSA_CA_SHA256:
        raise ValueError("FreeTSA CA certificate changed")
    manifests = sorted((root / "data/timestamps").glob("*.manifest.json"))
    for manifest in manifests:
        stem = manifest.name[:-len(".manifest.json")]
        ok = [a for a in AUTHORITIES if (manifest.parent / f"{stem}.{a}.tsr").exists()
              and verify_token(manifest, manifest.parent / f"{stem}.{a}.tsr", a, root)]
        if len(ok) < MINIMUM_TOKENS:
            raise ValueError(f"{manifest.name}: only {len(ok)} valid tokens")
    return {"manifests": len(manifests), "files_with_a_stamp": len(stamped_index(root)), "pending": len(pending(root))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    options = parser.parse_args()
    print(json.dumps(verify() if options.verify else stamp(), indent=1))


if __name__ == "__main__":
    main()
