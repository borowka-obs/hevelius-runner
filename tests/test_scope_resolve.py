from unittest.mock import MagicMock

import pytest

from api_client import resolve_scope_id_from_identifier


def test_resolve_numeric_id():
    client = MagicMock()
    sid, name = resolve_scope_id_from_identifier(client, "  7 ")
    assert sid == 7
    assert name is None
    client.list_telescopes.assert_not_called()


def test_resolve_by_name():
    client = MagicMock()
    client.list_telescopes.return_value = [
        {"scope_id": 3, "name": "Main"},
        {"scope_id": 5, "name": "Wide"},
    ]
    sid, name = resolve_scope_id_from_identifier(client, "Wide")
    assert sid == 5
    assert name == "Wide"


def test_resolve_name_case_insensitive():
    client = MagicMock()
    client.list_telescopes.return_value = [{"scope_id": 1, "name": "RC8"}]
    sid, _ = resolve_scope_id_from_identifier(client, "rc8")
    assert sid == 1


def test_resolve_unknown_name():
    client = MagicMock()
    client.list_telescopes.return_value = [{"scope_id": 1, "name": "A"}]
    with pytest.raises(ValueError, match="No telescope"):
        resolve_scope_id_from_identifier(client, "Nope")
