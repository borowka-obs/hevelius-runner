# Agent guide — hevelius-runner

## What this is

**hevelius-runner** is the observatory-side client for the Hevelius system. It runs on the machine that controls the telescope (typically with [NINA](https://nighttime-imaging.eu/)), talks to **hevelius-backend** over HTTPS, and handles local work: volumes/FITS/XISF scanning, task reporting, project stats, and (WIP) automated observing.

Related repos:

| Component | Role |
|-----------|------|
| [hevelius-backend](https://github.com/borowka-obs/hevelius-backend) | Central server, DB, REST API — **OpenAPI source of truth** |
| [hevelius-web](https://github.com/borowka-obs/hevelius-web) | Web UI |
| **hevelius-runner** (this repo) | Windows PC / observatory agent |

Do not invent or “fix” API contracts here. The OpenAPI spec lives in the backend:

- Spec: [`api/openapi.yaml`](https://github.com/borowka-obs/hevelius-backend/blob/master/api/openapi.yaml) in [borowka-obs/hevelius-backend](https://github.com/borowka-obs/hevelius-backend)
- Client code: `src/api_client.py` (and command modules that call it)

When adding or changing HTTP calls, align request/response shapes with that OpenAPI file (or an updated PR there). `.gitignore` ignores a local `api/openapi.yaml` copy if checked out for reference.

## Platform priority

**Primary target: Windows.** NINA, typical observatory PCs, PowerShell install helpers (`bin/*.ps1`), and CI (`windows-latest`) assume Windows.

Linux and macOS may work for some CLI features (e.g. `volumes`, `doctor`, API commands). That is **best-effort / lower priority**. It is acceptable if NINA integration or path/console behavior is Windows-only. Prefer Windows path examples in docs (`C:\…`, `y:\astro`) when documenting observatory workflows.

## Layout

```
src/hevelius-runner.py   # CLI entry (argparse subcommands)
src/api_client.py        # REST client + JWT login
src/cmd_*.py             # Subcommand implementations
src/image_formats.py     # Format-agnostic discovery + headers (FITS, XISF, …)
src/fits.py              # FITS-specific helpers
config/config.yaml.example
tests/                   # pytest
doc/                     # install, usage, devel, troubleshooting
```

Global CLI options (e.g. `-c` / `--config`) must appear **before** the subcommand.

Useful commands for agents verifying changes: `doctor`, `config`, `version`, `telescope`, `projects`, `volumes`. The `run` automation loop is outdated and may not work — do not treat it as the main product path unless fixing it deliberately.

## Conventions

- Prefer extending existing modules (`api_client`, `image_formats`, `cmd_*`) over new top-level frameworks.
- Image discovery goes through `image_formats.SUPPORTED_EXTENSIONS` / `read_header`; see `doc/devel.md`.
- Keep passwords and tokens out of logs; `config` output redacts the password.
- **CLI output should be visually attractive.** Use color-coded status text via `src/console_color.py` (respects `NO_COLOR` / non-TTY): green for OK/success, yellow for warnings, red for errors, dim/gray for disabled or secondary detail. Prefer clear, scannable lines over dense dumps.
- Update `CHANGELOG.md` (unreleased section) and user-facing docs (`README.md`, `doc/usage.md`, etc.) when behavior changes.
- Tests: `python -m pytest tests/ -v` (CI runs this on Windows for Python 3.12–3.14).

## Docs map

- Install: `doc/install.md`
- Usage: `doc/usage.md`
- Dev / formats: `doc/devel.md`
- Troubleshooting: `doc/troubleshooting.md`
