# Hevelius Runner Changelog

0.2.0 (unreleased)

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
- the 'volumes` command can now scan files in multiple modes: file (-f, or --file), file-list (-l, or --list),
  directory (-d, or --dir) or all volumes (--sanity-files)


0.0.1

- Initial automation prototype (INI config, NINA integration, API client)
