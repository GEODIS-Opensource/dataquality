#!/usr/bin/env bash
#
# Post-process and sign the GDM SS SBOM.
#
# The scripts live in scripts/; the SBOM data (SPDX JSON, signatures, keys)
# lives in SBOM/. Run this AFTER SonarQube generates SBOM/SBOM.spdx30.json. It:
#   1. re-injects the PURL / external identifier / manifest SHA-256 hash and
#      normalises licenses (postprocess_sbom.py), then
#   2. adds per-dependency SHA-256 hashes from PyPI (add_sbom_hashes.py), then
#   3. adds per-dependency copyright text from the PyPI distributions' license
#      files (add_sbom_copyrights.py), then
#   4. signs the resulting bytes with Ed25519 and writes a detached signature
#      plus the public key, then
#   5. verifies the signature.
#
# Ed25519 signatures are deterministic (RFC 8032): the same key over the same
# post-processed bytes always yields the same .sig, so CI reproduces the repo's
# signature exactly. All python steps are idempotent — re-running them on an
# already-corrected SBOM leaves the bytes (and therefore the signature) unchanged.
#
# Environment variables (all optional):
#   SBOM_FILE          SPDX JSON path        (default: <repo>/SBOM/SBOM.spdx30.json)
#   SBOM_SIGNING_KEY   Ed25519 private key   (default: <repo>/SBOM/sbom-signing-key.pem)
#   SBOM_PUBLIC_KEY    public key output     (default: <repo>/SBOM/sbom-signing-key.pub.pem)
# The signing key is git-ignored; in CI, materialise it from a secret and point
# SBOM_SIGNING_KEY at it (see .github/workflows/sbom-sign.yml).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SBOM_DIR="$REPO_ROOT/SBOM"

SBOM_FILE="${SBOM_FILE:-$SBOM_DIR/SBOM.spdx30.json}"
SIGNING_KEY="${SBOM_SIGNING_KEY:-$SBOM_DIR/sbom-signing-key.pem}"
PUBLIC_KEY="${SBOM_PUBLIC_KEY:-$SBOM_DIR/sbom-signing-key.pub.pem}"

# Prefer python3; fall back to python (e.g. on Windows where only `python` exists).
if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo ">> ERROR: no python3 or python interpreter found on PATH" >&2
  exit 1
fi

export SBOM_FILE

echo ">> Post-processing SBOM (PURL + external identifier + manifest hash + licenses)"
"$PYTHON" "$SCRIPT_DIR/postprocess_sbom.py"

echo ">> Adding per-dependency SHA-256 hashes from PyPI"
"$PYTHON" "$SCRIPT_DIR/add_sbom_hashes.py"

echo ">> Adding per-dependency copyright text from PyPI license files"
"$PYTHON" "$SCRIPT_DIR/add_sbom_copyrights.py"

if [[ ! -f "$SIGNING_KEY" ]]; then
  echo ">> No signing key at $SIGNING_KEY"
  echo "   Generating a new Ed25519 key. This is a DEV key, not an org-trusted"
  echo "   signing identity — use a managed key/HSM for release SBOMs."
  openssl genpkey -algorithm ed25519 -out "$SIGNING_KEY"
fi

# Publish the public key derived from whatever private key we signed with.
# Strip CR: Git-for-Windows' OpenSSL writes PEM with CRLF, which would make the
# committed (LF) key look changed on every local run.
openssl pkey -in "$SIGNING_KEY" -pubout | tr -d '\r' > "$PUBLIC_KEY"

echo ">> Signing $SBOM_FILE with Ed25519"
openssl pkeyutl -sign -inkey "$SIGNING_KEY" -rawin -in "$SBOM_FILE" -out "$SBOM_FILE.sig"
openssl base64 -A -in "$SBOM_FILE.sig" -out "$SBOM_FILE.sig.b64"

echo ">> Verifying signature"
openssl pkeyutl -verify -pubin -inkey "$PUBLIC_KEY" -rawin -in "$SBOM_FILE" -sigfile "$SBOM_FILE.sig"

echo ">> Done:"
echo "   $SBOM_FILE"
echo "   $SBOM_FILE.sig"
echo "   $SBOM_FILE.sig.b64"
echo "   $PUBLIC_KEY"
