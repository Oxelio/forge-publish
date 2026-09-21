from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from .config import Config
from .errors import ForgePublishError

REQUEST_TIMEOUT = (10, 300)
MAX_ERROR_MESSAGE_LENGTH = 500


class ForgejoError(ForgePublishError):
    """Raised when communication with Forgejo fails."""


class ForgejoClient:
    def __init__(
        self,
        config: Config,
        *,
        verify_tls: bool,
    ):
        self.config = config
        self.verify_tls = verify_tls
        self.session = requests.Session()

        if config.token:
            self.session.auth = (
                config.username,
                config.token,
            )

    def upload(
        self,
        url: str,
        file: Path,
        *,
        dry_run: bool,
    ) -> None:
        if dry_run:
            print()
            print("DRY RUN")
            print("-------")
            print(f"PUT  : {url}")
            print(f"FILE : {file}")
            return

        self._require_authentication()

        try:
            stream = file.open("rb")
        except OSError as exc:
            raise ForgejoError(f"Unable to read file: {file}") from exc

        try:
            with stream:
                response = self.session.put(
                    url,
                    data=stream,
                    timeout=REQUEST_TIMEOUT,
                    verify=self.verify_tls,
                )
        except requests.RequestException as exc:
            raise ForgejoError(f"HTTP request failed: {exc}") from exc
        except OSError as exc:
            raise ForgejoError(f"Unable to read file: {file}") from exc

        if 200 <= response.status_code < 300:
            return

        self._raise_error(response)

    def delete(
        self,
        url: str,
        *,
        dry_run: bool,
        ignore_404: bool,
    ) -> None:
        if dry_run:
            print()
            print("DRY RUN")
            print("-------")
            print(f"DELETE : {url}")
            return

        self._require_authentication()

        try:
            response = self.session.delete(
                url,
                timeout=REQUEST_TIMEOUT,
                verify=self.verify_tls,
            )
        except requests.RequestException as exc:
            raise ForgejoError(f"HTTP request failed: {exc}") from exc

        if response.status_code == 404 and ignore_404:
            return

        if not 200 <= response.status_code < 300:
            self._raise_error(response)

    def _require_authentication(self) -> None:
        if not self.config.token:
            raise ForgejoError("No Forgejo token configured.")

    @staticmethod
    def _response_message(response: requests.Response) -> str:
        message = ""

        try:
            payload: Any = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            for key in ("message", "error", "detail"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    message = value.strip()
                    break

        if not message:
            message = response.text.strip()

        if len(message) > MAX_ERROR_MESSAGE_LENGTH:
            return message[:MAX_ERROR_MESSAGE_LENGTH] + "..."

        return message

    @classmethod
    def _raise_error(cls, response: requests.Response) -> None:
        reasons = {
            400: "invalid package or request",
            401: "authentication failed",
            403: "permission denied",
            404: "resource not found",
            409: "package/file already exists",
            413: "package/file is too large",
            429: "too many requests",
        }

        if response.status_code >= 500:
            reason = "Forgejo server error"
        else:
            reason = reasons.get(
                response.status_code,
                "Forgejo returned an error",
            )

        message = cls._response_message(response)
        if message:
            reason += f": {message}"

        raise ForgejoError(f"HTTP {response.status_code}: {reason}")
