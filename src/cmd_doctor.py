import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable

from api_client import APIClient
from config_manager import ConfigManager
from console_color import GREEN, RED, color_segment
from cmd_volumes import _monitor_volumes_from_config

logger = logging.getLogger(__name__)


def _ok() -> str:
    return color_segment(GREEN, "OK", sys.stdout)


def _fail() -> str:
    return color_segment(RED, "FAILED", sys.stdout)


def cmd_doctor(cm: ConfigManager, api_client_factory: Callable[[dict], Any] = APIClient) -> int:

    # The api_client_factory is used in tests, to override the actual APIClient class with a mock.

    exit_code = 0
    api_cfg = cm.get_api_config()
    required_api = ("base_url", "timeout", "username", "password")
    missing = [k for k in required_api if not str(api_cfg.get(k, "")).strip()]
    if missing:
        logger.error(f"API config — missing: {', '.join(missing)}  {_fail()}")
        return 1

    client = api_client_factory(api_cfg)
    version_ok = False
    try:
        version = client.get_version()
        logger.info(f"API reachable — {api_cfg['base_url'].rstrip('/')}/ (version {version})  {_ok()}")
        version_ok = True
    except Exception as e:
        exit_code = 1
        logger.error(f"API reachable — unreachable: {e}  {_fail()}")

    login_ok = False
    if version_ok:
        try:
            login = client.login()
            if not login.status or not login.token:
                exit_code = 1
                logger.error(f"Login — {login.msg or 'no JWT token in response'}  {_fail()}")
            else:
                login_ok = True
                logger.info(f"Login — authenticated as {api_cfg['username']!r} (user id {login.user_id})  {_ok()}")
        except Exception as e:
            exit_code = 1
            logger.error(f"Login — {e}  {_fail()}")
    else:
        logger.info("Login — skipped (API not reached)")

    if version_ok and login_ok:
        try:
            scopes = client.list_telescopes()
            sid = api_cfg.get("scope_id")
            if sid is None or not str(sid).strip():
                logger.info("Telescope — api.scope_id not set; use `telescope list` and `telescope set`")
            else:
                want = int(sid)
                ids = {int(t.get("scope_id")) for t in scopes if t.get("scope_id") is not None}
                if want not in ids:
                    exit_code = 1
                    logger.error(
                        f"Telescope — scope_id={want} not found in API list ({len(scopes)} telescope(s))  {_fail()}"
                    )
                else:
                    names = [t.get("name") for t in scopes if int(t.get("scope_id", -1)) == want]
                    label = names[0] if names else "?"
                    logger.info(
                        f"Telescope — scope_id={want} ({label!r}), {len(scopes)} telescope(s) available  {_ok()}"
                    )
        except Exception as e:
            exit_code = 1
            logger.error(f"Telescope — {e}  {_fail()}")
    elif version_ok:
        logger.info("Telescope — skipped (not authenticated)")
    else:
        logger.info("Telescope — skipped (API not reached)")

    nina_cfg = cm.get_nina_config()
    exe = nina_cfg.get("executable_path", "")
    nina_path = Path(str(exe)) if exe else None
    if not nina_path or not nina_path.is_file():
        exit_code = 1
        logger.error(f"NINA — executable not found: {exe!r}  {_fail()}")
    else:
        logger.info(f"NINA — {nina_path}  {_ok()}")

    volumes = _monitor_volumes_from_config(cm)
    if not volumes:
        logger.info("Volumes — none configured")
    else:
        for path, nickname in volumes:
            if not os.path.isdir(path):
                exit_code = 1
                logger.error(f"Volume '{nickname}' — {path}  {_fail()} (directory not found)")
            else:
                try:
                    os.listdir(path)
                    logger.info(f"Volume '{nickname}' — {path}  {_ok()}")
                except OSError as e:
                    exit_code = 1
                    logger.error(f"Volume '{nickname}' — {path}  {_fail()} ({e})")

    if exit_code == 0:
        logger.info(f"All checks passed  {_ok()}")
    else:
        logger.error(f"Doctor — one or more checks failed (see above)  {_fail()}")
    return exit_code
