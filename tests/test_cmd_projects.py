from types import SimpleNamespace

import cmd_projects


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params=None, timeout=None, headers=None):
        self.calls.append((url, params, timeout, headers))
        return _FakeResponse(self.payload)


def test_get_projects_list_reads_projects_endpoint():
    session = _FakeSession({"projects": [{"project_id": 101, "name": "M31"}]})
    client = SimpleNamespace(
        base_url="https://example.test/api/",
        timeout=5,
        session=session,
        _get_auth_headers=lambda: {"Authorization": "Bearer x"},
    )
    projects = cmd_projects.get_projects_list(client, scope_id=3)
    assert len(projects) == 1
    assert projects[0]["project_id"] == 101
    assert "projects" in session.calls[0][0]
    assert session.calls[0][1]["scope_id"] == 3


def test_cmd_projects_list_prints_table_with_sexagesimal_radec(monkeypatch, capsys):
    monkeypatch.setattr(cmd_projects, "_require_api", lambda cm: (0, object()))
    monkeypatch.setattr(cmd_projects, "_scope_id_from_config", lambda cm: 3)
    monkeypatch.setattr(
        cmd_projects,
        "get_projects_list",
        lambda client, scope_id: [{"project_id": 5, "name": "M42", "ra": 5.5, "decl": -5.5}],
    )

    rc = cmd_projects.cmd_projects_list(object())
    assert rc == 0
    out = capsys.readouterr().out
    assert "5" in out
    assert "M42" in out
    assert "05 30 00" in out
    assert "-05 30 00" in out
    # Table rendering, not the old floating-point dump.
    assert "5.5" not in out
    assert "project_id=" not in out
    assert "│" in out


def test_cmd_projects_view_requires_name_or_id(monkeypatch, capsys):
    monkeypatch.setattr(cmd_projects, "_require_api", lambda cm: (0, object()))
    rc = cmd_projects.cmd_projects_view(object(), project_name=None, project_id=None)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Either --name or --project-id" in err


def test_cmd_projects_view_prints_project_and_subframes(monkeypatch, capsys):
    monkeypatch.setattr(cmd_projects, "_require_api", lambda cm: (0, object()))
    monkeypatch.setattr(cmd_projects, "_scope_id_from_config", lambda cm: 3)
    monkeypatch.setattr(
        cmd_projects,
        "get_project_details",
        lambda client, scope_id, project_id, name: {
            "project_id": 7,
            "name": "NGC7000",
            "scope_id": 3,
            "ra": 20.5,
            "decl": 44.0,
            "active": True,
            "subframes": [
                {"filter": {"short_name": "Ha"}, "exposure_time": 300, "count": 10, "project_id": 7},
                {"filter": {"short_name": "OIII"}, "exposure_time": 300, "count": 10, "project_id": 7},
            ],
        },
    )

    rc = cmd_projects.cmd_projects_view(object(), project_name="NGC7000", project_id=None)
    assert rc == 0
    out = capsys.readouterr().out
    assert "NGC7000" in out
    assert "#7" in out
    assert "Subframes:" in out
    assert "Ha" in out
    assert "OIII" in out
    # project_id is already printed for the whole project; must not repeat per subframe.
    assert "project_id" not in out


def test_cmd_projects_view_no_subframes(monkeypatch, capsys):
    monkeypatch.setattr(cmd_projects, "_require_api", lambda cm: (0, object()))
    monkeypatch.setattr(cmd_projects, "_scope_id_from_config", lambda cm: 3)
    monkeypatch.setattr(
        cmd_projects,
        "get_project_details",
        lambda client, scope_id, project_id, name: {"project_id": 9, "name": "Solo"},
    )

    rc = cmd_projects.cmd_projects_view(object(), project_name="Solo", project_id=None)
    assert rc == 0
    out = capsys.readouterr().out
    assert "Subframes: none" in out


def test_cmd_projects_dispatch_unknown_subcommand():
    rc = cmd_projects.cmd_projects(object(), SimpleNamespace(project_cmd="bogus"))
    assert rc == 2
