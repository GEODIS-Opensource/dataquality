#!/usr/bin/env python3
"""Populate `verifiedUsing` SHA-256 hashes on SBOM packages from PyPI.

Fetches authentic digests from the PyPI JSON API for each package@version and
records a Hash under `verifiedUsing`. Prefers the source distribution (sdist);
falls back to a py3-none-any wheel, then any wheel. Packages that can't be
resolved are left untouched and reported (no fabricated hashes).
"""
import json
import os
import sys
import urllib.request
import urllib.error

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Path to the SPDX JSON. Overridable via SBOM_FILE so the signing pipeline can
# share one location; defaults to <repo>/SBOM/SBOM.spdx30.json regardless of cwd.
PATH = os.environ.get("SBOM_FILE", os.path.join(REPO_ROOT, "SBOM", "SBOM.spdx30.json"))


def pick_digest(files):
    """Return (sha256, filename, kind) for the preferred artifact, or None."""
    sdists = [f for f in files if f.get("packagetype") == "sdist"]
    if sdists:
        f = sdists[0]
        return f["digests"]["sha256"], f["filename"], "sdist"
    wheels = [f for f in files if f.get("packagetype") == "bdist_wheel"]
    universal = [f for f in wheels if f.get("filename", "").endswith("-py3-none-any.whl")]
    chosen = universal or wheels
    if chosen:
        f = chosen[0]
        return f["digests"]["sha256"], f["filename"], "wheel"
    return None


def fetch(name, version):
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    return data.get("urls", [])


def main():
    d = json.load(open(PATH, encoding="utf-8"))
    ok, failed = [], []
    for n in d["@graph"]:
        if n.get("type") != "software_Package":
            continue
        name = n.get("name", "")
        version = n.get("software_packageVersion", "")
        if name.endswith("manifests") or version in ("", "main"):
            continue
        if any(h.get("algorithm") == "sha256" for h in n.get("verifiedUsing", [])):
            ok.append(f"{name}=={version} (already present)")
            continue
        try:
            files = fetch(name, version)
            picked = pick_digest(files)
            if not picked:
                failed.append(f"{name}=={version} (no distributable files)")
                continue
            sha, fname, kind = picked
            n.setdefault("verifiedUsing", []).append({
                "type": "Hash",
                "algorithm": "sha256",
                "hashValue": sha,
            })
            ok.append(f"{name}=={version} [{kind}: {fname}]")
        except urllib.error.HTTPError as e:
            failed.append(f"{name}=={version} (HTTP {e.code})")
        except Exception as e:  # noqa: BLE001
            failed.append(f"{name}=={version} ({e})")

    # newline="\n" so Windows text-mode does not rewrite LF->CRLF and change the
    # bytes that get signed; separators match postprocess_sbom.py for reproducibility.
    with open(PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, indent=2, separators=(",", " : "), ensure_ascii=False)
        f.write("\n")

    print(f"HASHED/OK: {len(ok)}")
    print(f"FAILED: {len(failed)}")
    for line in failed:
        print("  FAIL:", line)


if __name__ == "__main__":
    sys.exit(main())
