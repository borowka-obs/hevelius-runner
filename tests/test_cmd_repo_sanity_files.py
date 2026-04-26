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
