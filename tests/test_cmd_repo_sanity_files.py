from argparse import Namespace
import builtins
from pathlib import Path

import cmd_volumes


BLUE_HORSEHEAD_FITS = (
    Path(__file__).parent
    / "data"
    / "2026-06-12_21-38-51_blue horsehead_OIII_300.00s_LIGHT_0065.fits"
)


class _DummyConfigManager:
    loaded = True

    def get_paths_config(self):
        return {}


def _base_args(**overrides):
    args = Namespace(
        file=None,
        list=None,
        dir=None,
        show_header=False,
        tasks=False,
        projects=False,
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def test_sanity_files_specific_file(monkeypatch):
    cm = _DummyConfigManager()
    calls = []

    require_api_connect = {"value": None}

    def _fake_require_api(_cm, connect=False):
        require_api_connect["value"] = connect
        return 0, object()

    monkeypatch.setattr(cmd_volumes, "_require_api", _fake_require_api)
    monkeypatch.setattr(
        cmd_volumes,
        "process_fits_file",
        lambda client, fname, show_hdr=False, update_task=False, **kwargs: calls.append(
            (client, fname, show_hdr, update_task)
        ),
    )

    ret = cmd_volumes.sanity_files(cm, _base_args(file=r"c:\repo\one.fits", show_header=True))
    assert ret == 0
    assert len(calls) == 1
    assert calls[0][1] == r"c:\repo\one.fits"
    assert calls[0][2] is True


def test_sanity_files_list_file(monkeypatch):
    cm = _DummyConfigManager()
    calls = []

    monkeypatch.setattr(cmd_volumes, "_require_api", lambda _cm, connect=False: (0, object()))
    monkeypatch.setattr(
        cmd_volumes,
        "process_fits_list",
        lambda client, fname, show_hdr=False, **kwargs: calls.append(
            (client, fname, show_hdr, kwargs)
        ),
    )

    ret = cmd_volumes.sanity_files(cm, _base_args(list=r"c:\tmp\fits_list.txt"))
    assert ret == 0
    assert len(calls) == 1
    assert calls[0][1] == r"c:\tmp\fits_list.txt"


def test_sanity_files_specific_directory(monkeypatch):
    cm = _DummyConfigManager()
    calls = []

    monkeypatch.setattr(cmd_volumes, "_require_api", lambda _cm, connect=False: (0, object()))
    monkeypatch.setattr(
        cmd_volumes,
        "process_fits_dir",
        lambda client, path, show_hdr=False, **kwargs: calls.append(
            (client, path, show_hdr, kwargs)
        ),
    )

    ret = cmd_volumes.sanity_files(cm, _base_args(dir=r"c:\astro\night1", show_header=True))
    assert ret == 0
    assert len(calls) == 1
    assert calls[0][1] == r"c:\astro\night1"
    assert calls[0][2] is True


def test_sanity_files_defaults_to_all_configured_volumes(monkeypatch):
    cm = _DummyConfigManager()
    calls = []
    volumes = [(r"c:\astro\live", "live"), (r"d:\astro\archive", "archive")]

    monkeypatch.setattr(cmd_volumes, "_require_api", lambda _cm, connect=False: (0, object()))
    monkeypatch.setattr(cmd_volumes, "_monitor_volumes_from_config", lambda _cm: volumes)
    monkeypatch.setattr(
        cmd_volumes,
        "process_fits_dir",
        lambda client, path, show_hdr=False, **kwargs: calls.append(path),
    )

    ret = cmd_volumes.sanity_files(cm, _base_args())
    assert ret == 0
    assert calls == [r"c:\astro\live", r"d:\astro\archive"]


def test_process_fits_list_skips_excluded_full_path(monkeypatch):
    calls = []

    monkeypatch.setattr(
        cmd_volumes,
        "process_fits_file",
        lambda client, fname, show_hdr=False, update_task=False, **kwargs: calls.append(fname),
    )

    listed = [
        r"C:\astro\night\good_001.fits",
        r"C:\astro\night\FLAT_001.fits",
        r"C:\astro\night\also_shit_001.fits",
    ]

    def _fake_open(*args, **kwargs):
        class _F:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                return False

            def readlines(self_inner):
                return [f"{line}\n" for line in listed]

        return _F()

    monkeypatch.setattr(builtins, "open", _fake_open)

    cmd_volumes.process_fits_list(
        client=object(),
        fname="ignored.txt",
        show_hdr=False,
        exclude_patterns=["*FLAT*", "*shit*"],
    )

    assert len(calls) == 1
    assert calls[0].lower().endswith(r"good_001.fits")


def test_sanity_files_with_project_prefetches_and_prints_stats(monkeypatch, capsys):
    cm = _DummyConfigManager()
    calls = []
    volumes = [(r"c:\astro\live", "live")]

    require_api_connect = {"value": None}

    def _fake_require_api(_cm, connect=False):
        require_api_connect["value"] = connect
        return 0, object()

    monkeypatch.setattr(cmd_volumes, "_require_api", _fake_require_api)
    monkeypatch.setattr(cmd_volumes, "_scope_id_from_config", lambda _cm: 3)
    monkeypatch.setattr(cmd_volumes, "_fetch_projects_list", lambda client, scope_id: [{"project_id": 42, "name": "M42", "subframes": []}])
    monkeypatch.setattr(cmd_volumes, "_monitor_volumes_from_config", lambda _cm: volumes)
    monkeypatch.setattr(cmd_volumes, "_sync_project_stats_to_server", lambda client, stats: True)

    def _fake_process_dir(client, path, show_hdr=False, **kwargs):
        calls.append((path, kwargs))
        kwargs["project_stats"][42] = {
            "name": "M42",
            "project": {"project_id": 42, "name": "M42", "subframes": []},
            "buckets": {("Ha", 300.0): 2},
        }
        kwargs["project_tracker"]["files_without_project"] = 1

    monkeypatch.setattr(cmd_volumes, "process_fits_dir", _fake_process_dir)

    ret = cmd_volumes.sanity_files(cm, _base_args(projects=True))
    assert ret == 0
    assert require_api_connect["value"] is True
    assert len(calls) == 1
    assert calls[0][0] == r"c:\astro\live"
    assert calls[0][1]["projects"] == [{"project_id": 42, "name": "M42", "subframes": []}]
    out = capsys.readouterr().out
    assert "PROJECT STATISTICS" in out
    assert "Files without project match: 1" in out
    # Per-project bucket lines are emitted by _sync_project_stats_to_server
    # which is mocked away in this test, so we only assert the orphan-files
    # header section here.


def test_process_fits_file_project_found_updates_stats(monkeypatch, capsys):
    monkeypatch.setattr(cmd_volumes, "read_fits", lambda fname: {"FILTER": "Ha", "EXPTIME": 300, "OBJECT": "x"})
    monkeypatch.setattr(cmd_volumes, "get_task_by_filename", lambda client, key: None)

    project_stats = {}
    tracker = {"files_without_project": 0}
    cmd_volumes.process_fits_file(
        client=object(),
        fname=r"c:\repo\M42_001.fits",
        show_hdr=False,
        projects=[{"project_id": 42, "name": "M42", "subframes": []}],
        project_stats=project_stats,
        project_tracker=tracker,
    )
    out = capsys.readouterr().out
    assert "[matched" in out
    assert "project='M42'" in out
    assert "M42_001.fits" in out
    assert project_stats[42]["buckets"][("Ha", 300.0)] == 1
    assert tracker["files_without_project"] == 0


def test_process_fits_file_project_not_found_tracks_counter(monkeypatch, capsys):
    monkeypatch.setattr(cmd_volumes, "read_fits", lambda fname: {"FILTER": "OIII", "EXPTIME": 120, "OBJECT": "x"})
    monkeypatch.setattr(cmd_volumes, "get_task_by_filename", lambda client, key: None)

    project_stats = {}
    tracker = {"files_without_project": 0}
    cmd_volumes.process_fits_file(
        client=object(),
        fname=r"c:\repo\unknown_001.fits",
        show_hdr=False,
        projects=[{"name": "M42"}],
        project_stats=project_stats,
        project_tracker=tracker,
    )
    out = capsys.readouterr().out
    assert "[unmatched" in out
    assert "unknown_001.fits" in out
    assert project_stats == {}
    assert tracker["files_without_project"] == 1


def test_find_project_for_filename_uses_regexps():
    projects = [
        {"project_id": 1, "name": "M31", "regexps": "^M31_"},
        {"project_id": 2, "name": "M42", "regexps": "M42"},
    ]
    assert cmd_volumes._find_project_for_filename("M31_001.fits", projects)["project_id"] == 1
    assert cmd_volumes._find_project_for_filename("data_M42_stack.fits", projects)["project_id"] == 2
    assert cmd_volumes._find_project_for_filename("unknown.fits", projects) is None


def test_find_project_for_filename_falls_back_to_name_without_regexps():
    projects = [{"project_id": 42, "name": "M42"}]
    assert cmd_volumes._find_project_for_filename("M42_001.fits", projects)["project_id"] == 42


def test_blue_horsehead_matches_project_name_in_filename():
    assert BLUE_HORSEHEAD_FITS.is_file()
    project = {"project_id": 7, "name": "blue horsehead"}
    matched = cmd_volumes._find_project_for_filename(str(BLUE_HORSEHEAD_FITS), [project])
    assert matched is not None
    assert matched["project_id"] == 7


def test_blue_horsehead_matches_project_regexp_against_object_header():
    assert BLUE_HORSEHEAD_FITS.is_file()
    project = {"project_id": 7, "name": "unrelated", "regexps": "IC.4592"}
    matched = cmd_volumes._find_project_for_filename(
        str(BLUE_HORSEHEAD_FITS),
        [project],
        object_name="IC 4592",
    )
    assert matched is not None
    assert matched["project_id"] == 7


def test_blue_horsehead_process_fits_file_matches_combined_project(capsys):
    assert BLUE_HORSEHEAD_FITS.is_file()
    project = {"project_id": 7, "name": "blue horsehead", "regexps": "IC.4592", "subframes": []}
    project_stats = {}
    tracker = {"files_without_project": 0}

    cmd_volumes.process_fits_file(
        client=object(),
        fname=str(BLUE_HORSEHEAD_FITS),
        show_hdr=False,
        verbose=2,
        projects=[project],
        project_stats=project_stats,
        project_tracker=tracker,
    )

    out = capsys.readouterr().out
    assert "[matched" in out
    assert str(BLUE_HORSEHEAD_FITS) in out
    assert "project='blue horsehead'" in out
    assert "regexps:" in out
    assert "'IC.4592'/7:match" in out
    assert "'blue horsehead'/7:match" in out
    assert project_stats[7]["buckets"][("OIII", 300.0)] == 1
    assert tracker["files_without_project"] == 0


def test_process_fits_file_verbose_shows_regexp_details(monkeypatch, capsys):
    monkeypatch.setattr(cmd_volumes, "read_fits", lambda fname: {"FILTER": "Ha", "EXPTIME": 300, "OBJECT": "x"})
    monkeypatch.setattr(cmd_volumes, "get_task_by_filename", lambda client, key: None)

    cmd_volumes.process_fits_file(
        client=object(),
        fname=r"c:\repo\M31_001.fits",
        show_hdr=False,
        verbose=2,
        projects=[
            {"project_id": 1, "name": "M31", "regexps": "^M31_"},
            {"project_id": 2, "name": "M42", "regexps": "M42"},
        ],
    )
    out = capsys.readouterr().out
    assert "regexps:" in out
    assert "'^M31_'/1:match" in out
    assert "'M42'/2:no match" in out


def test_sanity_files_verbose_lists_projects_with_regexps(monkeypatch, capsys):
    cm = _DummyConfigManager()
    volumes = [(r"c:\astro\live", "live")]

    monkeypatch.setattr(cmd_volumes, "_require_api", lambda _cm, connect=False: (0, object()))
    monkeypatch.setattr(cmd_volumes, "_scope_id_from_config", lambda _cm: 3)
    monkeypatch.setattr(
        cmd_volumes,
        "_fetch_projects_list",
        lambda client, scope_id: [
            {"project_id": 1, "name": "M31", "regexps": "^M31_"},
            {"project_id": 2, "name": "M42"},
        ],
    )
    monkeypatch.setattr(cmd_volumes, "_monitor_volumes_from_config", lambda _cm: volumes)
    monkeypatch.setattr(cmd_volumes, "_sync_project_stats_to_server", lambda client, stats: True)
    monkeypatch.setattr(cmd_volumes, "process_fits_dir", lambda *args, **kwargs: None)

    ret = cmd_volumes.sanity_files(cm, _base_args(projects=True, verbose=1))
    assert ret == 0
    out = capsys.readouterr().out
    assert "Projects and regexps:" in out
    assert "project_id=1\tM31\tregexps=^M31_" in out
    assert "project_id=2\tM42\tregexps=(name only)" in out


class _FakeResponse:
    def __init__(self, payload=None):
        self._payload = payload or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    """Test double for ``requests.Session`` used by the runner.

    Records POST/PATCH/GET calls and lets each test inject a stable response
    payload for the GET /api/projects/{id} fresh-fetch the runner now performs.
    """

    def __init__(self, get_payload=None):
        self.post_calls = []
        self.patch_calls = []
        self.get_calls = []
        self._get_payload = get_payload

    def post(self, url, json=None, timeout=None, headers=None):
        self.post_calls.append((url, json, timeout, headers))
        return _FakeResponse()

    def patch(self, url, json=None, timeout=None, headers=None):
        self.patch_calls.append((url, json, timeout, headers))
        return _FakeResponse()

    def get(self, url, timeout=None, headers=None):
        self.get_calls.append((url, timeout, headers))
        return _FakeResponse(self._get_payload)


def _make_client(session):
    return type(
        "C",
        (),
        {
            "base_url": "https://example.test/api/",
            "timeout": 5,
            "session": session,
            "_get_auth_headers": lambda self: {"Authorization": "Bearer x"},
        },
    )()


def test_sync_project_stats_creates_missing_subframe():
    session = _FakeSession(get_payload={"status": True, "project": {"project_id": 42, "name": "M42", "subframes": []}})
    client = _make_client(session)
    stats = {
        42: {
            "name": "M42",
            "project": {"project_id": 42, "name": "M42", "subframes": []},
            "buckets": {("Ha", 300.0): 3},
        }
    }
    ok = cmd_volumes._sync_project_stats_to_server(client, stats)
    assert ok is True
    assert len(session.post_calls) == 1
    assert session.post_calls[0][0].endswith("/projects/42/subframes")
    assert session.post_calls[0][1]["filter"] == "Ha"
    assert session.post_calls[0][1]["count"] == 3
    assert "goal_count" not in session.post_calls[0][1]
    assert "active" not in session.post_calls[0][1]
    assert session.patch_calls == []


def test_sync_project_stats_updates_existing_subframe_count_only():
    fresh = {
        "project_id": 42, "name": "M42",
        "subframes": [
            {"id": 77, "filter": {"short_name": "Ha"}, "exposure_time": 300.0, "count": 1, "goal_count": 10}
        ],
    }
    session = _FakeSession(get_payload={"status": True, "project": fresh})
    client = _make_client(session)
    stats = {
        42: {
            "name": "M42",
            "project": {
                "project_id": 42,
                "name": "M42",
                "subframes": [
                    {"id": 77, "filter": {"short_name": "Ha"}, "exposure_time": 300.0, "count": 1, "goal_count": 10}
                ],
            },
            "buckets": {("Ha", 300.0): 5},
        }
    }
    ok = cmd_volumes._sync_project_stats_to_server(client, stats)
    assert ok is True
    assert session.post_calls == []
    assert len(session.patch_calls) == 1
    assert session.patch_calls[0][0].endswith("/projects/42/subframes/77")
    assert session.patch_calls[0][1] == {"count": 5}
    # Runner re-fetches the project right before sync so it compares against
    # fresh server state instead of a possibly stale cached copy.
    assert len(session.get_calls) == 1
    assert session.get_calls[0][0].endswith("/projects/42")


def test_sync_project_stats_skips_when_count_unchanged(capsys):
    """No PATCH is issued when server count already matches the bucket count."""
    fresh = {
        "project_id": 42, "name": "M42",
        "subframes": [
            {"id": 77, "filter": {"short_name": "Ha"}, "exposure_time": 300.0, "count": 5, "goal_count": 10}
        ],
    }
    session = _FakeSession(get_payload={"status": True, "project": fresh})
    client = _make_client(session)
    stats = {
        42: {
            "name": "M42",
            "project": {"project_id": 42, "name": "M42", "subframes": fresh["subframes"]},
            "buckets": {("Ha", 300.0): 5},
        }
    }
    ok = cmd_volumes._sync_project_stats_to_server(client, stats)
    assert ok is True
    assert session.patch_calls == []
    assert session.post_calls == []
    out = capsys.readouterr().out
    assert "skipped" in out
    assert "goal_count=10" in out


def test_sync_project_stats_uses_fresh_data_when_cache_is_stale(capsys):
    """The fresh GET trumps the stale cached project so we don't double-PATCH."""
    fresh = {
        "project_id": 42, "name": "M42",
        "subframes": [
            {"id": 77, "filter": {"short_name": "Ha"}, "exposure_time": 300.0, "count": 7, "goal_count": 10}
        ],
    }
    session = _FakeSession(get_payload={"status": True, "project": fresh})
    client = _make_client(session)
    stats = {
        42: {
            "name": "M42",
            # Cached count is 1 (stale) but server now reports 7 == bucket → skip.
            "project": {
                "project_id": 42, "name": "M42",
                "subframes": [{"id": 77, "filter": {"short_name": "Ha"}, "exposure_time": 300.0, "count": 1, "goal_count": 10}],
            },
            "buckets": {("Ha", 300.0): 7},
        }
    }
    ok = cmd_volumes._sync_project_stats_to_server(client, stats)
    assert ok is True
    assert session.patch_calls == []
    out = capsys.readouterr().out
    assert "skipped" in out


def test_sync_project_stats_color_codes_at_or_above_goal(capsys):
    """When count >= goal_count the line uses the green ANSI sequence."""
    fresh = {
        "project_id": 42, "name": "M42",
        "subframes": [
            {"id": 77, "filter": {"short_name": "Ha"}, "exposure_time": 300.0, "count": 1, "goal_count": 10}
        ],
    }
    session = _FakeSession(get_payload={"status": True, "project": fresh})
    client = _make_client(session)
    stats = {
        42: {
            "name": "M42",
            "project": {"project_id": 42, "name": "M42", "subframes": fresh["subframes"]},
            "buckets": {("Ha", 300.0): 12},  # exceeds goal_count=10 → green
        }
    }
    cmd_volumes._sync_project_stats_to_server(client, stats)
    assert len(session.patch_calls) == 1
    out = capsys.readouterr().out
    assert "updated" in out
    assert "count=12" in out
    assert "goal_count=10" in out
