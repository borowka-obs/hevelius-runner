import argparse
import sys
from typing import Any, Dict, List, Optional, Tuple

from api_client import APIClient, _join_api
from config_manager import ConfigManager


def _require_loaded(cm: ConfigManager) -> int:
    if cm.loaded:
        return 0
    print("Cannot continue without a valid configuration file.", file=sys.stderr)
    return 1


def _require_api(cm: ConfigManager) -> Tuple[int, Optional[APIClient]]:
    code = _require_loaded(cm)
    if code != 0:
        return code, None
    api_cfg = cm.get_api_config()
    required = ("base_url", "timeout", "username", "password")
    missing = [k for k in required if not str(api_cfg.get(k, "")).strip()]
    if missing:
        print(f"API configuration incomplete (missing: {', '.join(missing)}).", file=sys.stderr)
        return 1, None
    client = APIClient(api_cfg)
    try:
        client.get_version()
        client.login()
    except Exception as e:
        print(f"API login failed: {e}", file=sys.stderr)
        return 1, None
    return 0, client


def _scope_id_from_config(cm: ConfigManager) -> Optional[int]:
    raw = cm.get_api_config().get("scope_id")
    if raw is None or not str(raw).strip():
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _first_list_like(data: Any, keys: List[str]) -> Optional[List[Dict[str, Any]]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            v = data.get(key)
            if isinstance(v, list):
                return v
    return None


def _get_projects_from_endpoint(
    client: APIClient,
    endpoint: str,
    scope_id: int,
) -> Optional[List[Dict[str, Any]]]:
    url = _join_api(client.base_url, endpoint)
    response = client.session.get(
        url,
        params={"scope_id": scope_id},
        timeout=client.timeout,
        headers=client._get_auth_headers(),
    )
    response.raise_for_status()
    data = response.json()
    return _first_list_like(data, ["projects", "rows", "items", "data"])


def get_projects_list(client: APIClient, scope_id: int) -> List[Dict[str, Any]]:
    """
    Fetch projects for a local telescope (scope_id).

    Tries several endpoint names to tolerate backend naming differences.
    """
    candidates = ("projects", "project-list")
    last_error: Optional[Exception] = None
    for endpoint in candidates:
        try:
            rows = _get_projects_from_endpoint(client, endpoint, scope_id)
            if rows is not None:
                return rows
        except Exception as e:
            last_error = e
    if last_error is not None:
        raise last_error
    return []


def _project_id(project: Dict[str, Any]) -> Any:
    for key in ("project_id", "id"):
        if key in project:
            return project.get(key)
    return None


def _project_name(project: Dict[str, Any]) -> str:
    for key in ("name", "project_name"):
        if project.get(key) is not None:
            return str(project.get(key))
    return ""


def _project_radec(project: Dict[str, Any]) -> Tuple[Any, Any]:
    ra = project.get("ra") if "ra" in project else project.get("RA")
    dec = project.get("decl") if "decl" in project else project.get("dec")
    if dec is None:
        dec = project.get("DEC")
    return ra, dec


def _print_project_list(projects: List[Dict[str, Any]]) -> None:
    for project in projects:
        pid = _project_id(project)
        name = _project_name(project)
        ra, dec = _project_radec(project)
        extras = []
        if ra is not None:
            extras.append(f"ra={ra}")
        if dec is not None:
            extras.append(f"dec={dec}")
        extra_s = f" {' '.join(extras)}" if extras else ""
        print(f"project_id={pid}\t{name}{extra_s}")


def _fmt(value: Any, indent: int = 0) -> List[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        out: List[str] = []
        for key in sorted(value.keys()):
            v = value[key]
            if isinstance(v, (dict, list)):
                out.append(f"{prefix}{key}:")
                out.extend(_fmt(v, indent + 2))
            else:
                out.append(f"{prefix}{key}: {v}")
        return out
    if isinstance(value, list):
        out = []
        for idx, item in enumerate(value, start=1):
            if isinstance(item, (dict, list)):
                out.append(f"{prefix}- item {idx}:")
                out.extend(_fmt(item, indent + 2))
            else:
                out.append(f"{prefix}- {item}")
        return out
    return [f"{prefix}{value}"]


def _print_project_details(project: Dict[str, Any]) -> None:
    print("Project:")
    for line in _fmt(project, indent=2):
        print(line)


def _subframes_from_project(project: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("subframes", "frames", "project_subframes"):
        v = project.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    return []


def _project_matches(project: Dict[str, Any], project_id: Optional[int], name: Optional[str]) -> bool:
    if project_id is not None:
        pid = _project_id(project)
        try:
            return pid is not None and int(pid) == int(project_id)
        except (TypeError, ValueError):
            return False
    if name is not None:
        return _project_name(project).strip().lower() == name.strip().lower()
    return False


def _resolve_project_from_list(
    projects: List[Dict[str, Any]],
    project_id: Optional[int],
    name: Optional[str],
) -> Optional[Dict[str, Any]]:
    matches = [p for p in projects if _project_matches(p, project_id, name)]
    if not matches:
        return None
    return matches[0]


def _get_project_detail_from_endpoint(
    client: APIClient,
    endpoint: str,
    scope_id: int,
    project_id: Optional[int],
    name: Optional[str],
) -> Optional[Dict[str, Any]]:
    params: Dict[str, Any] = {"scope_id": scope_id}
    if project_id is not None:
        params["project_id"] = project_id
    if name is not None:
        params["name"] = name
    url = _join_api(client.base_url, endpoint)
    response = client.session.get(
        url,
        params=params,
        timeout=client.timeout,
        headers=client._get_auth_headers(),
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        project = data.get("project")
        if isinstance(project, dict):
            return project
        if _project_id(data) is not None or _project_name(data):
            return data
    return None


def get_project_details(
    client: APIClient,
    scope_id: int,
    project_id: Optional[int],
    name: Optional[str],
) -> Optional[Dict[str, Any]]:
    for endpoint in ("project-get", "project", "projects/view"):
        try:
            project = _get_project_detail_from_endpoint(client, endpoint, scope_id, project_id, name)
            if isinstance(project, dict):
                return project
        except Exception:
            continue
    projects = get_projects_list(client, scope_id)
    return _resolve_project_from_list(projects, project_id=project_id, name=name)


def cmd_projects_list(cm: ConfigManager) -> int:
    code, client = _require_api(cm)
    if code != 0 or client is None:
        return code

    scope_id = _scope_id_from_config(cm)
    if scope_id is None:
        print(
            "api.scope_id is not set. Run: hevelius-runner telescope list\n"
            "Then: hevelius-runner telescope set <id_or_name>",
            file=sys.stderr,
        )
        return 1

    try:
        projects = get_projects_list(client, scope_id)
    except Exception as e:
        print(f"Failed to list projects: {e}", file=sys.stderr)
        return 1

    if not projects:
        print("No projects returned by the API.")
        return 0
    _print_project_list(projects)
    return 0


def cmd_projects_view(cm: ConfigManager, project_name: Optional[str], project_id: Optional[int]) -> int:
    code, client = _require_api(cm)
    if code != 0 or client is None:
        return code

    if not project_name and project_id is None:
        print("Either --name or --project-id must be provided.", file=sys.stderr)
        return 2

    scope_id = _scope_id_from_config(cm)
    if scope_id is None:
        print(
            "api.scope_id is not set. Run: hevelius-runner telescope list\n"
            "Then: hevelius-runner telescope set <id_or_name>",
            file=sys.stderr,
        )
        return 1

    try:
        project = get_project_details(
            client,
            scope_id=scope_id,
            project_id=project_id,
            name=project_name,
        )
    except Exception as e:
        print(f"Failed to retrieve project details: {e}", file=sys.stderr)
        return 1

    if project is None:
        ident = f"project_id={project_id}" if project_id is not None else f"name={project_name!r}"
        print(f"No project found for {ident}.", file=sys.stderr)
        return 1

    _print_project_details(project)
    subframes = _subframes_from_project(project)
    if subframes:
        print("\nSubframes:")
        for idx, sf in enumerate(subframes, start=1):
            print(f"  [{idx}]")
            for line in _fmt(sf, indent=4):
                print(line)
    else:
        print("\nSubframes: none")
    return 0


def cmd_projects(cm: ConfigManager, args: argparse.Namespace) -> int:
    if args.projects_cmd == "list":
        return cmd_projects_list(cm)
    if args.projects_cmd == "view":
        return cmd_projects_view(cm, project_name=args.name, project_id=args.project_id)
    print("Unknown projects subcommand.", file=sys.stderr)
    return 2
