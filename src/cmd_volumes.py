"""
Code that handles files repository on disk.
"""
import glob
import logging
import os
import sys
from typing import List, Optional, Tuple

from fits import (
    gets,
    read_fits,
)

from api_client import APIClient
from config_manager import ConfigManager


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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    client = APIClient(api_cfg)
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

def process_fits_list(client: APIClient, fname: str, show_hdr: bool, dry_run: bool, update_task: bool) -> None:
    """
    Processes all FITS files listed in a specified text file.

    :param fname: name of a text file that contains a list of files to be loaded
    :param show_hdr: bool governing whether FITS headers will be printed or not
    :param dry_run: bool governing if DB changes are to be done or not.
    """

    with open(fname, encoding="utf-8") as f:
        lines = f.readlines()

    total = len(lines)
    print(f"Found {total} filename(s) in file {fname}")

    cnt = 1
    for line in lines:
        line = line.strip()
        if len(line) == 0 or line[0] == "#":
            # Skip empty and commented out lines
            continue

        print(f"Processing file {cnt} of {total}: {line}")
        process_fits_file(client, line, show_hdr=show_hdr, dry_run=dry_run, update_task=update_task)
        cnt += 1


def process_fits_dir(client: APIClient, dir: str, show_hdr: bool, dry_run: bool, update_task: bool) -> None:
    """
    Processes all FITS files in specified directory.

    :param dir: directory to be traversed
    :param show_hdr: bool governing whether FITS headers will be printed or not
    :param dry_run: bool governing if DB changes are to be done or not.
    """

    base = os.path.normpath(dir)
    pattern_fit = os.path.join(base, "**", "*.fit")
    pattern_fits = os.path.join(base, "**", "*.fits")
    print(f"patterns={pattern_fit!r}, {pattern_fits!r}")
    found_fit = glob.glob(pattern_fit, recursive=True)
    found_fits = glob.glob(pattern_fits, recursive=True)
    files = sorted(set(found_fit) | set(found_fits))

    print(f"Found {len(files)} files(s) in directory {dir}")

    cnt = 1
    total = len(files)

    for f in files:
        print(f"Processing file {cnt} of {total}: {f}")
        process_fits_file(client, str(f), show_hdr, dry_run=dry_run, update_task=update_task)
        cnt += 1


def process_fits_file(
    client: APIClient,
    fname,
    show_hdr: bool,
    verbose: bool = False,
    dry_run: bool = False,
    update_task: bool = False,
):
    """Processes a FITS file: optional header dump and task lookup via the API."""

    key = os.path.basename(fname)

    # Extract file parameters from the header
    h = read_fits(fname)
    filter = _h_str(h, "FILTER")
    object = _h_str(h, "OBJECT")

    task = get_task_by_filename(client, key)
    if task:
        tid, imagename = task
        print(f"  Task found: task_id={tid} imagename={imagename!r} (matched suffix {key!r}), filter={filter}, object={object}")
    else:
        print(f"  No task found for filename suffix {key!r}, filter={filter}, object={object}")

    if show_hdr:
        for k in h.keys():
            print(f"    {k}: {h[k]}")

    # OK, so we have a file on disk and there might or might not be a task for it.
    # TODO: add ability to insert new or update existing task.

    if not update_task:
        print("  Task DB update skipped (pass --task to enable API upsert).")
        return

    if dry_run:
        print("  Task DB update skipped (--dry-run).")
        return

    if task:
        task_update(client, fname, task[0], verbose=verbose)
        return
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
    """Add a task using FITS-derived values and POST /api/task-add."""
    h = read_fits(fname)
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

    h = read_fits(fname)

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

    code, client = _require_api(cm)
    if code != 0 or client is None:
        return code

    if args.file:
        print(f"Processing single file: {args.file}")
        process_fits_file(client, args.file, show_hdr=args.show_header, dry_run=args.dry_run, update_task=args.task)
        return 0

    if args.list:
        print(f"Processing list of files stored in {args.list}")
        process_fits_list(client, args.list, show_hdr=args.show_header, dry_run=args.dry_run, update_task=args.task)
        return 0

    if args.dir:
        path = args.dir
        print(f"Processing all files in dir: {path}")
        process_fits_dir(client, path, show_hdr=args.show_header, dry_run=args.dry_run, update_task=args.task)
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

    print(f"Processing all *.fit/*.fits files across {len(volumes)} configured volume(s).")
    for path, nickname in volumes:
        print(f"Volume '{nickname}': {path}")
        process_fits_dir(client, path, show_hdr=args.show_header, dry_run=args.dry_run, update_task=args.task)
    return 0


def sanity_db(cm: ConfigManager, args) -> int:
    """Compare tasks from the API to files under ``paths.repo-path``."""

    code, client = _require_api(cm)
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

    if args.file or args.list or args.dir or args.all_files:
        return sanity_files(cm, args)

    if args.sanity_db:
        return sanity_db(cm, args)

    print("ERROR: No sanity check selected. Use -d (--dir) or -l (--list) or -f (--file) or -a (--all-files) or --sanity-db to check the repository.")
    return 1
