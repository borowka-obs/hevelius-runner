from api_client import LoginResponse


def test_login_response_from_minimal_json():
    r = LoginResponse.from_json({"status": True, "token": "abc", "user_id": 42})
    assert r.status is True
    assert r.token == "abc"
    assert r.user_id == 42
    assert r.msg == ""
    assert r.firstname == ""


def test_login_response_failed_login():
    r = LoginResponse.from_json({"status": False, "msg": "bad password"})
    assert r.status is False
    assert r.token == ""
    assert r.msg == "bad password"
