# Contributing

Thanks for your interest in contributing! This document explains how to propose changes.

## Getting set up

See the [README](README.md) for prerequisites, local setup, and how to run the backend
and frontend. Install test dependencies with:

```bash
pip install -r tests/requirements-test.txt
```

## Development workflow

1. Fork the repository and create a feature branch off the default branch.
2. Make your change, keeping it focused and matching the surrounding code style.
3. Add or update tests under `tests/` for behavior changes.
4. Run the checks below and make sure they pass.
5. Open a pull request describing **what** changed and **why**.

## Checks before opening a PR

```bash
pytest                # run the test suite
pip-audit             # (recommended) check dependencies for known vulnerabilities
```

- Do not commit secrets or internal infrastructure identifiers. Configuration belongs in
  environment variables / the `app.yaml.example` files, never in tracked `app.yaml`.
- New source files should carry the Apache-2.0 license header (see below).
- If you add or change a dependency, update the pinned requirements and regenerate
  `THIRD-PARTY-NOTICES.md` from the SBOM.

## License header for new files

Add this header to the top of new source files:

```python
# Copyright 2026 GEODIS
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
```

## Developer Certificate of Origin / licensing of contributions

By contributing, you agree that your contributions are licensed under the project's
[Apache License 2.0](LICENSE), consistent with section 5 ("Submission of Contributions")
of that license.

> **Maintainers:** confirm with your legal team whether contributions should require a
> signed [DCO](https://developercertificate.org/) (`git commit -s`) or a Contributor
> License Agreement (CLA), and update this section accordingly.

## Code of Conduct

This project is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating,
you are expected to uphold it.
