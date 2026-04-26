import sys
from pathlib import Path
from typing import Any, Callable
from api_client import APIClient
from config_manager import ConfigManager

def cmd_doctor(cm: ConfigManager, api_client_factory: Callable[[dict], Any] = APIClient) -> int:

    # The api_client_factory is used in tests, to override the actual APIClient class with a mock.

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
    try:
        version = client.get_version()
        print(f"API reachable at {api_cfg['base_url'].rstrip('/')}/ - backend version: {version}")
    except Exception as e:
        print(f"API check failed (version endpoint): {e}", file=sys.stderr)
        return 1

    try:
        login = client.login()
        if not login.status or not login.token:
            print(f"Login failed: {login.msg or 'no JWT token in response'}", file=sys.stderr)
            return 1
        print(f"Authenticated as {api_cfg['username']!r} (user id {login.user_id}).")
    except Exception as e:
        print(f"API check failed (login): {e}", file=sys.stderr)
        return 1

    try:
        scopes = client.list_telescopes()
        print(f"Telescopes available: {len(scopes)}")
        sid = api_cfg.get("scope_id")
        if sid is not None and str(sid).strip() != "":
            want = int(sid)
            ids = {int(t.get("scope_id")) for t in scopes if t.get("scope_id") is not None}
            if want not in ids:
                print(
                    f"Configured api.scope_id={want} is not in the telescope list from the API.",
                    file=sys.stderr,
                )
                return 1
            names = [t.get("name") for t in scopes if int(t.get("scope_id", -1)) == want]
            label = names[0] if names else "?"
            print(f"Configured scope_id {want} OK ({label!r}).")
        else:
            print(
                "Note: api.scope_id is not set; use `telescope list` and `telescope set`.",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"API check failed (telescope list): {e}", file=sys.stderr)
        return 1

    nina_cfg = cm.get_nina_config()
    exe = nina_cfg.get("executable_path", "")
    nina_path = Path(str(exe)) if exe else None
    if not nina_path or not nina_path.is_file():
        print(
            f"NINA executable not found or not configured: {exe!r}",
            file=sys.stderr,
        )
        return 1
    print(f"NINA executable found: {nina_path}")

    print("Configuration and connectivity check passed.")
    return 0
