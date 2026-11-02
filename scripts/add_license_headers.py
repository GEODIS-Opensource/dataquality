#!/usr/bin/env python3
"""Add the Apache-2.0 license header to source files that don't already have one.

Usage:
    python scripts/add_license_headers.py [--check] [--year YEAR] [--holder "HOLDER"]

    --check   Report files missing a header and exit non-zero (for CI); make no changes.
    --year    Copyright year to insert (default: current year).
    --holder  Copyright holder (default: empty).

Skips vendored/old directories and anything already containing "Licensed under the
Apache License". A shebang line, if present, is preserved as the first line.
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

# Directories that should not receive headers.
EXCLUDE_DIRS = {
    ".git", "__pycache__", ".sonar", "SBOM", "scripts",
    "frontend_old",  # legacy code slated for removal
}

# File extensions to process, mapped to their comment style.
LINE_COMMENT = {".py": "#"}

HEADER_LINES = [
    "Copyright {year} {holder}",
    "",
    'Licensed under the Apache License, Version 2.0 (the "License");',
    "you may not use this file except in compliance with the License.",
    "You may obtain a copy of the License at",
    "",
    "    http://www.apache.org/licenses/LICENSE-2.0",
    "",
    "Unless required by applicable law or agreed to in writing, software",
    'distributed under the License is distributed on an "AS IS" BASIS,',
    "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.",
    "See the License for the specific language governing permissions and",
    "limitations under the License.",
]

MARKER = "Licensed under the Apache License"


def render_header(comment: str, year: int, holder: str) -> str:
    out = []
    for line in HEADER_LINES:
        text = line.format(year=year, holder=holder)
        out.append(f"{comment} {text}".rstrip() if text else comment)
    return "\n".join(out) + "\n"


def iter_source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in LINE_COMMENT:
            continue
        if any(part in EXCLUDE_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def has_header(text: str) -> bool:
    return MARKER in text[:1000]


def add_header(path: Path, root: Path, comment: str, year: int, holder: str) -> None:
    # Keep the write target constrained to the repository, even if the file
    # tree changes between discovery and modification.
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError(f"refusing to write outside repository: {path}")

    # utf-8-sig drops a leading BOM; otherwise it ends up after the header and
    # Python rejects it as an invalid character.
    original = path.read_text(encoding="utf-8-sig")
    header = render_header(comment, year, holder)
    if original.startswith("#!"):
        shebang, _, rest = original.partition("\n")
        new = f"{shebang}\n{header}\n{rest}"
    else:
        new = f"{header}\n{original}"
    # Use the validated path directly and refuse symlinks where supported, so
    # a replacement between validation and writing cannot redirect the output.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(os.fspath(path), flags, 0o644)
    try:
        output = os.fdopen(fd, "w", encoding="utf-8", newline="")
        fd = -1
        with output:
            output.write(new)
    finally:
        if fd != -1:
            os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--year", type=int, default=datetime.date.today().year)
    parser.add_argument("--holder", default="")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    missing = []
    for path in iter_source_files(root):
        comment = LINE_COMMENT[path.suffix]
        text = path.read_text(encoding="utf-8-sig")
        if has_header(text):
            continue
        if args.check:
            missing.append(path.relative_to(root))
        else:
            add_header(path, root, comment, args.year, args.holder)
            print(f"added header: {path.relative_to(root)}")

    if args.check and missing:
        print("Missing Apache-2.0 header in:")
        for m in missing:
            print(f"  {m}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
