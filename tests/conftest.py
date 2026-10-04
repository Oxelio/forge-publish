import io

import pytest
import requests
from requests.adapters import BaseAdapter


class RedirectAdapter(BaseAdapter):
    """Exercise Requests redirect handling without making network requests."""

    def __init__(self, status_code: int, location: str) -> None:
        self.status_code = status_code
        self.location = location
        self.requests: list[tuple[str, str, bytes | None]] = []

    def send(self, request, **kwargs):
        body = request.body
        if hasattr(body, "read"):
            body = body.read()
        self.requests.append((request.method, request.url, body))

        response = requests.Response()
        response.request = request
        response.url = request.url
        response.raw = io.BytesIO(b"<html>Login</html>")
        if len(self.requests) == 1:
            response.status_code = self.status_code
            response.headers["Location"] = self.location
        else:
            response.status_code = 200
        return response

    def close(self):
        pass


@pytest.fixture
def redirect_session():
    sessions = []

    def create(status_code: int, location: str = "https://login.example.com/login"):
        session = requests.Session()
        session.trust_env = False
        adapter = RedirectAdapter(status_code, location)
        session.mount("https://", adapter)
        sessions.append(session)
        return session, adapter

    yield create

    for session in sessions:
        session.close()
