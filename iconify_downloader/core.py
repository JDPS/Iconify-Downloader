from __future__ import annotations

from pathlib import Path

import click
import httpx

ICONIFY_API = "https://api.iconify.design"
GITHUB_RAW = "https://raw.githubusercontent.com/iconify/icon-sets/master/json"


def list_from_api(client: httpx.Client,
                  prefix: str,
                  debug: bool) -> tuple[list[str], dict]:
    # 1) Check set exists
    r = client.get(f"{ICONIFY_API}/collections", params={"prefix": prefix}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict) or prefix not in data:
        if debug:
            click.echo(f"[debug] /collections did not contain '{prefix}'", err=True)
        raise click.ClickException(f"Iconify API: unknown prefix '{prefix}'")
    # 2) List icons
    r = client.get(f"{ICONIFY_API}/collection",
                   params={"prefix": prefix,"info": "true"},
                   timeout=60)
    r.raise_for_status()
    col = r.json()
    icons = col.get("icons")
    if not isinstance(icons, list):
        if debug:
            keys = list(col.keys())
            click.echo(f"[debug] /collection icons"
                       f" not list "
                       f"(type={type(icons).__name__}),"
                       f" keys={keys}", err=True)
        raise click.ClickException("icons is not a list")
    info = col.get("info") or {}
    return [str(x) for x in icons], (info if isinstance(info, dict) else {})

def list_from_github(client: httpx.Client,
                     prefix: str,
                     debug: bool) -> tuple[list[str], dict, dict]:
    url = f"{GITHUB_RAW}/{prefix}.json"
    r = client.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    icons_obj = data.get("icons")
    if not isinstance(icons_obj, dict):
        if debug:
            click.echo(f"[debug] GitHub JSON"
                       f" 'icons' is {type(icons_obj)};"
                       f" top keys: {list(data.keys())}", err=True)
        raise click.ClickException(f"Unexpected JSON structure for '{prefix}'.")
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    categories = data.get("categories") if isinstance(data.get("categories"), dict) else {}
    return sorted(icons_obj.keys()), info, categories


def fetch_svg(client: httpx.Client,
              prefix: str,
              name: str,
              out_dir: Path,
              size: int | None) -> tuple[str, bool, str]:
    params = {"height": str(size)} if size else None
    url = f"{ICONIFY_API}/{prefix}:{name}.svg"
    try:
        r = client.get(url, params=params, timeout=40)
        r.raise_for_status()
        (out_dir / f"{prefix}-{name}.svg").write_bytes(r.content)
        return name, True, ""
    except Exception as exc:
        return name, False, str(exc)
