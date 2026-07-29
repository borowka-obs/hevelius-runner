"""
Code that handles files repository on disk.
"""
import logging
import os
import re
import sys
import fnmatch
from typing import Any, Dict, List, Optional, Tuple

from fits import gets
from image_formats import (
    header_items,
    image_files_in_dir,
    read_header,
    supported_extensions_glob_display,
)

from api_client import APIClient
from cmd_projects import _get_projects_from_endpoint
from config_manager import ConfigManager
from console_color import GREEN, ORANGE, RED, YELLOW, color_segment


def _color(code: str, text: str) -> str:
    return color_segment(code, text, sys.stdout)


def get_tasks_files_list(client: APIClient) -> List[Tuple[int, Optional[str]]]:
    """
    Return every task as ``(task_id, imagename)`` from the API (JWT required).

    Uses GET ``/api/tasks-filename-list`` (paginated). Per-filename lookups use
    ``/api/task-find-by-filename`` via :func:`get_task_by_filename`.
    """
    return client.list_all_tasks_filenames()


def get_task_by_filename(client: APIClient, filename: str) -> Optional[Tuple[int, Optional[str]]]:
    """
    Return the first matching task for a path suffix via GET ``/api/task-find-by-filename``.
    """
    found, matches = client.find_tasks_by_filename(filename)
    if not found or not matches:
        return None
    m0 = matches[0]
    tid = m0.get("task_id")
    if tid is None:
        return None
    return int(tid), m0.get("filename")


def task_filename_exists(client: APIClient, filename: str) -> bool:
    """True if at least one task's stored imagename ends with the given ``filename`` string."""
    found, _ = client.find_tasks_by_filename(filename)
    return found


def _require_loaded(cm: ConfigManager) -> int:
    if cm.loaded:
        return 0
    print("Cannot continue without a valid configuration file.", file=sys.stderr)
    return 1


def _require_api(cm: ConfigManager, connect: bool = True) -> Tuple[int, Optional[APIClient]]:
    code = _require_loaded(cm)
    if code != 0:
        return code, None
    api_cfg = cm.get_api_config()
    required = ("base_url", "timeout", "username", "password")
    missing = [k for k in required if not str(api_cfg.get(k, "")).strip()]
    if missing:
        print(f"API configuration incomplete (missing: {', '.join(missing)}).", file=sys.stderr)
        return 1, None
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    client = APIClient(api_cfg)
    if not connect:
        return 0, client

    try:
        client.connect()
    except Exception as e:
        print(f"API login failed: {e}", file=sys.stderr)
        return 1, None
    return 0, client


def _repo_path_from_config(cm: ConfigManager) -> Optional[str]:
    paths = cm.get_paths_config()
    raw = paths.get("repo-path")
    if raw is None or not str(raw).strip():
        print(
            "paths.repo-path is not set in config. Add e.g. repo-path: data/repo under paths.",
            file=sys.stderr,
        )
        return None
    return os.path.expanduser(os.path.expandvars(str(raw).strip()))


def _monitor_volumes_from_config(cm: ConfigManager) -> List[Tuple[str, str]]:
    """
    Return configured FITS monitor volumes as ``[(path, nickname), ...]``.

    Supports new ``paths.volumes`` and legacy ``paths.fits_monitor_dir`` fallback.
    """
    paths = cm.get_paths_config()
    volumes_raw = paths.get("volumes")
    volumes: List[Tuple[str, str]] = []

    if isinstance(volumes_raw, list):
        for idx, volume in enumerate(volumes_raw):
            if isinstance(volume, str):
                p = os.path.expanduser(os.path.expandvars(volume.strip()))
                if p:
                    volumes.append((p, f"volume-{idx + 1}"))
                continue

            if isinstance(volume, dict):
                raw_path = volume.get("path")
                if raw_path is None or not str(raw_path).strip():
                    print(
                        f"paths.volumes[{idx}] is missing required key 'path'.",
                        file=sys.stderr,
                    )
                    continue
                p = os.path.expanduser(os.path.expandvars(str(raw_path).strip()))
                nickname = str(volume.get("nickname") or f"volume-{idx + 1}")
                volumes.append((p, nickname))
                continue

            print(
                f"paths.volumes[{idx}] must be either a string path or mapping "
                f"with keys 'path' and optional 'nickname'.",
                file=sys.stderr,
            )

    if volumes:
        return volumes

    legacy = paths.get("fits_monitor_dir")
    if legacy is not None and str(legacy).strip():
        p = os.path.expanduser(os.path.expandvars(str(legacy).strip()))
        return [(p, "default")]

    return []


def _exclude_patterns_from_config(cm: ConfigManager) -> List[str]:
    """
    Return path exclusion patterns from config.

    Reads ``paths.exclude_patterns`` and supports both a single string and list
    of strings. Patterns are matched against normalized full file paths.
    """
    paths = cm.get_paths_config()
    raw = paths.get("exclude_patterns")
    if raw is None:
        return []
    if isinstance(raw, str):
        pattern = raw.strip()
        return [pattern] if pattern else []
    if isinstance(raw, list):
        out: List[str] = []
        for idx, item in enumerate(raw):
            if item is None:
                continue
            if not isinstance(item, str):
                print(
                    f"paths.exclude_patterns[{idx}] must be a string pattern.",
                    file=sys.stderr,
                )
                continue
            p = item.strip()
            if p:
                out.append(p)
        return out
    print("paths.exclude_patterns must be a string or list of strings.", file=sys.stderr)
    return []


def _normalize_full_path(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _resolve_path(path: str) -> str:
    """Absolute path for filesystem I/O (preserves filename case on Windows)."""
    return os.path.normpath(os.path.abspath(path))


def _is_excluded(full_path: str, exclude_patterns: List[str]) -> bool:
    """
    True if the normalized full path matches any exclusion pattern.

    Matching rules:
    - fnmatch against normalized full path
    - plain substring fallback against normalized full path
    """
    if not exclude_patterns:
        return False
    normalized = _normalize_full_path(full_path)
    for pattern in exclude_patterns:
        candidate = os.path.normcase(pattern.strip())
        if not candidate:
            continue
        if fnmatch.fnmatch(normalized, candidate):
            return True
        if candidate in normalized:
            return True
    return False


def _scope_id_from_config(cm: ConfigManager) -> Optional[int]:
    raw = cm.get_api_config().get("scope_id")
    if raw is None or not str(raw).strip():
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _fetch_projects_list(client: APIClient, scope_id: int) -> List[Dict[str, Any]]:
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


def _project_name(project: Dict[str, Any]) -> str:
    for key in ("name", "project_name"):
        val = project.get(key)
        if val is not None:
            s = str(val).strip()
            if s:
                return s
    return ""


def _parse_project_regexps(project: Dict[str, Any]) -> List[str]:
    raw = project.get("regexps")
    if raw is None or not str(raw).strip():
        return []
    return [part for part in str(raw).split() if part]


def _project_match_patterns(project: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Return ``(kind, pattern)`` pairs: configured regexps plus project name."""
    patterns: List[Tuple[str, str]] = []
    for pattern in _parse_project_regexps(project):
        patterns.append(("regexp", pattern))
    name = _project_name(project)
    if name:
        patterns.append(("name", name))
    return patterns


def _file_match_texts(basename: str, object_name: Optional[str] = None) -> List[str]:
    """Build the strings tested against project name/regexp patterns."""
    texts = [basename]
    if object_name:
        texts.append(object_name)
    return texts


def _pattern_matches_texts(kind: str, pattern: str, texts: List[str]) -> bool:
    for text in texts:
        if kind == "name":
            if pattern.lower() in text.lower():
                return True
            continue
        try:
            if re.search(pattern, text, re.IGNORECASE) is not None:
                return True
        except re.error:
            continue
    return False


RegexpTestResult = Tuple[Any, str, str, bool]


def _format_regexp_tests_summary(tests: List[RegexpTestResult]) -> str:
    parts = []
    for project_id, _kind, pattern, matched in tests:
        pid = project_id if project_id is not None else "?"
        status = "match" if matched else "no match"
        color = GREEN if matched else RED
        parts.append(f"'{pattern}'/{pid}:" + _color(color, status))
    return "regexps: " + " ".join(parts)


def _match_project_for_file(
    filename: str,
    projects: List[Dict[str, Any]],
    object_name: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], List[RegexpTestResult]]:
    """Match a file against project regexps and/or name.

    Patterns are tested against the basename and, when available, the FITS
    OBJECT header value. Returns the first matching project and every pattern
    tested with its status.
    """
    key = os.path.basename(filename)
    texts = _file_match_texts(key, object_name)
    tests: List[RegexpTestResult] = []
    matched_project: Optional[Dict[str, Any]] = None
    for project in projects:
        project_id = project.get("project_id")
        for kind, pattern in _project_match_patterns(project):
            matched = _pattern_matches_texts(kind, pattern, texts)
            tests.append((project_id, kind, pattern, matched))
            if matched and matched_project is None:
                matched_project = project
    return matched_project, tests


def _find_project_for_filename(
    filename: str,
    projects: List[Dict[str, Any]],
    object_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    project, _tests = _match_project_for_file(filename, projects, object_name=object_name)
    return project


def _format_project_regexps_display(project: Dict[str, Any]) -> str:
    raw = project.get("regexps")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    if _project_name(project):
        return "(name only)"
    return "(none)"


def _print_projects_with_regexps(projects: List[Dict[str, Any]]) -> None:
    print("Projects and regexps:")
    for project in projects:
        pid = project.get("project_id", "?")
        name = _project_name(project) or "?"
        regexps_display = _format_project_regexps_display(project)
        print(f"  project_id={pid}\t{name}\tregexps={regexps_display}")


def _update_project_stats(
    project_stats: Dict[int, Dict[str, Any]],
    project: Dict[str, Any],
    filter_name: Optional[str],
    exposure: Optional[float],
) -> None:
    project_id = project.get("project_id")
    if project_id is None:
        return
    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return

    pstats = project_stats.setdefault(
        pid,
        {
            "name": _project_name(project) or f"project-{pid}",
            "project": project,
            "buckets": {},
        },
    )
    per_project = pstats["buckets"]
    bucket = (filter_name, exposure)
    per_project[bucket] = per_project.get(bucket, 0) + 1


def _print_project_stats(
    project_stats: Dict[int, Dict[str, Any]],
    files_without_project: int,
    files_without_project_names: Optional[List[str]] = None,
) -> None:
    """Print the orphan-files header. Per-bucket details (with color and the
    add/update/skip action) are printed by :func:`_sync_project_stats_to_server`,
    which is the only code path that knows the action that was actually taken."""
    print()
    print("=== PROJECT STATISTICS ===")
    print(f"Files without project match: {files_without_project}")
    if files_without_project_names:
        for name in files_without_project_names:
            print(f"  {name}")
    if not project_stats:
        print("No project subframes were matched.")


def _subframe_filter_name(subframe: Dict[str, Any]) -> Optional[str]:
    filt = subframe.get("filter")
    if isinstance(filt, dict):
        short = filt.get("short_name")
        if short is not None and str(short).strip():
            return str(short).strip()
    if filt is not None and str(filt).strip():
        return str(filt).strip()
    return None


def _match_subframe(
    subframes: List[Dict[str, Any]],
    filter_name: str,
    exposure: float,
) -> Optional[Dict[str, Any]]:
    fkey = filter_name.strip().lower()
    for sf in subframes:
        sf_filter = _subframe_filter_name(sf)
        sf_exposure = sf.get("exposure_time")
        if sf_filter is None or sf_exposure is None:
            continue
        try:
            sf_exp = float(sf_exposure)
        except (TypeError, ValueError):
            continue
        if sf_filter.strip().lower() == fkey and abs(sf_exp - exposure) < 1e-6:
            return sf
    return None


def _fetch_project_fresh(client: APIClient, project_id: int) -> Optional[Dict[str, Any]]:
    """GET /api/projects/{id} just before sync so we compare against current
    server state (count/goal_count may have moved while we were scanning).

    Returns the project dict on success, or None when the call fails (the caller
    falls back to the cached project data from the initial list fetch)."""
    try:
        url = f"{client.base_url.rstrip('/')}/projects/{int(project_id)}"
        resp = client.session.get(
            url,
            timeout=client.timeout,
            headers=client._get_auth_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            project = data.get("project")
            if isinstance(project, dict):
                return project
    except Exception:
        return None
    return None


def _bucket_action_color(action: str, count: int, goal_count: Optional[int]) -> str:
    """Pick a color for a per-bucket sync result line.

    skipped (no change)            -> orange
    added/updated, count <  goal   -> yellow
    added/updated, count >= goal   -> green
    failed                         -> red
    """
    if action == "skipped":
        return ORANGE
    if action == "failed":
        return RED
    if goal_count is None or goal_count <= 0:
        return GREEN
    return GREEN if count >= goal_count else YELLOW


def _sync_one_bucket(
    client: APIClient,
    project_id: int,
    project_name: str,
    matched: Optional[Dict[str, Any]],
    filter_name: str,
    exposure_f: float,
    count: int,
) -> Tuple[str, Optional[int], Optional[str]]:
    """Sync a single (filter, exposure, count) bucket.

    Returns ``(action, goal_count, error)``:
      - action: ``added``, ``updated``, ``skipped``, or ``failed``
      - goal_count: server-side goal_count when known (used for color logic)
      - error: optional error message when action is ``failed``
    """
    if matched is None:
        url = f"{client.base_url.rstrip('/')}/projects/{project_id}/subframes"
        payload = {
            "filter": str(filter_name),
            "exposure_time": exposure_f,
            "count": int(count),
        }
        try:
            resp = client.session.post(
                url, json=payload, timeout=client.timeout,
                headers=client._get_auth_headers(),
            )
            resp.raise_for_status()
        except Exception as e:
            return "failed", None, f"creating subframe failed: {e}"
        return "added", None, None

    subframe_id = matched.get("id")
    if subframe_id is None:
        return "failed", None, "matched subframe has no id"

    matched_count = matched.get("count")
    goal_count = matched.get("goal_count")
    try:
        goal_count_int = int(goal_count) if goal_count is not None else None
    except (TypeError, ValueError):
        goal_count_int = None

    # Skip when the captured count on the server already matches what we'd
    # send. This avoids spurious last_updated bumps and keeps logs clean for
    # incremental rescans of the same volume.
    try:
        if matched_count is not None and int(matched_count) == int(count):
            return "skipped", goal_count_int, None
    except (TypeError, ValueError):
        pass

    url = f"{client.base_url.rstrip('/')}/projects/{project_id}/subframes/{subframe_id}"
    payload = {"count": int(count)}
    try:
        resp = client.session.patch(
            url, json=payload, timeout=client.timeout,
            headers=client._get_auth_headers(),
        )
        resp.raise_for_status()
    except Exception as e:
        return "failed", goal_count_int, f"updating subframe {subframe_id} failed: {e}"
    return "updated", goal_count_int, None


def _sync_project_stats_to_server(client: APIClient, project_stats: Dict[int, Dict[str, Any]]) -> bool:
    """Sync collected per-project subframe counts to the server.

    For each project, the runner first re-fetches the project (so comparisons
    against ``count``/``goal_count`` use fresh data), then for every bucket:

    * creates a new subframe if no matching (filter, exposure_time) row exists;
    * sends a PATCH with only ``count`` if the server count differs;
    * skips the call entirely when the server count already matches.

    Each per-bucket result is printed on a single color-coded line.
    """
    ok = True
    if not project_stats:
        return ok

    for project_id in sorted(project_stats.keys()):
        entry = project_stats[project_id]
        project_name = entry.get("name") or f"project-{project_id}"

        # Fetch fresh server state for this project; fall back to the cached
        # copy from the initial listing if the GET fails.
        fresh = _fetch_project_fresh(client, project_id)
        if fresh is None:
            fresh = entry.get("project") or {}
        subframes = fresh.get("subframes") if isinstance(fresh, dict) else None
        if not isinstance(subframes, list):
            subframes = []

        print(f"Project: {project_name}")
        buckets = entry.get("buckets", {})
        total_files = sum(buckets.values())
        print(f"  Total matched files: {total_files}")

        for (filter_name, exposure), count in sorted(
            buckets.items(),
            key=lambda item: (
                "" if item[0][0] is None else str(item[0][0]),
                -1.0 if item[0][1] is None else float(item[0][1]),
            ),
        ):
            if filter_name is None or exposure is None:
                print(
                    f"  {_color(RED, '[failed   ]')} incomplete bucket "
                    f"filter={filter_name} exposure={exposure} count={count}"
                )
                ok = False
                continue
            try:
                exposure_f = float(exposure)
            except (TypeError, ValueError):
                print(
                    f"  {_color(RED, '[failed   ]')} invalid exposure "
                    f"filter={filter_name} exposure={exposure!r} count={count}"
                )
                ok = False
                continue

            matched = _match_subframe(subframes, str(filter_name), exposure_f)
            action, goal_count, error = _sync_one_bucket(
                client, project_id, project_name, matched,
                str(filter_name), exposure_f, int(count),
            )
            if action == "failed":
                ok = False

            color = _bucket_action_color(action, int(count), goal_count)
            tag = f"[{action:<9}]"
            line = (
                f"  {tag} filter={filter_name} exposure={exposure_f} "
                f"count={count}"
            )
            if goal_count is not None:
                line += f" goal_count={goal_count}"
            if error:
                line += f"  ({error})"
            print(_color(color, line))
    return ok

def process_fits_list(
    client: APIClient,
    fname: str,
    show_hdr: bool,
    update_task: bool = False,
    projects: Optional[List[Dict[str, Any]]] = None,
    project_stats: Optional[Dict[int, Dict[str, Any]]] = None,
    project_tracker: Optional[Dict[str, int]] = None,
    exclude_patterns: Optional[List[str]] = None,
    verbose: int = 0,
) -> None:
    """
    Processes all FITS files listed in a specified text file.

    :param fname: name of a text file that contains a list of files to be loaded
    :param show_hdr: bool governing whether FITS headers will be printed or not
    """

    with open(fname, encoding="utf-8") as f:
        lines = f.readlines()

    file_lines = [l for l in lines if l.strip() and not l.strip().startswith("#")]
    total = len(file_lines)
    print(f"Found {total} filename(s) in file {fname}")

    cnt = 1
    for line in lines:
        line = line.strip()
        if len(line) == 0 or line[0] == "#":
            # Skip empty and commented out lines (do not bump the counter so
            # the user-visible "n of total" tracks file rows, not blank ones).
            continue

        full_path = _resolve_path(line)
        if _is_excluded(full_path, exclude_patterns or []):
            progress = _format_progress(cnt, total)
            print(f"{progress}{_format_status_tag('skipped')} {full_path}  (excluded)")
            cnt += 1
            continue

        process_fits_file(
            client,
            full_path,
            show_hdr=show_hdr,
            update_task=update_task,
            projects=projects,
            project_stats=project_stats,
            project_tracker=project_tracker,
            idx=cnt,
            total=total,
            verbose=verbose,
        )
        cnt += 1


def _image_files_in_dir(dir_path: str, *, resolve: bool = False) -> List[str]:
    """Return full paths of all supported image files under ``dir_path``."""
    to_path = _resolve_path if resolve else _normalize_full_path
    return sorted({to_path(f) for f in image_files_in_dir(dir_path)})


# Backward-compatible alias used by older tests / callers.
_fits_files_in_dir = _image_files_in_dir


def _paths_from_list_file(list_path: str, *, resolve: bool = False) -> List[str]:
    """Return full paths from a text file (one path per line)."""
    to_path = _resolve_path if resolve else _normalize_full_path
    paths: List[str] = []
    with open(list_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line[0] == "#":
                continue
            paths.append(to_path(line))
    return paths


def _collect_target_paths(
    cm: ConfigManager,
    args,
    *,
    resolve: bool = False,
) -> Tuple[int, List[str]]:
    """
    Resolve image file paths from ``-f`` / ``-l`` / ``-d`` or all configured volumes.

    Mirrors the path-selection rules used by :func:`sanity_files`.
    When ``resolve`` is True, paths keep filesystem casing (needed for rename on Windows).
    """
    to_path = _resolve_path if resolve else _normalize_full_path
    exclude_patterns = _exclude_patterns_from_config(cm)
    paths: List[str] = []

    if args.file:
        paths.append(to_path(args.file))
    elif args.list:
        paths.extend(_paths_from_list_file(args.list, resolve=resolve))
    elif args.dir:
        paths.extend(_image_files_in_dir(args.dir, resolve=resolve))
    else:
        volumes = _monitor_volumes_from_config(cm)
        if not volumes:
            rp = _repo_path_from_config(cm)
            if rp is None:
                print(
                    "No source paths configured. Configure paths.volumes "
                    "(or legacy paths.fits_monitor_dir), or use -f / -l / -d.",
                    file=sys.stderr,
                )
                return 1, []
            volumes = [(rp, "repo-path")]
        for path, nickname in volumes:
            print(f"Volume '{nickname}': {path}")
            paths.extend(_image_files_in_dir(path, resolve=resolve))

    if exclude_patterns:
        paths = [p for p in paths if not _is_excluded(p, exclude_patterns)]
    return 0, paths


def _rename_basename(basename: str, old: str, new: str) -> Optional[str]:
    """Return a new basename with all occurrences of ``old`` replaced by ``new``,
    or ``None`` if ``old`` does not appear. Matching is case-insensitive on Windows."""
    if os.name == "nt":
        lower_base = basename.lower()
        lower_old = old.lower()
        if lower_old not in lower_base:
            return None
        result = []
        i = 0
        while i < len(basename):
            if lower_base[i:i + len(lower_old)] == lower_old:
                result.append(new)
                i += len(lower_old)
            else:
                result.append(basename[i])
                i += 1
        return "".join(result)
    if old not in basename:
        return None
    return basename.replace(old, new)


def rename_files(cm: ConfigManager, args) -> int:
    """Replace ``old_string`` with ``new_string`` in each selected file's basename."""
    code = _require_loaded(cm)
    if code != 0:
        return code

    old = str(getattr(args, "old_string", "") or "")
    new = str(getattr(args, "new_string", "") or "")
    if not old:
        print("rename requires a non-empty search string.", file=sys.stderr)
        return 1

    code, paths = _collect_target_paths(cm, args, resolve=True)
    if code != 0:
        return code
    if not paths:
        print("No files to rename.")
        return 0

    print(f"Renaming basename substring {old!r} -> {new!r} in {len(paths)} file(s).")
    renamed = 0
    skipped = 0
    failed = 0

    for src in paths:
        if not os.path.isfile(src):
            print(f"  skip (not a file): {src}", file=sys.stderr)
            skipped += 1
            continue

        base = os.path.basename(src)
        new_base = _rename_basename(base, old, new)
        if new_base is None:
            skipped += 1
            continue
        if new_base == base:
            skipped += 1
            continue

        dst = os.path.join(os.path.dirname(src), new_base)
        if os.path.exists(dst):
            print(f"  failed (target exists): {src} -> {dst}", file=sys.stderr)
            failed += 1
            continue

        try:
            os.rename(src, dst)
        except OSError as e:
            print(f"  failed: {src} -> {dst}: {e}", file=sys.stderr)
            failed += 1
            continue

        print(f"  {base} -> {new_base}")
        renamed += 1

    print(f"Done: {renamed} renamed, {skipped} unchanged, {failed} failed.")
    return 1 if failed else 0


def process_fits_dir(
    client: APIClient,
    dir: str,
    show_hdr: bool,
    update_task: bool = False,
    projects: Optional[List[Dict[str, Any]]] = None,
    project_stats: Optional[Dict[int, Dict[str, Any]]] = None,
    project_tracker: Optional[Dict[str, int]] = None,
    exclude_patterns: Optional[List[str]] = None,
    verbose: int = 0,
) -> None:
    """
    Processes all supported image files in specified directory.

    :param dir: directory to be traversed
    :param show_hdr: bool governing whether headers will be printed or not
    """

    files = _image_files_in_dir(dir, resolve=True)

    print(f"Found {len(files)} files(s) in directory {dir}")

    cnt = 1
    total = len(files)

    for f in files:
        full_path = str(f)
        if _is_excluded(full_path, exclude_patterns or []):
            progress = _format_progress(cnt, total)
            print(f"{progress}{_format_status_tag('skipped')} {full_path}  (excluded)")
            cnt += 1
            continue

        process_fits_file(
            client,
            full_path,
            show_hdr,
            update_task=update_task,
            projects=projects,
            project_stats=project_stats,
            project_tracker=project_tracker,
            idx=cnt,
            total=total,
            verbose=verbose,
        )
        cnt += 1


def _format_progress(idx: Optional[int], total: Optional[int]) -> str:
    """Render the per-file progress prefix (e.g. ``[ 12/345]``) or empty string."""
    if idx is None or total is None or total <= 0:
        return ""
    width = max(1, len(str(total)))
    return f"[{idx:>{width}}/{total}] "


def _format_status_tag(status: str) -> str:
    """
    Render a fixed-width, color-coded status tag for compact per-file logging.

    matched   -> green   (file matched a project)
    unmatched -> red     (no project matched)
    skipped   -> yellow  (file was excluded or otherwise not processed)
    """
    label = f"{status:<9}"
    if status == "matched":
        return f"[{_color(GREEN, label)}]"
    if status == "unmatched":
        return f"[{_color(RED, label)}]"
    if status == "skipped":
        return f"[{_color(YELLOW, label)}]"
    return f"[{label}]"


def _format_file_params(filter_name: Optional[str], exposure: Optional[float],
                        object_name: Optional[str]) -> str:
    """Render ``filter=… exposure=… object=…`` skipping fields that are None."""
    parts = []
    if filter_name is not None:
        parts.append(f"filter={filter_name}")
    if exposure is not None:
        parts.append(f"exposure={exposure}")
    if object_name is not None:
        parts.append(f"object={object_name}")
    return " ".join(parts)


def process_fits_file(client: APIClient,  fname, show_hdr: bool, verbose: int = 0,
                      update_task: bool = False,
                      projects: Optional[List[Dict[str, Any]]] = None,
                      project_stats: Optional[Dict[int, Dict[str, Any]]] = None,
                      project_tracker: Optional[Dict[str, Any]] = None,
                      idx: Optional[int] = None,
                      total: Optional[int] = None):
    """Processes an image file: optional header dump and task lookup via the API.

    Supports FITS and XISF (see :mod:`image_formats`). Emits a single status
    line per file with a color-coded tag: ``matched`` (green), ``unmatched``
    (red), or ``skipped`` (yellow). The ``idx``/``total`` parameters are
    optional and only used to render the progress prefix when called from a
    batch processor.
    """

    key = os.path.basename(fname)

    # Extract file parameters from the header (format-agnostic)
    h = read_header(fname)
    filter = _h_str(h, "FILTER")
    object = _h_str(h, "OBJECT")
    exposure = _h_float(h, "EXPTIME")

    task = None
    if update_task:
        task = get_task_by_filename(client, key)

    project = None
    regexp_tests: List[RegexpTestResult] = []
    if projects is not None:
        project, regexp_tests = _match_project_for_file(key, projects, object_name=object)
        if project is not None:
            if project_stats is not None:
                _update_project_stats(project_stats, project, filter, exposure)
        else:
            if project_tracker is not None:
                project_tracker["files_without_project"] = project_tracker.get("files_without_project", 0) + 1
                files_without_project_names = project_tracker.get("files_without_project_names")
                if isinstance(files_without_project_names, list):
                    files_without_project_names.append(key)

    # Build the compact one-line summary for this file.
    if projects is not None:
        if project is not None:
            status = "matched"
        else:
            status = "unmatched"
    else:
        # Without --projects, fall back to the task status if available,
        # otherwise mark as matched (we still have a file on disk).
        status = "matched" if (not update_task or task) else "unmatched"

    extras: List[str] = []
    if project is not None:
        extras.append(f"project={_project_name(project)!r}")
    if update_task:
        if task:
            extras.append(f"task_id={task[0]}")
        else:
            extras.append("task=none")
    if projects is not None and verbose >= 2 and regexp_tests:
        extras.append(_format_regexp_tests_summary(regexp_tests))

    params = _format_file_params(filter, exposure, object)
    progress = _format_progress(idx, total)
    tag = _format_status_tag(status)
    extras_s = ("  " + " ".join(extras)) if extras else ""
    params_s = ("  " + params) if params else ""
    print(f"{progress}{tag} {fname}{params_s}{extras_s}")

    if show_hdr:
        for k, v in header_items(h):
            print(f"    {k}: {v}")

    if update_task:
        if task:
            task_update(client, fname, task[0], verbose=verbose)
        else:
            task_add(client, fname, verbose=verbose)


def _h_str(h, key: str) -> Optional[str]:
    try:
        v = gets(h, key)
    except Exception:
        return None
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _h_float(h, key: str) -> Optional[float]:
    s = _h_str(h, key)
    if s is None:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _h_int(h, key: str) -> Optional[int]:
    s = _h_str(h, key)
    if s is None:
        return None
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _extract_task_payload_from_header(client: APIClient, h, fname: str) -> Tuple[dict, List[str]]:
    payload = {
        "scope_id": client._scope_id,
        "user_id": client.get_current_user_id(),
        "object": _h_str(h, "OBJECT"),
        "ra": parse_ra(_h_str(h, "OBJCTRA")) if _h_str(h, "OBJCTRA") else None,
        "decl": parse_dec(_h_str(h, "OBJCTDEC")) if _h_str(h, "OBJCTDEC") else None,
        "exposure": _h_float(h, "EXPTIME"),
        "filter": _h_str(h, "FILTER"),
        "binning": _h_int(h, "XBINNING"),
        "imagename": fname,
        "state": 6,
    }

    missing = [k for k in ("user_id", "ra", "decl", "imagename") if payload.get(k) is None]
    payload = {k: v for k, v in payload.items() if v is not None}
    return payload, missing


def task_add(client: APIClient, fname: str, verbose: bool = False):
    """Add a task using header-derived values and POST /api/task-add."""
    h = read_header(fname)
    payload, missing = _extract_task_payload_from_header(client, h, fname)
    if missing:
        print(
            f"Task add skipped for {fname!r}: missing required fields for /api/task-add: {', '.join(missing)}.",
            file=sys.stderr,
        )
        return
    res = client.task_add(payload)
    if verbose:
        print(f"task-add payload={payload!r}")
    if not res.get("status"):
        print(f"Task add failed for {fname!r}: {res.get('msg', 'unknown error')}", file=sys.stderr)
        return
    print(f"  Task created: task_id={res.get('task_id')} for {fname!r}")


def task_update(client: APIClient, fname: str, task_id: int, verbose=False):

    h = read_header(fname)

    payload = {
        "task_id": task_id,
        "object": _h_str(h, "OBJECT"),
        "ra": parse_ra(_h_str(h, "OBJCTRA")) if _h_str(h, "OBJCTRA") else None,
        "decl": parse_dec(_h_str(h, "OBJCTDEC")) if _h_str(h, "OBJCTDEC") else None,
        "exposure": _h_float(h, "EXPTIME"),
        "filter": _h_str(h, "FILTER"),
        "binning": _h_int(h, "XBINNING"),
        "imagename": fname,
        "state": 6,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    res = client.task_update(payload)
    if verbose:
        print(f"task-update payload={payload!r}")
    if not res.get("status"):
        print(f"Task {task_id} update failed: {res.get('msg', 'unknown error')}", file=sys.stderr)
        return
    print(f"  Task updated via API: task_id={task_id}")


def parse_ra(s):
    """ Converts Right Ascension from one format to another: '18 18 49.00'' into 18.123456 """
    dms = s.split(" ")

    ra = float(dms[0])

    minus = ra < 0
    ra = abs(ra)

    ra += float(dms[1]) / 60.0 + float(dms[2]) / 3600.0

    return ra * (1 - 2 * minus)


def parse_dec(s):
    """
    Parse declination.
    """
    return parse_ra(s)


def parse_degms(s):
    """
    Parse degrees/minutes/seconds
    """
    return parse_ra(s)


def sanity_files(cm: ConfigManager, args) -> int:
    """Compare local FITS paths to tasks on the server (via filename suffix match)."""

    update_task = bool(getattr(args, "tasks", False))
    use_projects = bool(getattr(args, "projects", False))
    collect_orphans = bool(getattr(args, "orphans", False))
    verbose = int(getattr(args, "verbose", 0) or 0)
    exclude_patterns = _exclude_patterns_from_config(cm)
    if exclude_patterns:
        print(f"Exclude patterns enabled ({len(exclude_patterns)}): {exclude_patterns}")
    if collect_orphans and not use_projects:
        print("--orphans requires --projects.", file=sys.stderr)
        return 1

    code, client = _require_api(cm, connect=update_task or use_projects)
    if code != 0 or client is None:
        return code
    projects: Optional[List[Dict[str, Any]]] = None
    project_stats: Dict[int, Dict[str, Any]] = {}
    project_tracker: Dict[str, Any] = {
        "files_without_project": 0,
        "files_without_project_names": [] if collect_orphans else None,
    }

    if use_projects:
        scope_id = _scope_id_from_config(cm)
        if scope_id is None:
            print(
                "api.scope_id is not set. Run: hevelius-runner telescope list\n"
                "Then: hevelius-runner telescope set <id_or_name>",
                file=sys.stderr,
            )
            return 1
        try:
            projects = _fetch_projects_list(client, scope_id)
        except Exception as e:
            print(f"Failed to fetch projects list: {e}", file=sys.stderr)
            return 1
        print(f"Project processing enabled: loaded {len(projects)} project(s).")
        if verbose >= 1:
            _print_projects_with_regexps(projects)

    def _scan_kwargs() -> Dict[str, Any]:
        return {"verbose": verbose}

    def _project_kwargs() -> Dict[str, Any]:
        if not use_projects:
            return {}
        return {
            "projects": projects or [],
            "project_stats": project_stats,
            "project_tracker": project_tracker,
        }

    if args.file:
        full_path = _resolve_path(args.file)
        if _is_excluded(full_path, exclude_patterns):
            print(f"Ignoring single file (excluded): {full_path}")
            return 0
        print(f"Processing single file: {full_path}")
        if update_task:
            process_fits_file(
                client, full_path, show_hdr=args.show_header, update_task=True,
                **_project_kwargs(), **_scan_kwargs(),
            )
        else:
            process_fits_file(
                client, full_path, show_hdr=args.show_header,
                **_project_kwargs(), **_scan_kwargs(),
            )
        if use_projects:
            _print_project_stats(
                project_stats,
                project_tracker.get("files_without_project", 0),
                project_tracker.get("files_without_project_names"),
            )
            if not _sync_project_stats_to_server(client, project_stats):
                return 1
        return 0

    if args.list:
        print(f"Processing list of files stored in {args.list}")
        if update_task:
            process_fits_list(
                client,
                args.list,
                show_hdr=args.show_header,
                update_task=True,
                exclude_patterns=exclude_patterns,
                **_project_kwargs(),
                **_scan_kwargs(),
            )
        else:
            process_fits_list(
                client,
                args.list,
                show_hdr=args.show_header,
                exclude_patterns=exclude_patterns,
                **_project_kwargs(),
                **_scan_kwargs(),
            )
        if use_projects:
            _print_project_stats(
                project_stats,
                project_tracker.get("files_without_project", 0),
                project_tracker.get("files_without_project_names"),
            )
            if not _sync_project_stats_to_server(client, project_stats):
                return 1
        return 0

    if args.dir:
        path = args.dir
        print(f"Processing all files in dir: {path}")
        if update_task:
            process_fits_dir(
                client,
                path,
                show_hdr=args.show_header,
                update_task=True,
                exclude_patterns=exclude_patterns,
                **_project_kwargs(),
                **_scan_kwargs(),
            )
        else:
            process_fits_dir(
                client,
                path,
                show_hdr=args.show_header,
                exclude_patterns=exclude_patterns,
                **_project_kwargs(),
                **_scan_kwargs(),
            )
        if use_projects:
            _print_project_stats(
                project_stats,
                project_tracker.get("files_without_project", 0),
                project_tracker.get("files_without_project_names"),
            )
            if not _sync_project_stats_to_server(client, project_stats):
                return 1
        return 0

    volumes = _monitor_volumes_from_config(cm)
    if not volumes:
        rp = _repo_path_from_config(cm)
        if rp is None:
            print(
                "No source paths configured for --sanity-files. Configure paths.volumes "
                "(or legacy paths.fits_monitor_dir).",
                file=sys.stderr,
            )
            return 1
        volumes = [(rp, "repo-path")]

    print(
        f"Processing all {supported_extensions_glob_display()} files "
        f"across {len(volumes)} configured volume(s)."
    )
    for path, nickname in volumes:
        print(f"Volume '{nickname}': {path}")
        if update_task:
            process_fits_dir(
                client,
                path,
                show_hdr=args.show_header,
                update_task=True,
                exclude_patterns=exclude_patterns,
                **_project_kwargs(),
                **_scan_kwargs(),
            )
        else:
            process_fits_dir(
                client,
                path,
                show_hdr=args.show_header,
                exclude_patterns=exclude_patterns,
                **_project_kwargs(),
                **_scan_kwargs(),
            )
    if use_projects:
        _print_project_stats(
            project_stats,
            project_tracker.get("files_without_project", 0),
            project_tracker.get("files_without_project_names"),
        )
        if not _sync_project_stats_to_server(client, project_stats):
            return 1
    return 0


def sanity_db(cm: ConfigManager, args) -> int:
    """Compare tasks from the API to files under ``paths.repo-path``."""

    code, client = _require_api(cm, connect=True)
    if code != 0 or client is None:
        return code

    repo_path = _repo_path_from_config(cm)
    if repo_path is None:
        return 1

    min_task_id = getattr(args, "min_task_id", None)
    max_task_id = getattr(args, "max_task_id", None)
    delete_invalid = getattr(args, "delete_invalid", False)

    print(f"Checking API task list against repository path: {repo_path}")
    if min_task_id is not None or max_task_id is not None:
        print(f"Task ID range: {min_task_id or 'all'} to {max_task_id or 'all'}")
    print(f"Delete invalid tasks: {delete_invalid}")
    print()

    if delete_invalid:
        print(
            "Note: --delete-invalid is not supported: the Hevelius API exposes no task-delete "
            "operation from this client; invalid tasks were not removed.",
            file=sys.stderr,
        )
        print()

    rows = get_tasks_files_list(client)
    tasks = []
    for task_id, imagename in rows:
        if min_task_id is not None and task_id < min_task_id:
            continue
        if max_task_id is not None and task_id > max_task_id:
            continue
        tasks.append((task_id, imagename))

    if not tasks:
        print("No tasks found in the specified range.")
        return 0

    print(f"Found {len(tasks)} tasks to check.")
    print()

    tasks_no_filename: List[int] = []
    tasks_missing_file: List[Tuple[int, str]] = []
    tasks_ok: List[int] = []

    for task_id, imagename in tasks:
        if not imagename:
            tasks_no_filename.append(task_id)
            continue

        file_path = os.path.join(repo_path, imagename)
        if os.path.exists(file_path):
            tasks_ok.append(task_id)
        else:
            tasks_missing_file.append((task_id, imagename))

    print("=== SANITY CHECK RESULTS ===")
    print()

    if tasks_no_filename:
        print(f"Tasks with NO filename specified ({len(tasks_no_filename)}):")
        for task_id in tasks_no_filename:
            print(f"  Task {task_id}")
        print()
    else:
        print("✓ All tasks have filenames specified.")
        print()

    if tasks_missing_file:
        print(f"Tasks with MISSING files on disk ({len(tasks_missing_file)}):")
        for task_id, filename in tasks_missing_file:
            print(f"  Task {task_id}: {filename}")
        print()
    else:
        print("✓ All files referenced by tasks exist on disk.")
        print()

    print(f"Tasks OK: {len(tasks_ok)}")
    print(f"Total issues: {len(tasks_no_filename) + len(tasks_missing_file)}")
    print()

    return 0


def cmd_volumes(cm: ConfigManager, args) -> int:
    """Manages the on disk images repository."""

    if getattr(args, "volumes_cmd", None) == "rename":
        return rename_files(cm, args)

    if args.file or args.list or args.dir or args.all_files:
        return sanity_files(cm, args)

    if args.sanity_db:
        return sanity_db(cm, args)

    print("ERROR: No sanity check selected. Use -d (--dir) or -l (--list) or -f (--file) or -a (--all-files) or --sanity-db to check the repository.")
    return 1
