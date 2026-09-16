from __future__ import annotations

from pathlib import Path

import requests

from .config import Config


class ForgejoError(RuntimeError):
    pass


class ForgejoClient:

    def __init__(self, config: Config):
        self.config = config

        if not config.token:
            raise ForgejoError("No Forgejo token configured.")

        self.session = requests.Session()
        self.session.auth = (
            config.username,
            config.token,
        )

    def upload(
        self,
        url: str,
        file: Path,
        dry_run: bool = False,
    ) -> None:

        if dry_run:
            print()
            print("DRY RUN")
            print("-------")
            print(f"PUT  : {url}")
            print(f"FILE : {file}")
            return

        try:
            with file.open("rb") as f:
                response = self.session.put(
                    url,
                    data=f,
                )
        except requests.RequestException as exc:
            raise ForgejoError(
                f"HTTP request failed: {exc}"
            ) from exc

        if response.status_code in (200, 201):
            return

        self._raise_error(response)

    def delete(
        self,
        url: str,
        dry_run: bool = False,
        ignore_404: bool = False,
    ) -> None:

        if dry_run:
            print()
            print("DRY RUN")
            print("-------")
            print(f"DELETE : {url}")
            return

        try:
            response = self.session.delete(url)
        except requests.RequestException as exc:
            raise ForgejoError(
                f"HTTP request failed: {exc}"
            ) from exc

        if response.status_code == 404 and ignore_404:
            return

        if response.status_code not in (200, 204):
            self._raise_error(response)

    @staticmethod
    def _raise_error(response: requests.Response) -> None:
        message = response.text.strip()

        if response.status_code == 401:
            reason = "authentication failed"
        elif response.status_code == 403:
            reason = "permission denied"
        elif response.status_code == 404:
            reason = "resource not found"
        elif response.status_code == 409:
            reason = "package/file already exists"
        elif response.status_code == 400:
            reason = "invalid package or request"
        else:
            reason = "Forgejo returned an error"

        if message:
            reason += f": {message}"

        raise ForgejoError(
            f"HTTP {response.status_code}: {reason}"
        )