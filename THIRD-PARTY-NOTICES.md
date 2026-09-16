# Third-Party Notices

The GDM Self-Service Data Quality Platform ("the Software") is licensed under the
Apache License 2.0 (see [LICENSE](LICENSE)). The Software depends on the third-party
open-source components listed below. Each remains under its own license; those licenses
are not superseded by the Software's license.

This inventory was generated from the project SBOM (`SBOM/SBOM.spdx30.json`). License
identifiers use [SPDX](https://spdx.org/licenses/) expressions. Full license texts are
available in each package's distribution (e.g. under `site-packages/<package>/` after
`pip install`) and at the SPDX links above.

> **Regenerate this file** whenever dependencies change, and keep it in sync with a
> pinned lockfile so the versions here match what actually ships.

## License summary

All dependencies are permissive or weak-copyleft. **No GPL or AGPL (strong copyleft)
components are present.**

| License family | Count | Obligation |
|---|---|---|
| Permissive (MIT, BSD-2/3-Clause, Apache-2.0, PSF-2.0, Python-2.0, ISC, Zlib, MIT-CMU, NCSA, CC0-1.0) | 76 | Attribution only |
| MPL-2.0 (`certifi`) | 1 | File-level copyleft on the component's own files |
| LGPL-3.0-or-later WITH openvpn-openssl-exception (`psycopg2-binary`) | 1 | Weak copyleft; keep unmodified & replaceable |
| CC-BY-SA-3.0 (bundled inside `numpy`) | 1 | Share-alike, applies only to the bundled file |

See the [Weak-copyleft components](#weak-copyleft-components) section for details on
`psycopg2-binary`, `certifi`, and `numpy`.

## Dependencies

| Package | Version | License (SPDX) |
|---|---|---|
| altair | 5.5.0 | BSD-3-Clause |
| annotated-types | 0.8.0 | MIT |
| anyio | 3.7.1 | MIT |
| attrs | 26.1.0 | MIT |
| azure-core | 1.41.0 | MIT |
| azure-identity | 1.25.3 | MIT |
| blinker | 1.9.0 | MIT |
| cachetools | 5.5.2 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| cffi | 2.1.1 | MIT |
| charset-normalizer | 3.5.1 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| cryptography | 50.0.1 | Python-2.0 AND (BSD-3-Clause OR Apache-2.0) |
| databricks-sdk | 0.139.0 | Apache-2.0 |
| databricks-sql-connector | 4.5.0 | Apache-2.0 |
| et-xmlfile | 2.0.0 | MIT |
| fastapi | 0.104.1 | MIT |
| gitdb | 4.0.12 | BSD-3-Clause |
| GitPython | 3.1.62 | BSD-3-Clause |
| google-auth | 2.58.0 | Apache-2.0 |
| h11 | 0.16.0 | MIT |
| idna | 3.19 | BSD-3-Clause |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| lz4 | 4.4.5 | BSD-3-Clause |
| markdown-it-py | 4.2.0 | MIT |
| MarkupSafe | 3.0.3 | BSD-3-Clause |
| mdurl | 0.1.2 | MIT |
| msal | 1.38.0 | MIT |
| msal-extensions | 1.3.1 | MIT |
| narwhals | 2.26.0 | MIT |
| numpy | 2.5.3 | BSD-3-Clause AND BSD-2-Clause AND MIT AND Zlib AND NCSA AND BSD-2-Clause-FreeBSD AND OpenSSL AND BSD-3-Clause-Open-MPI AND CC0-1.0 AND CC-BY-SA-3.0 AND Apache-2.0 |
| oauthlib | 3.3.1 | BSD-3-Clause |
| openpyxl | 3.1.5 | MIT |
| orjson | 3.12.0 | Apache-2.0 |
| pandas | 2.3.3 | BSD-3-Clause AND BSD-2-Clause AND MIT AND TCL AND PSF-2.0 AND Apache-2.0 |
| pandas | 3.0.5 | BSD-3-Clause AND BSD-2-Clause AND TCL AND PSF-2.0 AND MIT AND Apache-2.0 |
| pillow | 10.4.0 | MIT-CMU AND CC0-1.0 |
| protobuf | 5.29.6 | BSD-3-Clause |
| protobuf | 6.33.6 | BSD-3-Clause |
| psycopg2-binary | 2.9.13 | PSF-2.0 AND zlib-acknowledgement AND LGPL-3.0-or-later WITH openvpn-openssl-exception |
| pyarrow | 25.0.1 | Apache-2.0 |
| pyasn1 | 0.6.4 | BSD-3-Clause |
| pyasn1-modules | 0.4.2 | BSD-2-Clause |
| pybreaker | 1.4.1 | BSD-3-Clause |
| pycparser | 3.0 | BSD-3-Clause |
| pydantic | 2.5.0 | MIT |
| pydantic-core | 2.14.1 | MIT |
| pydantic-settings | 2.1.0 | MIT |
| pydeck | 0.9.3 | Apache-2.0 |
| Pygments | 2.21.0 | BSD-3-Clause AND Apache-2.0 |
| PyJWT | 2.14.0 | MIT |
| python-dateutil | 2.9.0.post0 | BSD-3-Clause AND Apache-2.0 |
| python-dotenv | 1.2.3 | BSD-3-Clause |
| python-multipart | 0.0.6 | Apache-2.0 |
| pytz | 2026.3.post1 | MIT |
| referencing | 0.37.0 | MIT |
| requests | 2.34.2 | Apache-2.0 |
| rich | 13.9.4 | MIT |
| rpds-py | 2026.6.3 | MIT |
| six | 1.17.0 | MIT |
| smmap | 5.0.3 | BSD-3-Clause |
| sniffio | 1.3.1 | MIT OR Apache-2.0 |
| starlette | 0.27.0 | BSD-3-Clause |
| streamlit | 1.38.0 | Apache-2.0 |
| tenacity | 8.5.0 | Apache-2.0 |
| thrift | 0.24.0 | Apache-2.0 |
| toml | 0.10.2 | MIT |
| tornado | 6.5.9 | Apache-2.0 |
| trino | 0.336.0 | Apache-2.0 |
| typing-extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2026.4 | Apache-2.0 |
| tzlocal | 5.4.4 | MIT |
| urllib3 | 2.7.0 | MIT AND PSF-2.0 |
| uvicorn | 0.24.0 | BSD-3-Clause |
| watchdog | 4.0.2 | Apache-2.0 |
| zstandard | 0.25.0 | BSD-3-Clause |

> Note: `pandas` and `protobuf` appear at two versions because the backend and frontend
> environments resolved different versions. Pin both environments to a single version to
> remove the duplication.

## Weak-copyleft components

### psycopg2-binary — LGPL-3.0-or-later WITH openvpn-openssl-exception
- **Copyright:** the psycopg authors.
- **Source:** https://github.com/psycopg/psycopg2
- **License text:** https://www.gnu.org/licenses/lgpl-3.0.html and the package's
  `LICENSE` file in its distribution.
- **How the Software complies:** `psycopg2-binary` is used as an unmodified dependency
  installed via `pip`; it is not vendored, modified, or statically linked. End users can
  replace it with another build/version. Under the LGPL, this usage does not place the
  Software's own code under the LGPL. If you ever modify psycopg2 itself, additional LGPL
  obligations (providing your modified source) would apply.

### certifi — MPL-2.0
- **Copyright:** Kenneth Reitz and contributors.
- **Source:** https://github.com/certifi/python-certifi
- **License text:** https://www.mozilla.org/MPL/2.0/
- **How the Software complies:** the MPL-2.0 is a file-level copyleft that applies only to
  modifications of certifi's own files. `certifi` is used unmodified, so no source-
  disclosure obligation attaches to the Software.

### numpy — bundled CC-BY-SA-3.0 file
- **Source:** https://github.com/numpy/numpy
- `numpy` is BSD-3-Clause overall but bundles a small number of files under other terms,
  including one under CC-BY-SA-3.0. This applies only to that bundled file, not to numpy's
  API or to the Software. `numpy` is used as an unmodified `pip` dependency.
