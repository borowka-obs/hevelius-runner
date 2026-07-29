import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from api_client import APIClient, _join_api
from config_manager import ConfigManager
from console_color import GREEN, DIM, color_segment
from astro import ra_to_sexagesimal, dec_to_sexagesimal


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


def _ra_sexagesimal(ra: Any) -> str:
    if ra is None:
        return "—"
    try:
        return ra_to_sexagesimal(float(ra))
    except (TypeError, ValueError):
        return str(ra)


def _dec_sexagesimal(dec: Any) -> str:
    if dec is None:
        return "—"
    try:
        dv = float(dec)
    except (TypeError, ValueError):
        return str(dec)
    sx = dec_to_sexagesimal(dv)
    return sx if sx.startswith("-") else f"+{sx}"


def _compact_datetime(value: Any) -> str:
    if value is None:
        return "—"
    s = str(value).strip()
    if not s:
        return "—"
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})", s)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return s[:16]


def _table_lines(
    headers: List[str],
    rows: List[List[str]],
    aligns: Optional[List[str]] = None,
) -> List[str]:
    """Render a box-drawn table. ``aligns`` is a per-column list of 'l' or 'r'."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    aligns = aligns or ["l"] * len(headers)

    def _cell(text: str, i: int) -> str:
        return text.rjust(widths[i]) if aligns[i] == "r" else text.ljust(widths[i])

    def _row(cells: List[str]) -> str:
        return "│ " + " │ ".join(_cell(c, i) for i, c in enumerate(cells)) + " │"

    top = "┌─" + "─┬─".join("─" * w for w in widths) + "─┐"
    mid = "├─" + "─┼─".join("─" * w for w in widths) + "─┤"
    bot = "└─" + "─┴─".join("─" * w for w in widths) + "─┘"

    lines = [top, _row(headers), mid]
    lines.extend(_row(row) for row in rows)
    lines.append(bot)
    return lines


def _print_project_list(projects: List[Dict[str, Any]]) -> None:
    headers = ["ID", "Name", "RA", "Dec"]
    rows = []
    for project in projects:
        pid = _project_id(project)
        name = _project_name(project)
        ra, dec = _project_radec(project)
        rows.append([str(pid) if pid is not None else "—", name, _ra_sexagesimal(ra), _dec_sexagesimal(dec)])
    for line in _table_lines(headers, rows, aligns=["r", "l", "r", "r"]):
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


def _scope_names(client: APIClient) -> Dict[int, str]:
    try:
        scopes = client.list_telescopes()
    except Exception:
        return {}
    out: Dict[int, str] = {}
    for t in scopes:
        sid = t.get("scope_id")
        name = t.get("name")
        if sid is None or not name:
            continue
        try:
            out[int(sid)] = str(name)
        except (TypeError, ValueError):
            continue
    return out


def _scope_display(project: Dict[str, Any], scope_names: Dict[int, str]) -> str:
    sid = project.get("scope_id")
    if sid is None:
        return "—"
    name = scope_names.get(sid)
    if name is None:
        try:
            name = scope_names.get(int(sid))
        except (TypeError, ValueError):
            name = None
    return f"{name} ({sid})" if name else f"({sid})"


_LABEL_WIDTH = 13


def _label(text: str, stream: Any) -> str:
    """Pad to a fixed width *before* colorizing, so ANSI codes never affect alignment."""
    return color_segment(DIM, text.ljust(_LABEL_WIDTH), stream)


def _print_project_details(project: Dict[str, Any], scope_names: Dict[int, str]) -> None:
    pid = _project_id(project)
    name = _project_name(project)
    active = project.get("active")
    stream = sys.stdout
    badge = color_segment(GREEN, "active", stream) if active else color_segment(DIM, "inactive", stream)
    title = f"#{pid} {name}" if pid is not None else name
    print(f"{title}  [{badge}]")

    ra, dec = _project_radec(project)
    print(f"  {_label('RA/Dec:', stream)} {_ra_sexagesimal(ra)} / {_dec_sexagesimal(dec)}")

    print(f"  {_label('Scope:', stream)} {_scope_display(project, scope_names)}")

    total = project.get("total_integration_time")
    hours = f"{float(total) / 3600:.1f}h" if isinstance(total, (int, float)) else "—"
    updated = _compact_datetime(project.get("last_updated"))
    print(f"  {_label('Integration:', stream)} {hours}    {_label('Updated:', stream)} {updated}")

    start_date = project.get("start_date")
    end_date = project.get("end_date")
    if start_date or end_date:
        print(f"  {_label('Window:', stream)} {start_date or '—'} → {end_date or '—'}")

    description = project.get("description")
    if description:
        print(f"  {_label('Description:', stream)} {description}")


def _subframe_filter_short(subframe: Dict[str, Any]) -> str:
    filt = subframe.get("filter")
    if isinstance(filt, dict):
        short = filt.get("short_name")
        if short is not None and str(short).strip():
            return str(short).strip()
    if filt is not None and str(filt).strip():
        return str(filt).strip()
    return "—"


def _format_exposure(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):g}s"
    except (TypeError, ValueError):
        return str(value)


def _print_subframes(subframes: List[Dict[str, Any]]) -> None:
    if not subframes:
        print("\nSubframes: none")
        return
    headers = ["ID", "Filter", "Exposure", "Count/Goal", "Active", "Updated"]
    rows = []
    for sf in subframes:
        sid = sf.get("id")
        count = sf.get("count")
        goal = sf.get("goal_count")
        count_goal = f"{count if count is not None else 0}/{goal if goal is not None else '—'}"
        active = sf.get("active")
        active_s = "yes" if active else ("no" if active is not None else "—")
        rows.append([
            str(sid) if sid is not None else "—",
            _subframe_filter_short(sf),
            _format_exposure(sf.get("exposure_time")),
            count_goal,
            active_s,
            _compact_datetime(sf.get("last_updated")),
        ])
    print("\nSubframes:")
    for line in _table_lines(headers, rows, aligns=["r", "l", "r", "r", "l", "l"]):
        print(line)


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

    scope_names = _scope_names(client)
    _print_project_details(project, scope_names)
    subframes = _subframes_from_project(project)
    _print_subframes(subframes)
    return 0


def cmd_projects(cm: ConfigManager, args: Any) -> int:
    if args.project_cmd == "list":
        return cmd_projects_list(cm)
    if args.project_cmd == "view":
        return cmd_projects_view(cm, project_name=args.name, project_id=args.project_id)
    print("Unknown project subcommand.", file=sys.stderr)
    return 2
