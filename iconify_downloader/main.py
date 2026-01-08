from __future__ import annotations

import sys

import click
import httpx

from .cli import cli


def main():
    try:
        cli()
    except httpx.HTTPError as e:
        click.echo(f"HTTP error: {e}", err=True)
        sys.exit(2)
    except click.ClickException as e:
        click.echo(str(e), err=True)
        sys.exit(2)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
