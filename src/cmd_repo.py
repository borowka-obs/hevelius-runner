"""
Code that handles files repository on disk.
"""
import glob
import logging
import os
import sys
from astropy.io import fits
from typing import List, Optional, Tuple

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

def process_fits_list(client: APIClient, fname: str, show_hdr: bool, dry_run: bool) -> None:
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
        process_fits_file(client, line, show_hdr=show_hdr, dry_run=dry_run)
        cnt += 1


def process_fits_dir(client: APIClient, dir: str, show_hdr: bool, dry_run: bool) -> None:
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
        process_fits_file(client, str(f), show_hdr, dry_run)
        cnt += 1


def task_add(client: APIClient, fname):
    """Adds a new task based on a image filename, specified by fname. The
       filename parsing is already done by parse_iteleskop_name() and stored in
       details dict."""



def process_fits_file(client: APIClient, fname, verbose=False, show_hdr=False, dry_run=False):
    """Processes a FITS file: optional header dump and task lookup via the API."""
    key = os.path.basename(fname)
    task = get_task_by_filename(client, key)
    if task:
        tid, imagename = task
        print(f"  Task found: task_id={tid} imagename={imagename!r} (matched suffix {key!r})")
    else:
        print(f"  No task found for filename suffix {key!r}")

    if show_hdr:
        h = read_fits(fname)
        for k in h.keys():
            print(f"    {k}: {h[k]}")

    if verbose and task:
        task_update_params(client, fname, task[0], verbose=verbose, dry_run=dry_run)


def task_update_params(client: APIClient, fname: str, task_id: int, verbose=False, dry_run=False):

    h = read_fits(fname)

    if verbose:
        print(f"Header file: {repr(h)}")

    query = "UPDATE tasks SET "

    query += get_int_header(h, "he_resx", "NAXIS1")
    query += get_int_header(h, "he_resy", "NAXIS2")

    query += f"he_obsstart='{gets(h, 'DATE-OBS')}', "
    query += f"he_exposure={getf(h, 'EXPTIME')}, "

    query += get_float_header(h, "he_settemp", "SET-TEMP")
    query += get_float_header(h, "he_ccdtemp", "CCD-TEMP")

    query += f"he_pixwidth={getf(h, 'XPIXSZ')}, "
    query += f"he_pixheight={getf(h, 'YPIXSZ')}, "
    query += f"he_xbinning={geti(h, 'XBINNING')}, "
    query += f"he_ybinning={geti(h, 'YBINNING')}, "
    query += f"he_filter='{gets(h, 'FILTER')}', "

    if "OBJCTRA" in h:
        query += f"he_objectra={parse_ra(gets(h, 'OBJCTRA'))}, "
        query += f"he_objectdec={parse_dec(gets(h, 'OBJCTDEC'))}, "

    query += get_float_header(h, "he_objectalt", "OBJCTALT")
    query += get_float_header(h, "he_objectaz", "OBJCTAZ")
    query += get_float_header(h, "he_objectha", "OBJCTHA")
    query += get_string_header(h, "he_pierside", "PIERSIDE")

    query += f"he_site_lat={parse_degms(gets(h, 'SITELAT'))}, "
    query += f"he_site_lon={parse_degms(gets(h, 'SITELONG'))}, "

    query += f"he_jd={getf(h, 'JD')}, "

    query += get_float_header(h, "he_jd_helio", "JD-HELIO")

    query += get_float_header(h, "he_tracktime", "TRAKTIME")

    query += f"he_focal={getf(h, 'FOCALLEN')}, "
    query += f"he_aperture_diam={getf(h, 'APTDIA')}, "
    query += f"he_aperture_area={getf(h, 'APTAREA')}, "
    query += f"he_scope='{gets(h, 'TELESCOP')}', "
    query += f"he_camera='{gets(h, 'INSTRUME')}', "

    query += get_float_header(h, "he_moon_alt", 'MOONWYS')
    query += get_float_header(h, "he_moon_angle", 'MOONKAT')
    query += get_float_header(h, "he_moon_phase", 'MOONFAZA')
    query += get_float_header(h, "he_sun_alt", 'SUN')
    # sets he_solved, he_solved_ra, he_solved_dec, he_solved_x, he_solved_y
    query += parse_solved(h)

    query += parse_quality(h)  # gets FWHM, number of stars recognized

    # meaningless, but it's hard to tell if q ends with a , or not at this point.
    query += " task_id=task_id"

    query += f" WHERE task_id={task_id};"

    if verbose:
        print(query, file=sys.stderr)

    if dry_run:
        print(f"Task {task_id} update skipped (--dry-run).")
    else:
        print(
            f"Task {task_id}: FITS-derived SQL update is not sent to the API "
            f"(no task column-update endpoint in client); query was not executed.",
            file=sys.stderr,
        )
        if verbose:
            print(query, file=sys.stderr)


def get_int_header(header, sql, header_name):
    """
    Returns specified integer field from the header
    """
    if header_name not in header or not len(str(header[header_name])):
        return ""
    return "%s=%i, " % (sql, geti(header, header_name))


def get_float_header(header, sql, header_name):
    """
    Returns specified float field from the header
    """
    if header_name not in header or not len(str(header[header_name])):
        return ""
    return "%s=%f, " % (sql, getf(header, header_name))


def get_string_header(header, sql, header_name):
    """
    Returns specified string field from the header
    """
    if header_name not in header or not len(str(header[header_name])):
        return ""
    return "%s='%s', " % (sql, gets(header, header_name))


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


def parse_solved(h):
    """
    Returns string formatting that specifies if the frame was solved or not.
    """

    # Here's example FITS header this code is supposed to parse.
    # PA      =   6.40789182622E+001 / [deg, 0-360 CCW] Position angle of plate
    # CTYPE1  = 'RA---TAN'           / X-axis coordinate type
    # CRVAL1  =   2.74719564502E+002 / X-axis coordinate value
    # CRPIX1  =   2.04800000000E+003 / X-axis reference pixel
    # CDELT1  =  -1.77681403340E-004 / [deg/pixel] X-axis plate scale
    # CROTA1  =  -6.40789182622E+001 / [deg] Roll angle wrt X-axis
    # CTYPE2  = 'DEC--TAN'           / Y-axis coordinate type
    # CRVAL2  =  -1.37998534456E+001 / Y-axis coordinate value
    # CRPIX2  =   2.04800000000E+003 / Y-axis reference pixel
    # CDELT2  =  -1.77675999978E-004 / [deg/pixel] Y-Axis Plate scale
    # CROTA2  =  -6.40789182622E+001 / [deg] Roll angle wrt Y-axis
    # CD1_1   =  -7.76703599758E-005 / Change in RA---TAN along X-Axis
    # CD1_2   =  -1.59801261123E-004 / Change in RA---TAN along Y-Axis
    # CD2_1   =   1.59806120891E-004 / Change in DEC--TAN along X-Axis
    # CD2_2   =  -7.76679979895E-005 / Change in DEC--TAN along Y-Axis

    if "PLTSOLVD" not in h:
        return "he_solved=0, "

    solved = h["PLTSOLVD"]
    if not solved:
        return "he_solved=0, "

    # Ok, the header claims it's solved. Let's try to find it out
    q = "he_solved=1, "

    # Let's check if the first parameter is RA
    if not h["CTYPE1"] or h["CTYPE1"] != 'RA---TAN':
        print("Can't parse solved RA.")
        return "he_solved=2, "

    ra = float(h["CRVAL1"])

    # Now check declination
    if not h["CTYPE2"] or h["CTYPE2"] != 'DEC--TAN':
        print("Can't parse solved DEC.")
        return "he_solved=2, "

    dec = float(h["CRVAL2"])

    # Ok, now parse the x-axis reference pixel
    refx = int(h["CRPIX1"])
    refy = int(h["CRPIX2"])

    pixscalex = float(h["CDELT1"]) * 3600  # arcsec/pix in x direction
    pixscaley = float(h["CDELT2"]) * 3600  # arcsec/pix in y direction

    q += "he_solved_ra=%f, he_solved_dec=%f, he_solved_refx=%d, he_solved_refy=%d, he_pixscalex=%f, he_pixscaley=%f, " \
         % (ra, dec, refx, refy, pixscalex, pixscaley)

    # CD1_1   =  -7.76703599758E-005 / Change in RA---TAN along X-Axis
    # CD1_2   =  -1.59801261123E-004 / Change in RA---TAN along Y-Axis
    # CD2_1   =   1.59806120891E-004 / Change in DEC--TAN along X-Axis
    # CD2_2   =  -7.76679979895E-005 / Change in DEC--TAN along Y-Axis
    ra_change_x = float(h["CD1_1"])
    ra_change_y = float(h["CD1_2"])
    dec_change_x = float(h["CD2_1"])
    dec_change_y = float(h["CD2_2"])

    q += "he_solved_ra_change_x=%f, he_solved_ra_change_y=%f, he_solved_dec_change_x=%f, he_solved_dec_change_y=%f, " \
        % (ra_change_x, ra_change_y, dec_change_x, dec_change_y)

    return q


def parse_quality(header):

    q = ""
    if "FWHM" in header:
        q = f"he_fwhm={getf(header, 'FWHM')}, "

    if "HISTORY" not in header:
        return q

    for h in header["HISTORY"]:
        # There may be many HISTORY entries. We're looking for the one looking like this:
        # Matched 139 stars from the USNO UCAC4 Catalog
        if h.find("Matched ") == -1 or h.find("stars from the") == -1:
            continue

        h = h.strip()
        x = h.split(" ")
        stars = int(x[1])
        q += f"he_stars={stars}, "
        break

    return q


def gets(header, param):
    return header[param]


def getf(header, param):
    return float(header[param])


def geti(header, param):
    return int(header[param])


def read_fits(filename):
    """ Reads FITS file, returns its header content """

    hdul = fits.open(filename)

    return hdul[0].header


def sanity_files(cm: ConfigManager, args) -> int:
    """Compare local FITS paths to tasks on the server (via filename suffix match)."""

    code, client = _require_api(cm)
    if code != 0 or client is None:
        return code

    if args.file:
        print(f"Processing single file: {args.file}")
        process_fits_file(client, args.file, show_hdr=args.show_header, dry_run=args.dry_run)
        return 0

    if args.list:
        print(f"Processing list of files stored in {args.list}")
        process_fits_list(client, args.list, show_hdr=args.show_header, dry_run=args.dry_run)
        return 0

    if args.dir:
        path = args.dir
    else:
        rp = _repo_path_from_config(cm)
        if rp is None:
            return 1
        path = rp

    print(f"Processing all *.fit files in dir: {path}")
    process_fits_dir(client, path, show_hdr=args.show_header, dry_run=args.dry_run)
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


def cmd_repo(cm: ConfigManager, args) -> int:
    """Manages the on disk images repository."""

    code = _require_loaded(cm)
    if code != 0:
        return code

    if args.sanity_files:
        return sanity_files(cm, args)

    if args.sanity_db:
        return sanity_db(cm, args)

    print("ERROR: No sanity check selected. Use --sanity-files or --sanity-db to check the repository.")
    return 1
