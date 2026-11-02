#!/usr/bin/env python3
"""Populate `software_copyrightText` on SBOM dependency packages from PyPI.

SonarQube leaves `software_copyrightText` empty. For each package@version this
reads the license files shipped in the released distribution on PyPI (the
wheel's ``*.dist-info`` LICENSE/COPYING/NOTICE/AUTHORS files, or the sdist's
top-level ones) and records the ``Copyright ...`` lines found there.

Many projects (typically Apache-2.0 ones) ship only the bare license text and
put their copyright in source-file headers instead. When the license files
yield nothing, the headers of the source files shipped in the wheel are
scanned, skipping tests, vendored directories and files whose header says the
code was taken from another project, so another project's copyright is never
attributed to the package. Statements are ordered by how
many files carry them.

Wheels are read with HTTP range requests (only the zip directory and the
license members are fetched), so large platform wheels are cheap. Packages
with no extractable statement get ``NOASSERTION`` — nothing is invented.
Packages that already carry a real statement are left untouched, so re-runs
are idempotent and don't depend on the network.
"""
import io
import json
import os
import re
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PATH = os.environ.get("SBOM_FILE", os.path.join(REPO_ROOT, "SBOM", "SBOM.spdx30.json"))

NOASSERTION = "NOASSERTION"

# sdists can't be range-read; don't download anything bigger than this.
MAX_SDIST_BYTES = 25 * 1024 * 1024

_LICENSE_NAME = re.compile(r"(licen[cs]e|copying|notice|authors)", re.IGNORECASE)
# Case-sensitive on purpose: a leading "(c)" without a year is a list item in
# license bodies (Apache-2.0 §4(c), MPL-2.0), and lowercase "copyright" is prose.
_COPYRIGHT_LINE = re.compile(r"^\s*(?:Copyright\b|COPYRIGHT\b|©|\([cC]\)\s*\d{4})")
_HAS_YEAR_OR_SYMBOL = re.compile(r"\d{4}|\([cC]\)|©")
# Placeholders from license templates, e.g. Apache-2.0's "Copyright [yyyy] [name ...]".
_TEMPLATE = re.compile(r"[\[{<]\s*(yyyy|year|name of copyright owner|owner)", re.IGNORECASE)
# Copyright of the license *document* itself (GPL/LGPL texts), not of the package.
_LICENSE_DOC_OWNER = re.compile(r"free software foundation", re.IGNORECASE)
# Comment markers in front of a header line: "# ", "// ", "/* ", " * ", "; ".
_COMMENT_PREFIX = re.compile(r"^[#/*;!\s]+")

# Source-header fallback: which wheel members to scan, and how much of each.
_SOURCE_EXT = re.compile(r"\.(py|pyi|pyx|pxd|c|h|cpp|rs)$")
# Tests and bundled third-party code carry other projects' copyrights.
_SKIP_DIR = re.compile(
    r"(^|/)(tests?|testing|_?vendor(ed)?|third_?party|external|deps|libffi[^/]*)/",
    re.IGNORECASE,
)
# Headers that announce code copied in from another project, e.g. cffi's
# "Integrated from the cffi-buildtool project by ... under the following license".
_THIRD_PARTY_HEADER = re.compile(
    r"\b(integrated|vendored|copied|taken|imported|borrowed) from\b"
    r"|under the following licen[cs]e",
    re.IGNORECASE,
)
HEADER_BYTES = 4096
MAX_HEADER_LINES = 10


class _HTTPRangeFile(io.RawIOBase):
    """Seekable read-only file over HTTP Range requests, with a block cache."""

    BLOCK = 64 * 1024

    def __init__(self, url, size):
        self.url, self.size, self.pos, self._blocks = url, size, 0, {}

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=io.SEEK_SET):
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = max(0, base + offset)
        return self.pos

    def _block(self, index):
        if index not in self._blocks:
            start = index * self.BLOCK
            end = min(start + self.BLOCK, self.size) - 1
            req = urllib.request.Request(self.url, headers={"Range": f"bytes={start}-{end}"})
            with urllib.request.urlopen(req, timeout=30) as r:
                self._blocks[index] = r.read()
        return self._blocks[index]

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        out = bytearray()
        while n > 0:
            index, offset = divmod(self.pos, self.BLOCK)
            chunk = self._block(index)[offset:offset + n]
            if not chunk:
                break
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return bytes(out)


def _copyright_lines(text):
    """Yield each real copyright line in ``text``, whitespace/comment-normalised."""
    for raw in text.splitlines():
        line = _COMMENT_PREFIX.sub("", " ".join(raw.split()))
        line = line.removesuffix("*/").rstrip()
        if (
            _COPYRIGHT_LINE.match(line)
            and _HAS_YEAR_OR_SYMBOL.search(line)
            and not _TEMPLATE.search(line)
            and not _LICENSE_DOC_OWNER.search(line)
        ):
            yield line


def extract_copyrights(texts):
    """Return the de-duplicated, ordered real copyright lines from license texts."""
    seen, lines = set(), []
    for text in texts:
        for line in _copyright_lines(text):
            if line not in seen:
                seen.add(line)
                lines.append(line)
    return lines


def extract_header_copyrights(headers):
    """Return copyright lines from source headers, most widespread first.

    Each file counts once per statement; ties keep first-seen order, so the
    result is deterministic for a given distribution.
    """
    counts, first_seen = {}, {}
    for header in headers:
        if _THIRD_PARTY_HEADER.search(header):
            continue
        for line in sorted(set(_copyright_lines(header))):
            counts[line] = counts.get(line, 0) + 1
            first_seen.setdefault(line, len(first_seen))
    ranked = sorted(counts, key=lambda line: (-counts[line], first_seen[line]))
    return ranked[:MAX_HEADER_LINES]


def _wheel_license_texts(url, size):
    with zipfile.ZipFile(_HTTPRangeFile(url, size)) as zf:
        names = [
            n for n in zf.namelist()
            if ".dist-info/" in n and not n.endswith("/")
            and _LICENSE_NAME.search(n.rsplit("/", 1)[-1])
        ]
        return [zf.read(n).decode("utf-8", "replace") for n in names]


def _wheel_source_headers(url, size):
    """Return the first HEADER_BYTES of each first-party source file in a wheel."""
    with zipfile.ZipFile(_HTTPRangeFile(url, size)) as zf:
        names = [
            n for n in zf.namelist()
            if _SOURCE_EXT.search(n) and ".dist-info/" not in n and not _SKIP_DIR.search(n)
        ]
        headers = []
        for n in names:
            with zf.open(n) as fh:
                headers.append(fh.read(HEADER_BYTES).decode("utf-8", "replace"))
        return headers


def _sdist_license_texts(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    texts = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
        for m in tf.getmembers():
            # <pkg>-<ver>/LICENSE or <pkg>-<ver>/LICENSES/x.txt — not test fixtures etc.
            parts = m.name.split("/")
            if m.isfile() and len(parts) <= 3 and _LICENSE_NAME.search(parts[-1]):
                texts.append(tf.extractfile(m).read().decode("utf-8", "replace"))
    return texts


def candidate_distributions(files):
    """Yield (file, kind): the preferred wheel (py3-none-any, else smallest), then a small sdist.

    The sdist is a fallback for wheels whose dist-info ships no copyright line
    (some projects only keep it in the source tree's LICENSE/NOTICE).
    """
    wheels = [f for f in files if f.get("packagetype") == "bdist_wheel"]
    universal = [f for f in wheels if f["filename"].endswith("-py3-none-any.whl")]
    if universal or wheels:
        yield min(universal or wheels, key=lambda f: f.get("size", 0)), "wheel"
    for f in files:
        if f.get("packagetype") == "sdist" and f.get("size", 0) <= MAX_SDIST_BYTES:
            yield f, "sdist"
            break


def fetch_copyright(name, version):
    """Return (copyright text or None, source description)."""
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        files = json.load(r).get("urls", [])
    candidates = list(candidate_distributions(files))
    tried = []
    for dist, kind in candidates:
        if kind == "wheel":
            texts = _wheel_license_texts(dist["url"], dist["size"])
        else:
            texts = _sdist_license_texts(dist["url"])
        lines = extract_copyrights(texts)
        if lines:
            return "\n".join(lines), f"{kind}: {dist['filename']}"
        tried.append(f"{kind}: {dist['filename']}")
    # No license file names a holder: fall back to the shipped source headers.
    for dist, kind in candidates:
        if kind != "wheel":
            continue
        lines = extract_header_copyrights(_wheel_source_headers(dist["url"], dist["size"]))
        if lines:
            return "\n".join(lines), f"source headers in {dist['filename']}"
        tried.append(f"source headers in {dist['filename']}")
    return None, ("no copyright line in " + ", ".join(tried)) if tried else "no usable distribution"


def main():
    d = json.load(open(PATH, encoding="utf-8"))
    found, noassert = [], []
    for n in d["@graph"]:
        if n.get("type") != "software_Package":
            continue
        name = n.get("name", "")
        version = n.get("software_packageVersion", "")
        if name.endswith("manifests") or version in ("", "main"):
            continue
        current = n.get("software_copyrightText") or ""
        if current.strip() and current != NOASSERTION:
            found.append(f"{name}=={version} (already present)")
            continue
        try:
            text, source = fetch_copyright(name, version)
        except (urllib.error.URLError, zipfile.BadZipFile, tarfile.TarError, OSError) as e:
            text, source = None, f"error: {e}"
        if text:
            n["software_copyrightText"] = text
            found.append(f"{name}=={version} [{source}]")
        else:
            n["software_copyrightText"] = NOASSERTION
            noassert.append(f"{name}=={version} ({source})")

    # newline="\n" so Windows text-mode does not rewrite LF->CRLF and change the
    # bytes that get signed; separators match postprocess_sbom.py for reproducibility.
    with open(PATH, "w", encoding="utf-8", newline="\n") as f:
        json.dump(d, f, indent=2, separators=(",", " : "), ensure_ascii=False)
        f.write("\n")

    print(f"COPYRIGHT FOUND: {len(found)}")
    print(f"NOASSERTION: {len(noassert)}")
    for line in noassert:
        print("  NOASSERTION:", line)


if __name__ == "__main__":
    sys.exit(main())
