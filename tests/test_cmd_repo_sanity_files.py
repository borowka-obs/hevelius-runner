from argparse import Namespace
import builtins

import cmd_volumes


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
        lambda client, fname, show_hdr=False, update_task=False: calls.append(
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
    assert "Project: M42" in out
    assert "filter=Ha exposure=300.0 -> 2" in out


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
    assert "Project found: 'M42'" in out
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
    assert "Project not found" in out
    assert project_stats == {}
    assert tracker["files_without_project"] == 1


class _FakeResponse:
    def raise_for_status(self):
        return None


class _FakeSession:
    def __init__(self):
        self.post_calls = []
        self.patch_calls = []

    def post(self, url, json=None, timeout=None, headers=None):
        self.post_calls.append((url, json, timeout, headers))
        return _FakeResponse()

    def patch(self, url, json=None, timeout=None, headers=None):
        self.patch_calls.append((url, json, timeout, headers))
        return _FakeResponse()


def test_sync_project_stats_creates_missing_subframe():
    session = _FakeSession()
    client = type(
        "C",
        (),
        {
            "base_url": "https://example.test/api/",
            "timeout": 5,
            "session": session,
            "_get_auth_headers": lambda self: {"Authorization": "Bearer x"},
        },
    )()
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
    session = _FakeSession()
    client = type(
        "C",
        (),
        {
            "base_url": "https://example.test/api/",
            "timeout": 5,
            "session": session,
            "_get_auth_headers": lambda self: {"Authorization": "Bearer x"},
        },
    )()
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
