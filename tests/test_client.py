from pathlib import Path

import pytest
import requests

from forge_publish.client import (
    MAX_ERROR_MESSAGE_LENGTH,
    REQUEST_TIMEOUT,
    ForgejoClient,
    ForgejoError,
)
from forge_publish.config import Config


class FailingSession:
    def __init__(self, error=requests.ConnectionError) -> None:
        self.auth = None
        self.error = error

    def put(self, url, data, timeout, verify, allow_redirects):
        raise self.error("connection failed")


class FailingDeleteSession:
    def __init__(self, error=requests.ConnectionError) -> None:
        self.auth = None
        self.error = error

    def delete(self, url, timeout, verify, allow_redirects):
        raise self.error("connection failed")


_NO_JSON = object()


class Response:
    def __init__(
        self,
        status_code: int = 201,
        *,
        text: str = "",
        payload: object = _NO_JSON,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self.payload = payload

    def json(self):
        if self.payload is _NO_JSON:
            raise ValueError
        return self.payload


class Session:
    def __init__(
        self,
        *,
        put_response: Response | None = None,
        delete_response: Response | None = None,
    ) -> None:
        self.auth = None
        self.timeout = None
        self.verify = None
        self.allow_redirects = None
        self.put_response = put_response or Response()
        self.delete_response = delete_response or Response()

    def put(self, url, data, timeout, verify, allow_redirects):
        self.timeout = timeout
        self.verify = verify
        self.allow_redirects = allow_redirects
        return self.put_response

    def delete(self, url, timeout, verify, allow_redirects):
        self.timeout = timeout
        self.verify = verify
        self.allow_redirects = allow_redirects
        return self.delete_response


def _client(*, token: str | None = "secret", verify_tls: bool = True) -> ForgejoClient:
    return ForgejoClient(
        Config(
            url="https://forge.example.com",
            owner="Software",
            username="user",
            token=token,
        ),
        verify_tls=verify_tls,
    )


def test_client_configures_basic_authentication() -> None:
    client = _client()

    assert client.session.auth == ("user", "secret")


def test_dry_run_does_not_require_token(tmp_path: Path) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")

    _client(token=None).upload(
        url="https://forge.example.com/upload",
        file=package,
        dry_run=True,
    )


def test_upload_requires_authentication(tmp_path: Path) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")

    with pytest.raises(ForgejoError, match="No Forgejo token configured"):
        _client(token=None).upload(
            url="https://forge.example.com/upload",
            file=package,
            dry_run=False,
        )


def test_upload_reports_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(ForgejoError, match="Unable to read file"):
        _client().upload(
            url="https://forge.example.com/upload",
            file=tmp_path / "missing.bin",
            dry_run=False,
        )


def test_upload_uses_timeout(tmp_path: Path) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")
    client = _client()
    session = Session()
    client.session = session

    client.upload(
        url="https://forge.example.com/upload",
        file=package,
        dry_run=False,
    )

    assert session.timeout == REQUEST_TIMEOUT
    assert session.verify is True
    assert session.allow_redirects is False


@pytest.mark.parametrize(
    "error", [requests.ConnectionError, requests.Timeout, requests.exceptions.SSLError]
)
def test_upload_reports_network_error(tmp_path: Path, error) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")
    client = _client()
    client.session = FailingSession(error)

    with pytest.raises(
        ForgejoError,
        match="HTTP request failed: connection failed",
    ):
        client.upload(
            url="https://forge.example.com/upload",
            file=package,
            dry_run=False,
        )


def test_upload_disables_tls_verification(tmp_path: Path) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")
    client = _client(verify_tls=False)
    session = Session()
    client.session = session

    client.upload(
        url="https://forge.example.com/upload",
        file=package,
        dry_run=False,
    )

    assert session.verify is False


def test_delete_dry_run_does_not_require_token() -> None:
    _client(token=None).delete(
        url="https://forge.example.com/package",
        dry_run=True,
        ignore_404=False,
    )


def test_delete_disables_tls_verification() -> None:
    client = _client(verify_tls=False)
    session = Session()
    client.session = session

    client.delete(
        url="https://forge.example.com/package",
        dry_run=False,
        ignore_404=False,
    )

    assert session.verify is False
    assert session.timeout == REQUEST_TIMEOUT
    assert session.allow_redirects is False


def test_delete_ignores_404_when_requested() -> None:
    client = _client()
    client.session = Session(delete_response=Response(404))

    client.delete(
        url="https://forge.example.com/package",
        dry_run=False,
        ignore_404=True,
    )


@pytest.mark.parametrize(
    "error", [requests.ConnectionError, requests.Timeout, requests.exceptions.SSLError]
)
def test_delete_reports_network_error(error) -> None:
    client = _client()
    client.session = FailingDeleteSession(error)

    with pytest.raises(ForgejoError, match="HTTP request failed: connection failed"):
        client.delete(
            url="https://forge.example.com/package",
            dry_run=False,
            ignore_404=False,
        )


@pytest.mark.parametrize("status_code", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("operation", ["upload", "delete"])
@pytest.mark.parametrize("location", ["/login", "https://login.example.com/login"])
def test_redirects_do_not_send_a_second_request(
    tmp_path: Path,
    redirect_session,
    status_code: int,
    operation: str,
    location: str,
) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"private package data")
    client = _client()
    client.session, adapter = redirect_session(status_code, location)
    url = "https://forge.example.com/upload"

    with pytest.raises(ForgejoError, match=f"HTTP {status_code}:.*redirect"):
        if operation == "upload":
            client.upload(url, package, dry_run=False)
        else:
            client.delete(url, dry_run=False, ignore_404=True)

    expected = (
        ("PUT", url, b"private package data")
        if operation == "upload"
        else ("DELETE", url, None)
    )
    assert adapter.requests == [expected]


@pytest.mark.parametrize("status_code", [200, 201, 202, 204])
@pytest.mark.parametrize("operation", ["upload", "delete"])
def test_direct_success_is_preserved(
    tmp_path: Path,
    redirect_session,
    status_code: int,
    operation: str,
) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")
    client = _client()
    client.session, adapter = redirect_session(status_code)
    url = "https://forge.example.com/upload"

    if operation == "upload":
        client.upload(url, package, dry_run=False)
    else:
        client.delete(url, dry_run=False, ignore_404=False)

    assert len(adapter.requests) == 1


def test_dry_run_makes_no_http_requests(tmp_path: Path, redirect_session) -> None:
    client = _client(token=None)
    client.session, adapter = redirect_session(302)
    url = "https://forge.example.com/upload"

    client.upload(url, tmp_path / "missing.bin", dry_run=True)
    client.delete(url, dry_run=True, ignore_404=False)

    assert adapter.requests == []


@pytest.mark.parametrize("status_code", [300, 304, 399])
def test_other_3xx_responses_give_canonical_url_guidance(status_code: int) -> None:
    with pytest.raises(ForgejoError, match="canonical Forgejo URL.*proxy"):
        ForgejoClient._raise_error(Response(status_code, text="login page"))


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"message": "message text"}, "message text"),
        ({"error": "error text"}, "error text"),
        ({"detail": "detail text"}, "detail text"),
    ],
)
def test_response_message_reads_json_fields(
    payload: dict[str, str],
    expected: str,
) -> None:
    assert ForgejoClient._response_message(Response(payload=payload)) == expected


def test_response_message_falls_back_to_text() -> None:
    assert ForgejoClient._response_message(Response(text=" server error ")) == (
        "server error"
    )


def test_response_message_truncates_long_messages() -> None:
    message = "x" * (MAX_ERROR_MESSAGE_LENGTH + 10)

    result = ForgejoClient._response_message(Response(payload={"message": message}))

    assert result == "x" * MAX_ERROR_MESSAGE_LENGTH + "..."


@pytest.mark.parametrize(
    ("status_code", "reason"),
    [
        (400, "invalid package or request"),
        (401, "authentication failed"),
        (403, "permission denied"),
        (404, "resource not found"),
        (409, "package/file already exists"),
        (413, "package/file is too large"),
        (429, "too many requests"),
        (418, "Forgejo returned an error"),
        (500, "Forgejo server error"),
    ],
)
def test_raise_error_maps_status_codes(status_code: int, reason: str) -> None:
    with pytest.raises(ForgejoError) as exc_info:
        ForgejoClient._raise_error(Response(status_code))

    assert str(exc_info.value) == f"HTTP {status_code}: {reason}"


def test_raise_error_includes_server_message() -> None:
    with pytest.raises(ForgejoError) as exc_info:
        ForgejoClient._raise_error(
            Response(400, payload={"message": "invalid package name"})
        )

    assert str(exc_info.value) == (
        "HTTP 400: invalid package or request: invalid package name"
    )
