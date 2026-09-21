from __future__ import annotations

from pathlib import Path

import click

from .client import ForgejoClient
from .config import configure, load_config
from .errors import ForgePublishError
from .publishers import deb, generic, npm


def _create_client(
    *,
    dry_run: bool,
    insecure: bool = False,
) -> ForgejoClient:
    config = load_config(require_token=not dry_run)

    if insecure:
        click.echo(
            "WARNING: TLS certificate verification is disabled.",
            err=True,
        )

    return ForgejoClient(
        config,
        verify_tls=not insecure,
    )


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
    try:
        configure(
            url=url,
            owner=owner,
            username=username,
        )
    except ForgePublishError as exc:
        raise click.ClickException(str(exc)) from exc


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
    "--insecure",
    is_flag=True,
    help="Disable TLS certificate verification.",
)
@click.option("--dry-run", is_flag=True)
def deb_command(
    file: Path,
    distribution: str,
    component: str,
    insecure: bool,
    dry_run: bool,
):
    """Publish a Debian package."""
    try:
        client = _create_client(
            dry_run=dry_run,
            insecure=insecure,
        )
        deb.publish(
            client=client,
            file=file,
            distribution=distribution,
            component=component,
            dry_run=dry_run,
        )
    except ForgePublishError as exc:
        raise click.ClickException(str(exc)) from exc


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
    "--insecure",
    is_flag=True,
    help="Disable TLS certificate verification.",
)
@click.option("--dry-run", is_flag=True)
def generic_command(
    file: Path,
    package_name: str,
    version: str,
    filename: str | None,
    insecure: bool,
    dry_run: bool,
):
    """Publish a Generic package."""
    try:
        client = _create_client(
            dry_run=dry_run,
            insecure=insecure,
        )

        generic.publish(
            client=client,
            file=file,
            package_name=package_name,
            version=version,
            filename=filename,
            dry_run=dry_run,
        )
    except ForgePublishError as exc:
        raise click.ClickException(str(exc)) from exc


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
@click.option("--dry-run", is_flag=True)
def npm_command(
    directory: Path,
    dry_run: bool,
):
    """Publish an NPM package."""
    try:
        client = _create_client(dry_run=dry_run)
        npm.publish(
            client=client,
            directory=directory,
            dry_run=dry_run,
        )
    except ForgePublishError as exc:
        raise click.ClickException(str(exc)) from exc
