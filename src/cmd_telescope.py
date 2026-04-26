import sys
import logging
from typing import Optional
from api_client import APIClient, resolve_scope_id_from_identifier
from config_manager import ConfigManager

def cmd_telescope_list(cm: ConfigManager) -> int:

    api_cfg = cm.get_api_config()
    required = ("base_url", "timeout", "username", "password")
    missing = [k for k in required if not str(api_cfg.get(k, "")).strip()]
    if missing:
        print(f"API configuration incomplete (missing: {', '.join(missing)}).", file=sys.stderr)
        return 1
    client = APIClient(api_cfg)
    try:
        client.get_version()
        client.login()
        scopes = client.list_telescopes()
    except Exception as e:
        print(f"Failed to list telescopes: {e}", file=sys.stderr)
        return 1
    if not scopes:
        print("No telescopes returned by the API.")
        return 0
    configured_scope_id: Optional[int] = None
    raw_scope_id = api_cfg.get("scope_id")
    if raw_scope_id is not None and str(raw_scope_id).strip() != "":
        try:
            configured_scope_id = int(raw_scope_id)
        except (TypeError, ValueError):
            configured_scope_id = None

    for t in scopes:
        sid = t.get("scope_id")
        name = t.get("name") or ""
        marker = " "
        if configured_scope_id is not None and sid is not None:
            try:
                if int(sid) == configured_scope_id:
                    marker = "*"
            except (TypeError, ValueError):
                pass
        print(f"scope_id={sid}\t{name} {marker}")
    return 0


def cmd_telescope_set(cm: ConfigManager, identifier: str) -> int:

    api_cfg = cm.get_api_config()
    required = ("base_url", "timeout", "username", "password")
    missing = [k for k in required if not str(api_cfg.get(k, "")).strip()]
    if missing:
        print(f"API configuration incomplete (missing: {', '.join(missing)}).", file=sys.stderr)
        return 1
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    client = APIClient(api_cfg)
    try:
        client.get_version()
        client.login()
        scope_id, matched_name = resolve_scope_id_from_identifier(client, identifier)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Failed to resolve telescope: {e}", file=sys.stderr)
        return 1
    try:
        cm.write_api_scope_id(scope_id)
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    extra = f" ({matched_name!r})" if matched_name else ""
    print(f"Wrote api.scope_id = {scope_id}{extra} to {cm.config_path}")
    return 0
