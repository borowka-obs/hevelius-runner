import logging

from api_client import APIClient, _join_api


def test_verify_ssl_accepts_bool():
    logging.basicConfig(level=logging.WARNING)
    c = APIClient(
        {
            "base_url": "https://example.test/",
            "timeout": "10",
            "username": "u",
            "password": "p",
            "verify_ssl": False,
        }
    )
    assert c.verify_ssl is False


def test_join_api_relative_path():
    assert _join_api("https://h.example/api/", "scopes") == "https://h.example/api/scopes"
    assert _join_api("https://h.example/api", "version") == "https://h.example/api/version"


def test_verify_ssl_accepts_string():
    logging.basicConfig(level=logging.WARNING)
    c = APIClient(
        {
            "base_url": "https://example.test/",
            "timeout": 10,
            "username": "u",
            "password": "p",
            "verify_ssl": "false",
        }
    )
    assert c.verify_ssl is False
