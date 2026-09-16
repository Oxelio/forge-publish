from __future__ import annotations

from pathlib import Path

import click

from .client import ForgejoClient
from .config import configure, load_config
from .publishers import deb, generic, npm


@click.group()
@click.version_option()
def main():
    """Publish packages to Forgejo package registries."""


@main.command("config")
@click.option(
    "--url",
    default="https://forge.fco.local",
    show_default=True,
)
@click.option(
    "--owner",
    default="Software",
    show_default=True,
)
@click.option(
    "--username",
    prompt="Forgejo username",
)
def config_command(
    url: str,
    owner: str,
    username: str,
):
    """Configure Forgejo credentials."""

    configure(
        url=url,
        owner=owner,
        username=username,
    )


@main.command("deb")
@click.argument(
    "file",
    type=click.Path(
        exists=True,
        dir_okay=False,
        path_type=Path,
    ),
)
@click.option(
    "--distribution",
    "-d",
    default="lenny",
    show_default=True,
)
@click.option(
    "--component",
    "-c",
    default="main",
    show_default=True,
)
@click.option(
    "--dry-run",
    is_flag=True,
)
def deb_command(
    file: Path,
    distribution: str,
    component: str,
    dry_run: bool,
):
    """Publish a Debian package."""

    try:
        config = load_config()
        client = ForgejoClient(config)

        deb.publish(
            client=client,
            file=file,
            distribution=distribution,
            component=component,
            dry_run=dry_run,
        )

    except RuntimeError as exc:
        raise click.ClickException(str(exc))


@main.command("generic")
@click.argument(
    "file",
    type=click.Path(
        exists=True,
        dir_okay=False,
        path_type=Path,
    ),
)
@click.option(
    "--package",
    "package_name",
    required=True,
    help="Generic package name.",
)
@click.option(
    "--version",
    required=True,
    help="Package version.",
)
@click.option(
    "--filename",
    help="Filename stored in Forgejo.",
)
@click.option(
    "--dry-run",
    is_flag=True,
)
def generic_command(
    file: Path,
    package_name: str,
    version: str,
    filename: str | None,
    dry_run: bool,
):
    """Publish a Generic package."""

    try:
        config = load_config()
        client = ForgejoClient(config)

        generic.publish(
            client=client,
            file=file,
            package_name=package_name,
            version=version,
            filename=filename,
            dry_run=dry_run,
        )

    except RuntimeError as exc:
        raise click.ClickException(str(exc))


@main.command("npm")
@click.argument(
    "directory",
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
    ),
    default=".",
)
@click.option(
    "--dry-run",
    is_flag=True,
)
def npm_command(
    directory: Path,
    dry_run: bool,
):
    """Publish an NPM package."""

    try:
        config = load_config()
        client = ForgejoClient(config)

        npm.publish(
            client=client,
            directory=directory,
            dry_run=dry_run,
        )

    except RuntimeError as exc:
        raise click.ClickException(str(exc))