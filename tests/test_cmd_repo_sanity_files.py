from argparse import Namespace

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
        dry_run=False,
        task=False,
        project=False,
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def test_sanity_files_specific_file(monkeypatch):
    cm = _DummyConfigManager()
    calls = []

    monkeypatch.setattr(cmd_volumes, "_require_api", lambda _cm: (0, object()))
    monkeypatch.setattr(
        cmd_volumes,
        "process_fits_file",
        lambda client, fname, show_hdr=False, dry_run=False: calls.append(
            (client, fname, show_hdr, dry_run)
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

    monkeypatch.setattr(cmd_volumes, "_require_api", lambda _cm: (0, object()))
    monkeypatch.setattr(
        cmd_volumes,
        "process_fits_list",
        lambda client, fname, show_hdr=False, dry_run=False: calls.append(
            (client, fname, show_hdr, dry_run)
        ),
    )

    ret = cmd_volumes.sanity_files(cm, _base_args(list=r"c:\tmp\fits_list.txt", dry_run=True))
    assert ret == 0
    assert len(calls) == 1
    assert calls[0][1] == r"c:\tmp\fits_list.txt"
    assert calls[0][3] is True


def test_sanity_files_specific_directory(monkeypatch):
    cm = _DummyConfigManager()
    calls = []

    monkeypatch.setattr(cmd_volumes, "_require_api", lambda _cm: (0, object()))
    monkeypatch.setattr(
        cmd_volumes,
        "process_fits_dir",
        lambda client, path, show_hdr=False, dry_run=False: calls.append(
            (client, path, show_hdr, dry_run)
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

    monkeypatch.setattr(cmd_volumes, "_require_api", lambda _cm: (0, object()))
    monkeypatch.setattr(cmd_volumes, "_monitor_volumes_from_config", lambda _cm: volumes)
    monkeypatch.setattr(
        cmd_volumes,
        "process_fits_dir",
        lambda client, path, show_hdr=False, dry_run=False: calls.append(path),
    )

    ret = cmd_volumes.sanity_files(cm, _base_args())
    assert ret == 0
    assert calls == [r"c:\astro\live", r"d:\astro\archive"]


def test_sanity_files_with_project_prefetches_and_prints_stats(monkeypatch, capsys):
    cm = _DummyConfigManager()
    calls = []
    volumes = [(r"c:\astro\live", "live")]

    monkeypatch.setattr(cmd_volumes, "_require_api", lambda _cm: (0, object()))
    monkeypatch.setattr(cmd_volumes, "_scope_id_from_config", lambda _cm: 3)
    monkeypatch.setattr(cmd_volumes, "_fetch_projects_list", lambda client, scope_id: [{"name": "M42"}])
    monkeypatch.setattr(cmd_volumes, "_monitor_volumes_from_config", lambda _cm: volumes)

    def _fake_process_dir(client, path, show_hdr=False, dry_run=False, **kwargs):
        calls.append((path, kwargs))
        kwargs["project_stats"]["M42"] = {("Ha", 300.0): 2}
        kwargs["project_tracker"]["files_without_project"] = 1

    monkeypatch.setattr(cmd_volumes, "process_fits_dir", _fake_process_dir)

    ret = cmd_volumes.sanity_files(cm, _base_args(project=True))
    assert ret == 0
    assert len(calls) == 1
    assert calls[0][0] == r"c:\astro\live"
    assert calls[0][1]["projects"] == [{"name": "M42"}]
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
        projects=[{"name": "M42"}],
        project_stats=project_stats,
        project_tracker=tracker,
    )
    out = capsys.readouterr().out
    assert "Project found: 'M42'" in out
    assert project_stats["M42"][("Ha", 300.0)] == 1
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
