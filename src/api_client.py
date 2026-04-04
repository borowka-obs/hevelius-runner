import logging
import re
import requests
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import certifi


def _join_api(base_url: str, path: str) -> str:
    """Join base URL (usually .../api/) with a relative path segment (no leading slash)."""
    path = path.lstrip("/")
    base = base_url if base_url.endswith("/") else base_url + "/"
    return urljoin(base, path)


@dataclass
class LoginResponse:
    """Login JSON per OpenAPI; backend may omit optional fields on success."""

    status: bool
    token: str = ""
    user_id: int = 0
    firstname: str = ""
    lastname: str = ""
    share: float = 0.0
    phone: str = ""
    email: str = ""
    permissions: int = 0
    aavso_id: str = ""
    ftp_login: str = ""
    ftp_pass: str = ""
    msg: str = ""

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "LoginResponse":
        def s(key: str, default: str = "") -> str:
            v = data.get(key)
            return default if v is None else str(v)

        def i(key: str, default: int = 0) -> int:
            v = data.get(key)
            if v is None:
                return default
            try:
                return int(v)
            except (TypeError, ValueError):
                return default

        def f(key: str, default: float = 0.0) -> float:
            v = data.get(key)
            if v is None:
                return default
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        return cls(
            status=bool(data.get("status", False)),
            token=s("token"),
            user_id=i("user_id"),
            firstname=s("firstname"),
            lastname=s("lastname"),
            share=f("share"),
            phone=s("phone"),
            email=s("email"),
            permissions=i("permissions"),
            aavso_id=s("aavso_id"),
            ftp_login=s("ftp_login"),
            ftp_pass=s("ftp_pass"),
            msg=s("msg"),
        )


class APIClient:
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize API client with configuration.

        Args:
            config: Dictionary containing 'base_url', 'timeout', 'username', 'password';
                optional 'verify_ssl', 'scope_id'.
        """
        self.base_url = config["base_url"]
        self.timeout = int(config["timeout"])
        self.logger = logging.getLogger(__name__)
        verify = config.get("verify_ssl", True)
        if isinstance(verify, bool):
            self.verify_ssl = verify
        else:
            self.verify_ssl = str(verify).lower() == "true"
        self._username = config["username"]
        self._password = config["password"]
        self._token: Optional[str] = None
        sid = config.get("scope_id")
        if sid is None or (isinstance(sid, str) and not str(sid).strip()):
            self._scope_id: Optional[int] = None
        else:
            self._scope_id = int(sid)

        if self.verify_ssl:
            self.session = requests.Session()
            self.session.verify = certifi.where()
        else:
            self.session = requests.Session()
            self.session.verify = False
            self.logger.warning("SSL verification is disabled. This is not recommended for production use.")

    def _get_auth_headers(self) -> Dict[str, str]:
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    def login(self) -> LoginResponse:
        """
        Authenticate with the API (plaintext password over HTTPS; JWT in response).

        Raises:
            requests.RequestException: If the API call fails
        """
        try:
            url = _join_api(self.base_url, "login")
            payload = {"username": self._username, "password": self._password}
            self.logger.info(f"Authenticating user {self._username}")
            response = self.session.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            login_response = LoginResponse.from_json(data)
            if login_response.status and login_response.token:
                self._token = login_response.token
                self.logger.info("Authentication successful (JWT received)")
            elif login_response.status:
                self.logger.error("Login reported success but no token was returned")
            else:
                self.logger.error(f"Authentication failed: {login_response.msg}")
            return login_response
        except requests.RequestException as e:
            self.logger.error(f"Login failed: {str(e)}")
            raise

    def get_version(self) -> str:
        try:
            self.logger.debug("base_url=%s", self.base_url)
            url = _join_api(self.base_url, "version")
            self.logger.info(f"Checking backend connectivity ({url})")
            response = self.session.get(url, timeout=self.timeout)
            self.logger.debug(f"API version response: {response.text}")
            response.raise_for_status()
            return response.json()["version"]
        except requests.RequestException as e:
            self.logger.error(f"Failed to retrieve version: {str(e)}")
            raise

    def list_telescopes(self) -> List[Dict[str, Any]]:
        """
        GET /api/scopes — requires JWT (call login or connect first).
        """
        url = _join_api(self.base_url, "scopes")
        self.logger.info("Fetching telescope list")
        response = self.session.get(url, timeout=self.timeout, headers=self._get_auth_headers())
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "scopes" in data:
            return list(data["scopes"])
        if isinstance(data, dict) and "telescopes" in data:
            return list(data["telescopes"])
        self.logger.warning("Unexpected telescopes response shape; returning empty list")
        return []

    def get_night_plan(self, date: str) -> List[Dict[str, Any]]:
        if self._scope_id is None:
            raise ValueError(
                "scope_id is not configured; set api.scope_id in config.yaml "
                "or use: hevelius-runner telescope set <id_or_name>"
            )
        try:
            url = _join_api(self.base_url, "night-plan")
            params = {"scope_id": self._scope_id}
            self.logger.info(f"Fetching night plan for date: {date} (scope_id={self._scope_id})")
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
                headers=self._get_auth_headers(),
            )
            response.raise_for_status()
            response_json = response.json()
            tasks = response_json["tasks"]
            self.logger.info(f"Retrieved {len(tasks)} tasks for {date}")
            self.logger.debug(f"Tasks: {tasks}")
            return tasks
        except requests.RequestException as e:
            self.logger.error(f"Failed to retrieve night plan: {str(e)}")
            raise

    def update_task_status(self, task_id: str, status: str, fits_files: Optional[List[str]] = None) -> bool:
        try:
            url = _join_api(self.base_url, "task-update")
            payload = {"task_id": task_id, "status": status, "fits_files": fits_files or []}
            self.logger.info(f"Updating task {task_id} with status: {status}")
            response = self.session.post(
                url,
                json=payload,
                timeout=self.timeout,
                headers=self._get_auth_headers(),
            )
            response.raise_for_status()
            self.logger.info(f"Successfully updated task {task_id}")
            return True
        except requests.RequestException as e:
            self.logger.error(f"Failed to update task {task_id}: {str(e)}")
            raise

    def check_task_status(self, task_id: str) -> Optional[Any]:
        try:
            url = _join_api(self.base_url, "task-get")
            self.logger.info(f"Checking status for task: {task_id}")
            response = self.session.get(
                url,
                params={"task_id": task_id},
                timeout=self.timeout,
                headers=self._get_auth_headers(),
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("status"):
                self.logger.error(f"Task {task_id} not found: {data.get('msg')}")
                return None
            task = data.get("task")
            if not task:
                return None
            st = task.get("state")
            self.logger.debug(f"Task {task_id} status: {st}")
            return st
        except requests.RequestException as e:
            self.logger.error(f"Failed to check task status: {str(e)}")
            raise

    def connect(self):
        """Reachability check + login; stores JWT for subsequent calls."""
        ver = self.get_version()
        self.logger.info(f"Backend ({self.base_url}) reachable, returned version is {ver}")
        self.login()


def resolve_scope_id_from_identifier(
    client: APIClient,
    identifier: str,
) -> tuple[int, Optional[str]]:
    """
    If identifier is numeric, return (id, None).
    Otherwise match telescope name (case-insensitive, stripped); returns (id, matched name).
    Raises ValueError if not found or ambiguous.
    """
    s = identifier.strip()
    if not s:
        raise ValueError("Telescope identifier is empty.")
    if re.fullmatch(r"-?\d+", s):
        return int(s), None

    scopes = client.list_telescopes()
    key = s.lower()
    matches = []
    for t in scopes:
        name = (t.get("name") or "").strip()
        if name.lower() == key:
            matches.append((int(t["scope_id"]), name))

    if not matches:
        names = [f"{t.get('scope_id')}: {t.get('name')!r}" for t in scopes]
        hint = "\n  ".join(names) if names else "(no telescopes returned)"
        raise ValueError(f"No telescope named {identifier!r}.\n  {hint}")

    if len(matches) > 1:
        raise ValueError(f"Ambiguous name {identifier!r}; use scope_id instead: {matches}")

    return matches[0][0], matches[0][1]
