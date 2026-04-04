import copy
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def _warn_missing_config(path: Path) -> None:
    example = path.parent / "config.yaml.example"
    hint = (
        f"Configuration file not found: {path}\n"
        f"  Copy the example to create your config:\n"
        f"    {example.name} → {path.name}\n"
        f"  (full path: {path.resolve()})\n"
        f"Then edit API credentials, paths, and NINA location."
    )
    print(hint, file=sys.stderr)


def _warn_invalid_yaml(path: Path, err: yaml.YAMLError) -> None:
    print(
        f"Could not parse configuration (invalid YAML): {path}\n"
        f"  {err}",
        file=sys.stderr,
    )


class ConfigManager:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = Path(config_path)
        self.raw: Optional[Dict[str, Any]] = None
        self.loaded = False

        if not self.config_path.exists():
            _warn_missing_config(self.config_path)
            return

        try:
            text = self.config_path.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            _warn_invalid_yaml(self.config_path, e)
            return
        except OSError as e:
            print(f"Could not read configuration file: {self.config_path}\n  {e}", file=sys.stderr)
            return

        if data is None:
            self.raw = {}
        elif not isinstance(data, dict):
            print(
                f"Configuration must be a YAML mapping (key/value), not {type(data).__name__}: "
                f"{self.config_path}",
                file=sys.stderr,
            )
            return
        else:
            self.raw = data

        self.loaded = True

    def get_api_config(self) -> Dict[str, Any]:
        if not self.loaded or not self.raw:
            return {}
        return dict(self.raw.get("api") or {})

    def get_paths_config(self) -> Dict[str, Any]:
        if not self.loaded or not self.raw:
            return {}
        return dict(self.raw.get("paths") or {})

    def get_nina_config(self) -> Dict[str, Any]:
        if not self.loaded or not self.raw:
            return {}
        return dict(self.raw.get("nina") or {})

    def get_scripts_config(self) -> Dict[str, Any]:
        if not self.loaded or not self.raw:
            return {}
        return dict(self.raw.get("scripts") or {})

    def redacted_copy(self) -> Dict[str, Any]:
        """Deep copy of raw config with secrets masked (for display)."""
        if not self.raw:
            return {}
        out = copy.deepcopy(self.raw)
        api = out.get("api")
        if isinstance(api, dict) and "password" in api:
            api["password"] = "***"
        return out

    def write_api_scope_id(self, scope_id: int) -> None:
        """Persist api.scope_id into the config file (mutates in-memory raw)."""
        if not self.loaded or self.raw is None:
            raise RuntimeError("Cannot write scope_id: configuration is not loaded.")
        api = self.raw.setdefault("api", {})
        api["scope_id"] = int(scope_id)
        text = yaml.dump(
            self.raw,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
        self.config_path.write_text(text.rstrip() + "\n", encoding="utf-8")
