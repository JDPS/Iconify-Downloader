#!/usr/bin/env python3
# iconify_dl.py — stable CLI for bulk-downloading Iconify icons as SVG
# Docs used:
# - /collections (confirm set): https://iconify.design/docs/api/collections.html
# - /collection (list icons):  https://iconify.design/docs/api/collection.html

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import click
import httpx
from tqdm import tqdm

ICONIFY_API = "https://api.iconify.design"
GITHUB_RAW = "https://raw.githubusercontent.com/iconify/icon-sets/master/json"

URL_PREFIX_RE = re.compile(
    r"(?:iconify\.design/(?:icon-sets|icons)/|icon-sets\.iconify\.design/)"
    r"([a-z0-9][a-z0-9\-]*)/?",
    re.I,
)
STRICT_PREFIX_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$", re.I)


def infer_prefix(s: str) -> str:
    s = s.strip()
    m = URL_PREFIX_RE.search(s)
    if m:
        return m.group(1).lower()
    try:
        p = urlparse(s)
        if p.scheme and p.netloc:
            parts = [x for x in p.path.split("/") if x]
            if parts:
                cand = parts[-1].lower().removesuffix(".json")
                if STRICT_PREFIX_RE.match(cand):
                    return cand
    except Exception as exc:
        print(exc, file=sys.stderr)
    if STRICT_PREFIX_RE.match(s):
        return s.lower()
    raise click.ClickException(
        f"Cannot infer icon-set prefix from '{s}'. "
        "Use a prefix like 'fluent' or a set URL such as 'https://icon-sets.iconify.design/fluent/'."
    )


def list_from_api(client: httpx.Client,
                  prefix: str,
                  debug: bool) -> tuple[list[str], dict]:
    # 1) Verify set exists
    try:
        r = client.get(f"{ICONIFY_API}/collections", params={"prefix": prefix},
                       timeout=30)
        r.raise_for_status()
        data = r.json()
        # When filtered by 'prefix',
        # the response is an object: { "<prefix>": IconifyInfo }
        if not isinstance(data, dict) or prefix not in data:
            if debug:
                click.echo(
                    f"[debug] /collections returned"
                    f" JSON without '{prefix}' key:"
                    f"{list(data.keys()) if isinstance(data, dict) else type(data)}",
                    err=True)
            raise KeyError("prefix not found in /collections")
        info = data[prefix]
    except Exception as exc:
        if debug:
            click.echo(f"[debug] /collections"
                       f" failed or missing prefix '{prefix}': {exc}",
                       err=True)
        raise

    # 2) list icons
    try:
        r = client.get(f"{ICONIFY_API}/collection",
                       params={"prefix": prefix, "info": "true"},
                       timeout=60)
        r.raise_for_status()
        col = r.json()
        icons = col.get("icons")
        if not isinstance(icons, list):
            if debug:
                click.echo(f"[debug] /collection returned unexpected 'icons' type:"
                           f" {type(icons)}; body keys: {list(col.keys())}", err=True)
            raise TypeError("icons is not a list")
        # Prefer licence from /collection response if present
        info = col.get("info") or info or {}
        return [str(x) for x in icons], (info if isinstance(info, dict) else {})
    except Exception as exc:
        if debug:
            click.echo(f"[debug] /collection failed for '{prefix}': {exc}", err=True)
        raise


def list_from_github(client: httpx.Client,
                     prefix: str,
                     debug: bool) -> tuple[list[str], dict]:
    url = f"{GITHUB_RAW}/{prefix}.json"
    r = client.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    icons_obj = data.get("icons")
    if not isinstance(icons_obj, dict):
        if debug:
            click.echo(f"[debug] GitHub JSON 'icons' is {type(icons_obj)}; top keys:"
                       f" {list(data.keys())}", err=True)
        raise click.ClickException(f"Unexpected JSON structure"
                                   f" from GitHub for '{prefix}'.")
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    return sorted(icons_obj.keys()), info


def filter_icons(
    names: Iterable[str],
    include: set[str] | None,
    exclude: set[str] | None,
    contains: str | None,
) -> list[str]:
    out = []
    for n in names:
        if include and n not in include:
            continue
        if exclude and n in exclude:
            continue
        if contains and contains.lower() not in n.lower():
            continue
        out.append(n)
    return out


def write_license(out_dir: Path, prefix: str, info: dict):
    lic = info.get("license") or {}
    lic_name = lic.get("title") or lic.get("name")
    lic_ref = lic.get("spdx") or lic.get("url")
    if lic_name or lic_ref:
        (out_dir / "LICENSE.txt").write_text(
            (
                f"Iconify set: {prefix}\n"
                f"License: {lic_name or 'N/A'}\n"
                f"Reference: {lic_ref or 'N/A'}\n"
                f"Note: Some sets need attribution."
                f" Check upstream license before redistribution.\n"
            ),
            encoding="utf-8",
        )


def fetch_svg(client: httpx.Client,
              prefix: str, name: str,
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
        return (name, False, str(exc))


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("prefix_or_url", metavar="PREFIX_OR_URL")
@click.option("-o", "--out", "out_dir",
              type=click.Path(path_type=Path),
              default=Path("./iconify_svgs"),
              help="Output directory for SVG files.")
@click.option("--include", default="",
              help="Comma-separated icon names to include (exact).")
@click.option("--exclude", default="",
              help="Comma-separated icon names to exclude (exact).")
@click.option("--contains", default="", help="Substring filter for icon names.")
@click.option("-j", "--jobs", type=int, default=12, show_default=True,
              help="Concurrent downloads.")
@click.option("--size", type=int, default=None, help="Optional icon height (px).")
@click.option("--overwrite/--no-overwrite", default=False, show_default=True,
              help="Overwrite existing files.")
@click.option("--debug/--no-debug", default=False, show_default=True,
              help="Verbose diagnostics.")
def cli(prefix_or_url, out_dir: Path,
        include, exclude, contains, jobs, size, overwrite, debug):
    """
    Download an Iconify icon set as individual SVGs.

    PREFIX_OR_URL can be a set URL (e.g. https://icon-sets.iconify.design/fluent/)
    or a set prefix (e.g. fluent, mdi, tabler).
    """
    prefix = infer_prefix(prefix_or_url)
    out_dir.mkdir(parents=True, exist_ok=True)

    include_set = {s.strip() for s in include.split(",") if s.strip()} or None
    exclude_set = {s.strip() for s in exclude.split(",") if s.strip()} or None
    contains_str = contains.strip() or None

    with httpx.Client(http2=True, timeout=60) as client:
        # Try API; if it fails, GitHub fallback
        icon_names: list[str] = []
        info: dict = {}

        try:
            icon_names, info = list_from_api(client, prefix, debug)
            if debug:
                click.echo(f"[debug] API returned {len(icon_names)} icons for"
                           f" '{prefix}'",
                           err=True)
        except Exception as exc:
            print(exc)
            if debug:
                click.echo(f"[debug] Falling back to GitHub JSON for '{prefix}'",
                           err=True)
            icon_names, info = list_from_github(client, prefix, debug)
            if debug:
                click.echo(f"[debug] GitHub returned {len(icon_names)}"
                           f" icons for '{prefix}'",
                           err=True)

        if not icon_names:
            raise click.ClickException(f"No icons found for prefix '{prefix}'"
                                       f" (API and GitHub both empty).")

        names = filter_icons(icon_names, include_set, exclude_set, contains_str)
        if not names:
            raise click.ClickException("Filters removed all icons."
                                       " Try adjusting --include/--exclude/--contains.")

        write_license(out_dir, prefix, info)

        # Build worklist (skip existing unless --overwrite)
        to_fetch = []
        existing = 0
        for n in names:
            fp = out_dir / f"{prefix}-{n}.svg"
            if fp.exists() and not overwrite:
                existing += 1
            else:
                to_fetch.append(n)

        if debug:
            click.echo(f"[debug] {len(to_fetch)} to download,"
                       f" {existing} already present",
                       err=True)

        successes = 0
        failures = 0
        errors: list[tuple[str, str]] = []

        with ThreadPoolExecutor(
                max_workers=max(
                    1,jobs)) as pool, tqdm(total=len(to_fetch),
                                           unit="icon",
                                           desc=f"Downloading {prefix}") as pbar:
            futures = []
            for n in to_fetch:
                futures.append(pool.submit(fetch_svg, client, prefix, n, out_dir, size))
            for fut in as_completed(futures):
                name, ok, err = fut.result()
                if ok:
                    successes += 1
                else:
                    failures += 1
                    errors.append((name, err))
                pbar.update(1)

        msg = f"Done. {successes} downloaded"
        if existing:
            msg += f", {existing} already present"
        if failures:
            msg += f", {failures} failed"
        click.echo(msg)
        if failures and debug:
            for name, err in errors[:10]:
                click.echo(f"[debug] {name}: {err}", err=True)
            if len(errors) > 10:
                click.echo(f"[debug] ...and {len(errors) - 10} more errors.", err=True)


if __name__ == "__main__":
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
