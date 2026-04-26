import textwrap
from unittest.mock import MagicMock, patch

def _write_minimal_config(path, password="x"):
    path.write_text(
        textwrap.dedent(
            f"""
            api:
              base_url: https://example.test/api/
              timeout: 5
              username: testuser
              password: {password}
              verify_ssl: false
              scope_id: 3
            paths:
              template_dir: t
              output_dir: o
            nina:
              executable_path: {path.parent / "nina_fake.exe"}
            scripts:
              startup_script: s.py
            """
        ).strip(),
        encoding="utf-8",
    )


def test_run_command_invokes_observatory(tmp_path, runner_mod):
    cfg = tmp_path / "c.yaml"
    _write_minimal_config(cfg)
    fake_nina = tmp_path / "nina_fake.exe"
    fake_nina.write_bytes(b"")

    with patch.object(runner_mod, "ObservatoryAutomation") as MockObs:
        instance = MagicMock()
        MockObs.return_value = instance
        ret = runner_mod.main(["-c", str(cfg), "run"])
        assert ret == 0
        MockObs.assert_called_once()
        instance.run.assert_called_once()


def test_no_subcommand_prints_help(capsys, runner_mod):
    ret = runner_mod.main([])
    assert ret == 0
    out = capsys.readouterr().out
    assert "COMMAND" in out or "command" in out.lower()
    assert "run" in out
    assert "config" in out


def test_config_command_prints_yaml_without_password(tmp_path, capsys, runner_mod):
    cfg = tmp_path / "c.yaml"
    _write_minimal_config(cfg, password="realpassword")

    ret = runner_mod.main(["-c", str(cfg), "config"])
    assert ret == 0
    out = capsys.readouterr().out
    assert "realpassword" not in out
    assert "***" in out
    assert "example.test" in out
    assert "configuration file:" in out
    assert str(cfg.resolve()) in out


def test_doctor_command_success(tmp_path, capsys, runner_mod):
    cfg = tmp_path / "c.yaml"
    fake_nina = tmp_path / "nina_fake.exe"
    fake_nina.write_bytes(b"")

    cfg.write_text(
        textwrap.dedent(
            f"""
            api:
              base_url: https://example.test/api/
              timeout: 5
              username: u
              password: p
              verify_ssl: false
              scope_id: 1
            paths:
              template_dir: t
              output_dir: o
            nina:
              executable_path: {fake_nina}
            scripts: {{}}
            """
        ).strip(),
        encoding="utf-8",
    )

    mock_login = MagicMock()
    mock_login.status = True
    mock_login.token = "jwt-test-token"
    mock_login.user_id = 1
    mock_login.msg = ""

    with patch.object(runner_mod, "APIClient") as MockClient:
        client = MagicMock()
        client.get_version.return_value = "1.0.0"
        client.login.return_value = mock_login
        client.list_telescopes.return_value = [{"scope_id": 1, "name": "Test"}]
        MockClient.return_value = client

        ret = runner_mod.main(["-c", str(cfg), "doctor"])
        assert ret == 0
        out = capsys.readouterr().out
        assert "1.0.0" in out
        assert "Connectivity check passed" in out or "check passed" in out


def test_version_prints_runner_version(capsys, runner_mod):
    ret = runner_mod.main(["version"])
    assert ret == 0
    out = capsys.readouterr().out
    assert "hevelius-runner" in out
    assert out.strip()


def test_run_without_scope_id_exits(tmp_path, runner_mod):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        """
api:
  base_url: https://example.test/api/
  timeout: 5
  username: u
  password: p
  verify_ssl: false
paths:
  template_dir: t
  output_dir: o
nina:
  executable_path: nina.exe
scripts: {}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "nina.exe").write_bytes(b"")
    ret = runner_mod.main(["-c", str(cfg), "run"])
    assert ret == 1


def test_projects_command_dispatches(tmp_path, runner_mod):
    cfg = tmp_path / "c.yaml"
    _write_minimal_config(cfg)
    fake_nina = tmp_path / "nina_fake.exe"
    fake_nina.write_bytes(b"")
    with patch.object(runner_mod, "cmd_projects") as mock_projects:
        mock_projects.return_value = 0
        ret = runner_mod.main(["-c", str(cfg), "projects", "list"])
        assert ret == 0
        mock_projects.assert_called_once()
