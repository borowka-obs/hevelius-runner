import sys
from pathlib import Path
from typing import Any, Callable

from api_client import APIClient
from config_manager import ConfigManager
from console_color import RED, color_segment


def _red(text: str) -> str:
    return color_segment(RED, text, sys.stderr)


def cmd_doctor(cm: ConfigManager, api_client_factory: Callable[[dict], Any] = APIClient) -> int:

    # The api_client_factory is used in tests, to override the actual APIClient class with a mock.

    exit_code = 0
    api_cfg = cm.get_api_config()
    required_api = ("base_url", "timeout", "username", "password")
    missing = [k for k in required_api if not str(api_cfg.get(k, "")).strip()]
    if missing:
        print(
            f"API configuration is incomplete (missing: {', '.join(missing)}).",
            file=sys.stderr,
        )
        return 1

    client = api_client_factory(api_cfg)
    version_ok = False
    try:
        version = client.get_version()
        print(f"API reachable at {api_cfg['base_url'].rstrip('/')}/ - backend version: {version}")
        version_ok = True
    except Exception as e:
        exit_code = 1
        print(
            f"Backend API: {_red('unreachable')} ({e})",
            file=sys.stderr,
        )
        print(
            "Skipping API login and telescope checks (backend not reached).",
            file=sys.stderr,
        )

    login_ok = False
    if version_ok:
        try:
            login = client.login()
            if not login.status or not login.token:
                exit_code = 1
                print(f"Login failed: {login.msg or 'no JWT token in response'}", file=sys.stderr)
            else:
                login_ok = True
                print(f"Authenticated as {api_cfg['username']!r} (user id {login.user_id}).")
        except Exception as e:
            exit_code = 1
            print(f"API check failed (login): {e}", file=sys.stderr)

    if version_ok and not login_ok:
        print("Skipping telescope list (not authenticated).", file=sys.stderr)

    if version_ok and login_ok:
        try:
            scopes = client.list_telescopes()
            print(f"Telescopes available: {len(scopes)}")
            sid = api_cfg.get("scope_id")
            if sid is not None and str(sid).strip() != "":
                want = int(sid)
                ids = {int(t.get("scope_id")) for t in scopes if t.get("scope_id") is not None}
                if want not in ids:
                    exit_code = 1
                    print(
                        f"Configured api.scope_id={want} is not in the telescope list from the API.",
                        file=sys.stderr,
                    )
                else:
                    names = [t.get("name") for t in scopes if int(t.get("scope_id", -1)) == want]
                    label = names[0] if names else "?"
                    print(f"Configured scope_id {want} OK ({label!r}).")
            else:
                print(
                    "Note: api.scope_id is not set; use `telescope list` and `telescope set`.",
                    file=sys.stderr,
                )
        except Exception as e:
            exit_code = 1
            print(f"API check failed (telescope list): {e}", file=sys.stderr)

    nina_cfg = cm.get_nina_config()
    exe = nina_cfg.get("executable_path", "")
    nina_path = Path(str(exe)) if exe else None
    if not nina_path or not nina_path.is_file():
        exit_code = 1
        print(
            f"NINA executable not found or not configured: {exe!r}",
            file=sys.stderr,
        )
    else:
        print(f"NINA executable found: {nina_path}")

    if exit_code == 0:
        print("Configuration and connectivity check passed.")
    else:
        print(
            "Configuration check finished with one or more issues (see messages above).",
            file=sys.stderr,
        )
    return exit_code
