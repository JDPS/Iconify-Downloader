#!/usr/bin/env python3
# iconify_dl_plus.py — conservative variant that preserves original behavior and adds:
#   --json <file>      (offline/pinned listing from local JSON)
#   --no-prefix        (rename files after download to name.svg)
#   --by-category      (move files into per-category folders; works when JSON has categories)
#   --zip <file.zip>   (zip output directory after download)
#   --dry-run          (list actions; skip downloads)
#
# Design notes:
# - We DO NOT change list_from_api/list_from_github signatures or fetch_svg signature.
# - We add post-processing steps (rename/move/zip) to avoid touching download code paths.
# - Style: built-in generics (list[str], dict), annotations enabled via __future__.

from __future__ import annotations

import json
import re
import shutil
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
            parts = [x for x in p.path.split('/') if x]
            if parts:
                cand = parts[-1].lower().removesuffix('.json')
                if STRICT_PREFIX_RE.match(cand):
                    return cand
    except Exception:
        pass
    if STRICT_PREFIX_RE.match(s):
        return s.lower()
    raise click.ClickException(
        f"Cannot infer icon-set prefix from '{s}'. "
        "Use a prefix like 'fluent' or a set URL such as 'https://icon-sets.iconify.design/fluent/'."
    )


def list_from_api(client: httpx.Client, prefix: str, debug: bool) -> tuple[list[str], dict]:
    # 1) Check set exists
    r = client.get(f"{ICONIFY_API}/collections", params={"prefix": prefix}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict) or prefix not in data:
        if debug:
            click.echo(f"[debug] /collections did not contain '{prefix}'", err=True)
        raise click.ClickException(f"Iconify API: unknown prefix '{prefix}'")
    # 2) List icons
    r = client.get(f"{ICONIFY_API}/collection", params={"prefix": prefix, "info": "true"}, timeout=60)
    r.raise_for_status()
    col = r.json()
    icons = col.get("icons")
    if not isinstance(icons, list):
        if debug:
            keys = list(col.keys())
            click.echo(f"[debug] /collection icons not list (type={type(icons).__name__}), keys={keys}", err=True)
        raise click.ClickException("icons is not a list")
    info = col.get("info") or {}
    return [str(x) for x in icons], (info if isinstance(info, dict) else {})


def list_from_github(client: httpx.Client, prefix: str, debug: bool) -> tuple[list[str], dict, dict]:
    url = f"{GITHUB_RAW}/{prefix}.json"
    r = client.get(url, timeout=60)
    r.raise_for_status()
    data = r.json()
    icons_obj = data.get("icons")
    if not isinstance(icons_obj, dict):
        if debug:
            click.echo(f"[debug] GitHub JSON 'icons' is {type(icons_obj)}; top keys: {list(data.keys())}", err=True)
        raise click.ClickException(f"Unexpected JSON structure for '{prefix}'.")
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    categories = data.get("categories") if isinstance(data.get("categories"), dict) else {}
    return sorted(icons_obj.keys()), info, categories


def filter_icons(names: Iterable[str], include: set[str] | None, exclude: set[str] | None, contains: str | None) -> list[str]:
    out: list[str] = []
    for n in names:
        if include and n not in include:
            continue
        if exclude and n in exclude:
            continue
        if contains and contains.lower() not in n.lower():
            continue
        out.append(n)
    return out


def write_license(out_dir: Path, prefix: str, info: dict) -> None:
    lic = (info.get("license") or {}) if isinstance(info, dict) else {}
    lic_name = lic.get("title") or lic.get("name")
    lic_ref = lic.get("spdx") or lic.get("url")
    if lic_name or lic_ref:
        (out_dir / "LICENSE.txt").write_text(
            (
                f"Iconify set: {prefix}\n"
                f"License: {lic_name or 'N/A'}\n"
                f"Reference: {lic_ref or 'N/A'}\n"
                f"Note: Some sets need attribution. Check upstream license before redistribution.\n"
            ),
            encoding="utf-8",
        )


def fetch_svg(client: httpx.Client, prefix: str, name: str, out_dir: Path, size: int | None) -> tuple[str, bool, str]:
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
# New options (non-breaking to core flow)
@click.option("--json", "json_path", type=click.Path(path_type=Path), default=None,
              help="Use a local Iconify JSON file instead of API/GitHub listing.")
@click.option("--no-prefix", is_flag=True, help="Rename files to 'name.svg' after download.")
@click.option("--by-category", is_flag=True, help="Move files into category subfolders when available.")
@click.option("--zip", "zip_name", default=None, help="Zip output directory to this file when done.")
@click.option("--dry-run", is_flag=True, help="List actions without downloading files.")
def cli(prefix_or_url, out_dir: Path,
        include, exclude, contains, jobs, size, overwrite, debug,
        json_path, no_prefix, by_category, zip_name, dry_run):
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

    # List icons (prefer local JSON if provided)
    icon_names: list[str] = []
    categories: dict = {}
    info: dict = {}

    if json_path:
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        icons_obj = data.get("icons") or {}
        if not isinstance(icons_obj, dict):
            raise click.ClickException("Local JSON doesn't have dict 'icons'.")
        icon_names = sorted(icons_obj.keys())
        info = data.get("info") or {}
        if by_category and isinstance(data.get("categories"), dict):
            categories = data["categories"]
        if debug:
            click.echo(f"[debug] Local JSON listing: {len(icon_names)} icons", err=True)
    else:
        with httpx.Client(http2=True, timeout=60) as client:
            try:
                icon_names, info = list_from_api(client, prefix, debug)
                if debug:
                    click.echo(f"[debug] API returned {len(icon_names)} icons for '{prefix}'", err=True)
            except Exception as exc:
                if debug:
                    click.echo(f"[debug] /collection failed for '{prefix}': {exc}", err=True)
                    click.echo(f"[debug] Falling back to GitHub JSON for '{prefix}'", err=True)
                icon_names, info, categories = list_from_github(client, prefix, debug)
                if debug:
                    click.echo(f"[debug] GitHub returned {len(icon_names)} icons for '{prefix}'", err=True)

    if not icon_names:
        raise click.ClickException(f"No icons found for prefix '{prefix}' (API/GitHub/local JSON empty).")

    names = filter_icons(icon_names, include_set, exclude_set, contains_str)
    if not names:
        raise click.ClickException("Filters removed all icons. Try adjusting --include/--exclude/--contains.")

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
        click.echo(f"[debug] {len(to_fetch)} to download, {existing} already present", err=True)

    # Dry-run: just show what would be downloaded/moved
    if dry_run:
        click.echo(f"[dry-run] Would download {len(to_fetch)} icons into {out_dir}")
        if no_prefix:
            click.echo("[dry-run] Would rename files to 'name.svg'")
        if by_category and categories:
            click.echo("[dry-run] Would move files into category subfolders")
        if zip_name:
            click.echo(f"[dry-run] Would zip directory to {zip_name}")
        return

    # Download
    successes = 0
    failures = 0
    errors: list[tuple[str, str]] = []
    with httpx.Client(http2=True, timeout=60) as client:
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool, tqdm(total=len(to_fetch), unit="icon", desc=f"Downloading {prefix}") as pbar:
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

    # Post-processing: rename (no-prefix) and/or move into categories
    if no_prefix or (by_category and categories):
        moved = 0
        for n in names:
            src = out_dir / f"{prefix}-{n}.svg"
            if not src.exists():
                continue
            # target dir
            target_dir = out_dir
            if by_category and categories:
                # Build reverse map once
                # categories: { "category": [ "name", ... ] }
                # We'll scan memberships lazily
                cat_name = None
                for cat, members in categories.items():
                    if n in members:
                        cat_name = cat
                        break
                if cat_name:
                    target_dir = out_dir / cat_name
                    target_dir.mkdir(parents=True, exist_ok=True)
            # target filename
            dst_name = f"{n}.svg" if no_prefix else f"{prefix}-{n}.svg"
            dst = target_dir / dst_name
            if src.resolve() != dst.resolve():
                try:
                    shutil.move(str(src), str(dst))
                    moved += 1
                except Exception as exc:
                    if debug:
                        click.echo(f"[debug] move failed for {src} -> {dst}: {exc}", err=True)
        if debug:
            click.echo(f"[debug] Post-process moved/renamed {moved} files", err=True)

    # Zip
    if zip_name:
        base = Path(zip_name)
        archive_base = base.with_suffix("")
        shutil.make_archive(str(archive_base), "zip", out_dir)
        click.echo(f"Zipped to {archive_base}.zip")


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
