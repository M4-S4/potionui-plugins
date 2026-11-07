import json
import shutil
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path


class ApiError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, detail: str):
        super().__init__(f"{method} {path} answered HTTP {status}: {detail[:300]}")
        self.method = method
        self.path = path
        self.status = status
        self.detail = detail


class ApiUnreachable(RuntimeError):
    pass


@dataclass(frozen=True)
class Download:
    path: Path
    size: int
    content_type: str
    filename: str | None


def unwrap(payload):
    if isinstance(payload, dict) and "success" in payload and "data" in payload:
        if payload["success"] is False:
            raise ValueError(payload.get("message") or payload.get("error") or "the API answered success=false")
        return payload["data"]
    return payload


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._token: str | None = None

    @property
    def authenticated(self) -> bool:
        return self._token is not None

    def login(self, username: str, password: str) -> None:
        body = urllib.parse.urlencode({"username": username, "password": password}).encode()
        payload = self._json("POST", "/api/auth/login", body, "application/x-www-form-urlencoded", auth=False)
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise ApiError("POST", "/api/auth/login", 200, "the answer holds no access_token")
        self._token = token

    def get_json(self, path: str, params: dict | None = None, missing_ok: bool = False):
        try:
            return self._json("GET", self._with_query(path, params))
        except ApiError as error:
            if missing_ok and error.status == 404:
                return None
            raise

    def post_json(self, path: str, payload: dict):
        return self._json("POST", path, json.dumps(payload).encode(), "application/json")

    def upload(self, path: str, file: Path, content_type: str, filename: str | None = None, fields: dict | None = None):
        boundary = f"potion-audit-{uuid.uuid4().hex}"
        name = filename or file.name
        parts = []
        for key, value in (fields or {}).items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: {content_type}\r\n\r\n'.encode())
        parts.append(file.read_bytes())
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        return self._json("POST", path, b"".join(parts), f"multipart/form-data; boundary={boundary}")

    def download(self, path: str, dest: Path, params: dict | None = None) -> Download:
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_name(dest.name + ".part")
        with self._open("GET", self._with_query(path, params)) as response:
            content_type = response.headers.get("Content-Type", "")
            filename = _filename(response.headers.get("Content-Disposition", ""))
            with open(partial, "wb") as handle:
                shutil.copyfileobj(response, handle, 1024 * 1024)
        partial.replace(dest)
        return Download(dest, dest.stat().st_size, content_type, filename)

    def _with_query(self, path: str, params: dict | None) -> str:
        if not params:
            return path
        return path + "?" + urllib.parse.urlencode(params, doseq=True)

    def _json(self, method: str, path: str, body: bytes | None = None, content_type: str | None = None, auth: bool = True):
        with self._open(method, path, body, content_type, auth) as response:
            raw = response.read()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as error:
            raise ApiError(method, path, response.status, f"the answer is not JSON ({error})") from error

    def _open(self, method: str, path: str, body: bytes | None = None, content_type: str | None = None, auth: bool = True):
        headers = {"Accept": "application/json, */*"}
        if content_type:
            headers["Content-Type"] = content_type
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(self.base_url + path, data=body, headers=headers, method=method)
        try:
            return urllib.request.urlopen(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            detail = _detail(error)
            error.close()
            raise ApiError(method, path.split("?", 1)[0], error.code, detail) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            raise ApiUnreachable(f"{method} {self.base_url}{path.split('?', 1)[0]}: {error}") from None


def _detail(error: urllib.error.HTTPError) -> str:
    raw = error.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return raw.decode("utf-8", "replace")
    if isinstance(payload, dict):
        for key in ("detail", "message", "error"):
            if payload.get(key):
                value = payload[key]
                return value if isinstance(value, str) else json.dumps(value)
    return json.dumps(payload)


def _filename(disposition: str) -> str | None:
    for part in disposition.split(";"):
        key, _, value = part.strip().partition("=")
        if key.lower() == "filename" and value:
            return value.strip('"')
    return None
