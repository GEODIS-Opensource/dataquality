#!/usr/bin/env python3
"""Re-apply GDM SS SBOM enrichments after SonarQube regenerates the SPDX document.

SonarQube overwrites SBOM/SBOM.spdx30.json on every scan, dropping the manual
edits that satisfy the SBOM quality checks. This script re-injects, into the
document's root ``software_Package``:

  * ``software_packageUrl`` + ``externalIdentifier`` (packageUrl) + ``externalRef`` (vcs)
  * ``verifiedUsing`` — a SHA-256 over the dependency manifests
  * ``software_copyrightText`` — the project copyright (matches LICENSE/NOTICE)

Every dependency ``software_Package`` also gets a ``software_packageUrl`` and a
``packageUrl`` ``externalIdentifier``. SonarQube only records the PURL as an
``externalRef`` locator, which SBOM quality checks do not count as a package
identifier. The existing ``pkg:`` locator is reused; if a package has none, a
``pkg:pypi`` PURL is built from its name and version.

It also normalises the license relationships so no package reports NOASSERTION:

  * the root project is pinned to ``Apache-2.0`` (matches the repo LICENSE) for
    both its declared and concluded license, and
  * every dependency whose declared license SonarQube left as NOASSERTION is
    filled from the license it *concluded* (and vice-versa), reusing the
    existing ``simplelicensing_LicenseExpression`` elements. No license is
    invented — a dependency with no determinable license on either side is left
    untouched.

The root package is discovered dynamically via ``SpdxDocument.rootElement`` so the
random document UUID in the spdxId does not need to be hard-coded.

Output is written with LF newlines and a fixed key/value separator so the bytes
are reproducible across platforms — this keeps the detached Ed25519 signature
(which is itself deterministic) identical in CI and locally.

Configuration via environment variables (all optional):
  SBOM_FILE             path to the SPDX JSON (default: SBOM/SBOM.spdx30.json)
  SBOM_PURL             package URL to record (default: the GEODIS-Opensource repo PURL)
  SBOM_MANIFESTS        space-separated manifest paths, relative to repo root
  SBOM_PROJECT_LICENSE  SPDX license id for the root project (default: Apache-2.0)
  SBOM_PROJECT_COPYRIGHT  copyright text for the root project
                        (default: "Copyright 2026", as in LICENSE/NOTICE)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_PURL = "pkg:github/geodis-opensource/dataquality@main"
DEFAULT_MANIFESTS = "backend/requirements.txt frontend/requirements.txt"
DEFAULT_PROJECT_LICENSE = "Apache-2.0"
DEFAULT_PROJECT_COPYRIGHT = "Copyright 2026"

# License expressions that carry no usable license information; treated as
# "missing" so they can be back-filled from the other side of the relationship.
_NO_LICENSE = {"NOASSERTION", "NONE", "NoAssertion", None}


def _spdx_namespace(spdx_id: str) -> str:
    """Return the document namespace prefix from any element spdxId.

    ``https://.../<uuid>/SPDXRef-gnrtd1`` -> ``https://.../<uuid>/`` so newly
    minted elements share the document's random UUID namespace.
    """
    return spdx_id.rsplit("/", 1)[0] + "/"


def _package_purl(pkg: dict) -> str | None:
    """Return the package's PURL from its externalRef locators, else build a pypi one.

    PyPI PURL names are lower-cased with runs of ``-_.`` collapsed to ``-``
    (PEP 503 normalisation, as required by the purl-spec pypi type).
    """
    for ref in pkg.get("externalRef", []):
        for locator in ref.get("locator", []):
            if locator.startswith("pkg:"):
                return locator
    name = pkg.get("name")
    version = pkg.get("software_packageVersion")
    if not name or not version:
        return None
    return f"pkg:pypi/{re.sub(r'[-_.]+', '-', name).lower()}@{version}"


def enrich_package_identifiers(graph: list, root_id: str) -> tuple[int, list[str]]:
    """Set software_packageUrl + a packageUrl externalIdentifier on every dependency.

    Returns (#packages identified, names of packages with no derivable PURL).
    The root package is skipped; main() sets its identifiers explicitly.
    """
    identified, missing = 0, []
    for pkg in graph:
        if pkg.get("type") != "software_Package" or pkg.get("spdxId") == root_id:
            continue
        purl = _package_purl(pkg)
        if purl is None:
            missing.append(pkg.get("name", pkg.get("spdxId")))
            continue
        pkg["software_packageUrl"] = purl
        others = [
            i
            for i in pkg.get("externalIdentifier", [])
            if i.get("externalIdentifierType") != "packageUrl"
        ]
        pkg["externalIdentifier"] = [
            {
                "type": "ExternalIdentifier",
                "externalIdentifierType": "packageUrl",
                "identifier": purl,
            }
        ] + others
        identified += 1
    return identified, missing


def enrich_licenses(graph: list, root_id: str, project_license: str) -> int:
    """Remove NOASSERTION licenses from every package. Returns #relationships changed.

    The root project is pinned to ``project_license`` on both sides. For every
    other package, a NOASSERTION declared/concluded license is back-filled from
    the opposite side when that side names a real license. Existing license
    expression elements are reused; one is created only if ``project_license``
    is absent from the document.
    """
    namespace = _spdx_namespace(root_id)

    text_to_id: dict[str, str] = {}
    id_to_text: dict[str, str] = {}
    for element in graph:
        if element.get("type") == "simplelicensing_LicenseExpression":
            text = element.get("simplelicensing_licenseExpression")
            id_to_text[element["spdxId"]] = text
            text_to_id.setdefault(text, element["spdxId"])

    def ensure_license(text: str) -> str:
        if text in text_to_id:
            return text_to_id[text]
        slug = "".join(c if c.isalnum() else "-" for c in text).strip("-").lower()
        new_id = f"{namespace}SPDXRef-lic-{slug or 'expr'}"
        existing = {e.get("spdxId") for e in graph}
        candidate, n = new_id, 1
        while candidate in existing:
            candidate, n = f"{new_id}-{n}", n + 1
        graph.append(
            {
                "spdxId": candidate,
                "type": "simplelicensing_LicenseExpression",
                "simplelicensing_licenseExpression": text,
                "creationInfo": "_:creationInfo_0",
            }
        )
        text_to_id[text] = candidate
        id_to_text[candidate] = text
        return candidate

    concluded: dict[str, dict] = {}
    declared: dict[str, dict] = {}
    for element in graph:
        if element.get("type") == "Relationship":
            rel_type = element.get("relationshipType")
            if rel_type == "hasConcludedLicense":
                concluded[element["from"]] = element
            elif rel_type == "hasDeclaredLicense":
                declared[element["from"]] = element

    def rel_text(rel: dict | None) -> str | None:
        if not rel or not rel.get("to"):
            return None
        return id_to_text.get(rel["to"][0])

    package_ids = [e["spdxId"] for e in graph if e.get("type") == "software_Package"]

    changed = 0
    for pid in package_ids:
        concluded_rel = concluded.get(pid)
        declared_rel = declared.get(pid)

        if pid == root_id:
            target = [ensure_license(project_license)]
            for rel in (concluded_rel, declared_rel):
                if rel is not None and rel.get("to") != target:
                    rel["to"] = list(target)
                    changed += 1
            continue

        concluded_missing = rel_text(concluded_rel) in _NO_LICENSE
        declared_missing = rel_text(declared_rel) in _NO_LICENSE
        if declared_rel is not None and declared_missing and not concluded_missing:
            declared_rel["to"] = list(concluded_rel["to"])
            changed += 1
        elif concluded_rel is not None and concluded_missing and not declared_missing:
            concluded_rel["to"] = list(declared_rel["to"])
            changed += 1

    return changed


def main() -> int:
    sbom_file = os.environ.get(
        "SBOM_FILE", os.path.join(REPO_ROOT, "SBOM", "SBOM.spdx30.json")
    )
    purl = os.environ.get("SBOM_PURL", DEFAULT_PURL)
    manifests_rel = os.environ.get("SBOM_MANIFESTS", DEFAULT_MANIFESTS).split()
    manifests = [os.path.join(REPO_ROOT, m) for m in manifests_rel]

    # SHA-256 over the raw bytes of each manifest, concatenated in order.
    # Matches: cat <manifests> | sha256sum
    digest = hashlib.sha256()
    for m in manifests:
        with open(m, "rb") as fh:
            digest.update(fh.read())
    hash_value = digest.hexdigest()

    with open(sbom_file, encoding="utf-8") as fh:
        doc = json.load(fh)

    graph = doc.get("@graph", [])

    root_ids: list[str] = []
    for element in graph:
        if element.get("type") == "SpdxDocument":
            root_ids.extend(element.get("rootElement", []))
    if not root_ids:
        print("ERROR: no SpdxDocument.rootElement found in SBOM", file=sys.stderr)
        return 1
    root_id = root_ids[0]

    pkg = next(
        (
            e
            for e in graph
            if e.get("spdxId") == root_id and e.get("type") == "software_Package"
        ),
        None,
    )
    if pkg is None:
        print(f"ERROR: root software_Package {root_id} not found", file=sys.stderr)
        return 1

    manifest_names = ", ".join(
        os.path.relpath(m, REPO_ROOT).replace("\\", "/") for m in manifests
    )

    pkg["software_copyrightText"] = os.environ.get(
        "SBOM_PROJECT_COPYRIGHT", DEFAULT_PROJECT_COPYRIGHT
    )
    pkg["software_packageUrl"] = purl
    pkg["externalIdentifier"] = [
        {
            "type": "ExternalIdentifier",
            "externalIdentifierType": "packageUrl",
            "identifier": purl,
        }
    ]
    pkg["externalRef"] = [
        {
            "type": "ExternalRef",
            "locator": [purl],
            "externalRefType": "vcs",
        }
    ]
    pkg["verifiedUsing"] = [
        {
            "type": "Hash",
            "algorithm": "sha256",
            "hashValue": hash_value,
            "comment": (
                "SHA-256 over the concatenation of dependency manifests "
                f"{manifest_names}."
            ),
        }
    ]

    identified, unidentified = enrich_package_identifiers(graph, root_id)

    project_license = os.environ.get("SBOM_PROJECT_LICENSE", DEFAULT_PROJECT_LICENSE)
    changed = enrich_licenses(graph, root_id, project_license)

    # newline="\n" so Windows text-mode does not rewrite LF->CRLF and change the
    # bytes we sign. separators keep the SonarQube/Gson-style " : " spacing.
    with open(sbom_file, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False, separators=(",", " : "))
        fh.write("\n")

    print(f"Injected PURL={purl}")
    print(f"Injected sha256={hash_value} into {root_id}")
    print(f"Package identifiers: {identified} dependency package(s) given a PURL")
    for name in unidentified:
        print(f"  WARN: no PURL derivable for {name}")
    print(f"Normalised licenses: {changed} relationship(s) updated (project={project_license})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
