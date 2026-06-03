# Security Policy

## Supported versions

pyxschem is pre-1.0 (Development Status: Alpha). Only the most recent release
on PyPI receives security fixes.

| Version | Supported |
|-|-|
| latest 0.x | yes |
| older | no |

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue.

Use GitHub's private vulnerability reporting:
<https://github.com/Cognitohazard/pyxschem/security/advisories/new>

### Threat surface

pyxschem parses untrusted `.sch` / `.sym` / `xschemrc` files (including Tcl-style
`$VAR` / `$env(NAME)` expansion) and, via `XschemCLI`, shells out to the external
`xschem` binary. Treat input files from untrusted sources accordingly. Reports
involving parser crashes, path traversal during library resolution, or argument
construction in the CLI wrapper are in scope.

As a small project we cannot commit to a fixed response SLA, but we aim to
acknowledge reports promptly.
