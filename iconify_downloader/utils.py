from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse

import click

URL_PREFIX_RE = re.compile(
    r"(?:iconify.design/(?:icon-sets|icons)/|icon-sets.iconify.design/)"
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
    except Exception as exc:
        print(exc, file=sys.stderr)
    if STRICT_PREFIX_RE.match(s):
        return s.lower()
    raise click.ClickException(
        f"Cannot infer icon-set prefix from '{s}'. "
        "Use a prefix like 'fluent' or a set URL such as 'https://icon-sets.iconify.design/fluent/'."
    )


def filter_icons(names: Iterable[str],
                 include: set[str] | None,
                 exclude: set[str] | None,
                 contains: str | None) -> list[str]:
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
                f"Note: Some sets need attribution."
                f" Check upstream license before redistribution.\n"
            ),
            encoding="utf-8",
        )
