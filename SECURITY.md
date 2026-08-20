# Security policy

## Supported versions

Security fixes are applied to the latest commit on `main`. Older commits and
forks are not maintained as separate release lines.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's **Report a
vulnerability** flow on the repository Security page when that option is
available. If it is unavailable, open a public issue containing only a request
for a private contact channel. Do not include exploit details, route data,
credentials, tokens, or other sensitive information in a public issue.

Include the affected URL or commit, impact, reproducible steps, and a minimal
proof of concept with secrets removed. The maintainer will acknowledge reports
on a best-effort basis, normally within seven days. Please allow time for a fix
before public disclosure.

## Secrets and historical credentials

If a credential is exposed, revoke or rotate it first; deleting it from the
current source tree is not sufficient because Git history and existing clones
may still contain it. Do not test suspected credentials against third-party
systems.

## Scope

Useful reports include authentication or authorization bypasses, injection,
unsafe file generation, sensitive-data exposure, and abuse of server-side
requests. Reports that only concern upstream public routing availability,
browser extensions, or unsupported local modifications are generally out of
scope unless this project introduces an additional security impact.
