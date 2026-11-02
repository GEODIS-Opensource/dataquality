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
| Permissive (MIT, BSD-2/3-Clause, Apache-2.0, PSF-2.0, Python-2.0, ISC, Zlib, MIT-CMU, NCSA, CC0-1.0) | 67 | Attribution only |
| MPL-2.0 (`certifi`) | 1 | File-level copyleft on the component's own files |
| LGPL-3.0-or-later WITH openvpn-openssl-exception (`psycopg2-binary`) | 1 | Weak copyleft; keep unmodified & replaceable |
| CC-BY-SA-3.0 (bundled inside `numpy`) | 1 | Share-alike, applies only to the bundled file |

See the [Weak-copyleft components](#weak-copyleft-components) section for details on
`psycopg2-binary`, `certifi`, and `numpy`.

## Dependencies

| Package | Version | License (SPDX) |
|---|---|---|
| altair | 6.3.0 | BSD-3-Clause |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| attrs | 26.1.0 | MIT |
| azure-core | 1.41.0 | MIT |
| azure-identity | 1.27.0 | MIT |
| certifi | 2026.10.23 | MPL-2.0 |
| cffi | 2.1.1 | MIT |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| cryptography | 50.0.2 | (BSD-3-Clause OR Apache-2.0) AND Python-2.0 |
| databricks-sdk | 0.158.0 | Apache-2.0 |
| databricks-sql-connector | 4.8.0 | Apache-2.0 |
| et-xmlfile | 2.0.0 | MIT |
| fastapi | 0.162.0 | MIT |
| google-auth | 2.62.0 | Apache-2.0 |
| h11 | 0.16.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| itsdangerous | 2.2.0 | BSD-3-Clause |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| lz4 | 4.4.5 | BSD-3-Clause |
| MarkupSafe | 3.0.4 | BSD-3-Clause |
| msal | 1.39.0 | MIT |
| msal-extensions | 1.3.1 | MIT |
| narwhals | 2.28.0 | MIT |
| numpy | 2.5.4 | BSD-3-Clause AND BSD-2-Clause AND MIT AND BSD-3-Clause-Open-MPI AND NCSA AND BSD-2-Clause-FreeBSD AND OpenSSL AND Zlib AND CC0-1.0 AND CC-BY-SA-3.0 AND Apache-2.0 |
| oauthlib | 4.0.0 | BSD-3-Clause |
| openpyxl | 3.1.5 | MIT |
| opentelemetry-api | 1.45.2 | Apache-2.0 |
| orjson | 3.13.0 | Apache-2.0 |
| pandas | 2.3.3 | BSD-3-Clause AND BSD-2-Clause AND Apache-2.0 AND MIT AND TCL AND PSF-2.0 |
| pillow | 13.0.0 | MIT-CMU AND CC0-1.0 |
| protobuf | 7.36.2 | BSD-3-Clause |
| psycopg2-binary | 2.9.13 | zlib-acknowledgement AND LGPL-3.0-or-later WITH openvpn-openssl-exception AND PSF-2.0 |
| pyarrow | 26.0.0 | Apache-2.0 |
| pyasn1 | 0.6.5 | BSD-3-Clause |
| pyasn1-modules | 0.4.2 | BSD-2-Clause |
| pybreaker | 1.4.1 | BSD-3-Clause |
| pycparser | 3.12 | BSD-3-Clause |
| pydantic | 2.14.1 | MIT |
| pydantic-core | 2.50.1 | MIT |
| pydantic-settings | 2.16.2 | MIT |
| pydeck | 0.9.3 | Apache-2.0 |
| PyJWT | 2.15.1 | MIT |
| python-dateutil | 2.9.0.post0 | BSD-3-Clause AND Apache-2.0 |
| python-dateutil | 3.0.0 | BSD-3-Clause AND Apache-2.0 |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| pytz | 2026.6 | MIT |
| referencing | 0.37.0 | MIT |
| requests | 2.34.2 | Apache-2.0 |
| rpds-py | 2026.9.1 | MIT |
| six | 1.17.0 | MIT |
| starlette | 1.10.0 | BSD-3-Clause |
| streamlit | 1.66.1 | Apache-2.0 |
| thrift | 0.25.0 | Apache-2.0 |
| trino | 0.340.0 | Apache-2.0 |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| tzdata | 2026.6 | Apache-2.0 |
| tzlocal | 5.4.5 | MIT |
| urllib3 | 2.8.0 | MIT AND PSF-2.0 |
| uvicorn | 0.54.0 | BSD-3-Clause |
| watchdog | 6.0.0 | Apache-2.0 |
| websockets | 17.3 | BSD-3-Clause |
| zstandard | 0.25.0 | BSD-3-Clause |

> Note: `python-dateutil` appears at two versions because the backend and frontend
> environments resolved different versions (in the backend, `databricks-sql-connector` 4.x
> requires `python-dateutil<3.0.0`). Pin both environments to a single version to remove
> the duplication.

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
