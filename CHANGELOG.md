# Hevelius Runner Changelog

0.2.0 (unreleased)

- YAML configuration with `run`, `config`, and `check` subcommands; redacted `config` output
- Added `version` command; optional `--backend` queries the Hevelius API `/version` endpoint
- Login uses plaintext password over HTTPS and JWT; `LoginResponse` accepts partial JSON from the server
- Added `telescope list` (`GET /api/scopes`) and `telescope set <id_or_name>` to write `api.scope_id`
- `run` requires `scope_id`; `check` validates JWT login and telescope list (and configured `scope_id` when set)
- Fixed API URL joining for `task-update` and `task-get`
- OpenAPI: documented plaintext password for `/api/login`
- Unit tests for config, CLI, login parsing, scope resolution, and URL helpers
- `check` command renamed to `doctor`

0.0.1

- Initial automation prototype (INI config, NINA integration, API client)
