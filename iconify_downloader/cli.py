from __future__ import annotations

import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click
import httpx
from tqdm import tqdm

from .core import fetch_svg, list_from_api, list_from_github
from .utils import filter_icons, infer_prefix, write_license


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
@click.option("--json",
              "json_path",
              type=click.Path(path_type=Path),
              default=None,
              help="Use a local Iconify JSON file instead of API/GitHub listing.")
@click.option("--no-prefix",
              is_flag=True,
              help="Rename files to 'name.svg' after download.")
@click.option("--by-category",
              is_flag=True,
              help="Move files into category subfolders when available.")
@click.option("--zip", "zip_name",
              default=None,
              help="Zip output directory to this file when done.")
@click.option("--dry-run",
              is_flag=True,
              help="List actions without downloading files.")
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
                    click.echo(f"[debug] API returned {len(icon_names)} "
                               f"icons for '{prefix}'", err=True)
            except Exception as exc:
                if debug:
                    click.echo(f"[debug] /collection"
                               f" failed for '{prefix}': {exc}", err=True)
                    click.echo(f"[debug] Falling back to"
                               f" GitHub JSON for '{prefix}'", err=True)
                icon_names, info, categories = list_from_github(client, prefix, debug)
                if debug:
                    click.echo(f"[debug] GitHub returned"
                               f" {len(icon_names)} icons for '{prefix}'", err=True)

    if not icon_names:
        raise click.ClickException(f"No icons found for prefix"
                                   f" '{prefix}' (API/GitHub/local JSON empty).")

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
        click.echo(f"[debug] {len(to_fetch)} to download"
                   f", {existing} already present", err=True)

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
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool, tqdm(
                total=len(to_fetch),
                unit="icon",
                desc=f"Downloading {prefix}"
        ) as pbar:
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
                # Build the reverse map once
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
                        click.echo(f"[debug] move failed"
                                   f" for {src} -> {dst}: {exc}", err=True)
        if debug:
            click.echo(f"[debug] Post-process"
                       f" moved/renamed {moved} files", err=True)

    # Zip
    if zip_name:
        base = Path(zip_name)
        archive_base = base.with_suffix("")
        shutil.make_archive(str(archive_base), "zip", out_dir)
        click.echo(f"Zipped to {archive_base}.zip")
