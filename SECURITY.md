# Security Policy

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues, pull
requests, or discussions.**

Instead, report them privately using one of the following:

- GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  ("Report a vulnerability" under the repository's **Security** tab)

Please include as much of the following as you can:

- A description of the vulnerability and its impact.
- Steps to reproduce (proof of concept, affected endpoint/component, configuration).
- The affected version, commit, or deployment.
- Any suggested remediation.

## What to expect

- We aim to acknowledge your report within **7 business days**.
- We aim to provide an assessment and expected remediation timeline after triage.
- We try to keep you informed of progress and coordinate disclosure timing with you.
- With your permission, we are happy to credit you once a fix is released.

## Scope

This policy covers the code in this repository. Vulnerabilities in third-party
dependencies should be reported to the respective upstream projects; if a dependency
issue affects this project, please let us know so we can upgrade or mitigate.

## Handling secrets

This project reads all credentials and infrastructure identifiers from environment
variables (see the `app.yaml.example` files). Never commit real secrets. If you discover
a committed secret, treat it as compromised: report it privately, and it should be
**rotated/revoked**, not merely removed from the latest commit.
