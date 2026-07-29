# Hevelius Runner Changelog

0.3.0 (2026-07-29)

- Basic installation script that makes it easier to use
- Mass rename implemented (`hevelius-runner volumes rename "SUBSTRING1" "SUBSTRING2"`)
- Exclude patterns - specified files or directories can be excluded from the volumes handling.
- `projects` command renamed to `project`
- `project list` and `project view` now render compact, table-based, color-aware output
  with RA/Dec in sexagesimal notation and
  expanded scope name/ID for `project view`
- Volumes and file monitor support PixInsight/NINA XISF (``.xisf``) in addition to FITS
- Image discovery/header reading centralized in ``image_formats`` (extensible for future types)

0.2.0 (2026-04-28)

- YAML configuration with `run`, `config`, and `doctor` subcommands; redacted `config` output
- Added `version` command; optional `--backend` queries the Hevelius API `/version` endpoint
- Login uses plaintext password over HTTPS and JWT; `LoginResponse` accepts partial JSON from the server
- Added `telescope list` (`GET /api/scopes`) and `telescope set <id_or_name>` to write `api.scope_id`
- `run` requires `scope_id`; `check` validates JWT login and telescope list (and configured `scope_id` when set)
- Fixed API URL joining for `task-update` and `task-get`
- OpenAPI: documented plaintext password for `/api/login`
- Unit tests for config, CLI, login parsing, scope resolution, and URL helpers
- `check` command renamed to `doctor`
- `repo` command renamed to `volumes`
- the `volumes` command can now scan files in multiple modes: file (-f, or --file), file-list (-l, or --list),
  directory (-d, or --dir) or all volumes (--sanity-files)
- the `volumes` command now take optional `--tasks` argument. If specified, it will insert or update tasks
  for each found file.
- the `volumes` command now take optional `--projects` argument. If specified, it will try to match files
  to projects, and then update the projects statistics.
- the `volumes` command now have optional `--orphans` argument. If specified, it will list all files
  there it was unable to match to any project.

0.0.1 (never released)

- Initial automation prototype (INI config, NINA integration, API client)
