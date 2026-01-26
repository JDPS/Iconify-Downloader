# Iconify Downloader (CLI)

A simple command-line tool to **bulk-download Iconify icon sets** as SVG files.  
It supports online and offline modes, JSON-based listing, category grouping, zipping, and dry-run previews — all while keeping the workflow clean and minimal.

---

## ✨ Features

- ✅ Download complete Iconify icon sets via API or GitHub JSON
- 🧭 Supports URLs or prefixes (e.g. `fluent`, `mdi`, `tabler`, etc.)
- 📦 Offline / pinned listing from a local JSON (`--json <file>`)
- 🗂 Group icons into category folders (`--by-category`)
- 🏷 Save as `name.svg` instead of `prefix-name.svg` (`--no-prefix`)
- 🪣 Zip results after download (`--zip <file.zip>`)
- 🧪 Dry-run mode (`--dry-run`) to preview without downloading
- 🧵 Multithreaded downloads (fast and reliable)
- 🪶 Pure-Python, single-file tool — no external dependencies beyond `click`, `httpx`, and `tqdm`

---

## 🧰 Installation

### 1. Clone or copy the script

```bash
git clone https://github.com/JDPS/Iconify-Downloader.git
cd iconify-downloader
```

### 2. Install the package

Using **uv** (recommended):

```bash
uv sync
```

Or using **pip**:

```bash
pip install .
```

## 🚀 Usage

### Basic example

Download all icons from a collection using the installed CLI:

```bash
iconify-dl lucide-lab -o ./icons
```

Or using `python -m`:

```bash
python -m iconify_downloader lucide-lab -o ./icons
```

Or using `uv run`:

```bash
uv run iconify-dl lucide-lab -o ./icons
```

If `/collection` isn’t flat, the script automatically falls back to GitHub JSON and downloads from there.

---

### Offline / pinned listing

Download once from GitHub:

```bash
curl -LO https://raw.githubusercontent.com/iconify/icon-sets/master/json/fluent.json
```

Then run without network dependency:

```bash
iconify-dl fluent -o ./icons --json fluent.json
```

---

### Rename files (no prefix)

```bash
iconify-dl mdi -o ./mdi --contains arrow --no-prefix
```

---

### Group by category

```bash
iconify-dl tabler -o ./tabler --by-category
```

---

### Dry run (no downloads)

```bash
iconify-dl https://icon-sets.iconify.design/lucide-lab/ -o ./icons --dry-run
```

---

### Zip results after download

```bash
iconify-dl fluent -o ./icons --zip fluent_icons.zip
```

---

## 🧩 Options Reference

| Option                       | Description                                                      |
| ---------------------------- | ---------------------------------------------------------------- |
| `PREFIX_OR_URL`              | Iconify prefix (`fluent`, `mdi`, `tabler`, etc.) or full set URL |
| `-o, --out`                  | Output directory (default: `./iconify_svgs`)                     |
| `--include`                  | Comma-separated list of icons to include                         |
| `--exclude`                  | Comma-separated list of icons to exclude                         |
| `--contains`                 | Substring filter for icon names                                  |
| `-j, --jobs`                 | Number of concurrent downloads (default: 12)                     |
| `--size`                     | Icon height (in pixels)                                          |
| `--overwrite/--no-overwrite` | Overwrite existing files (default: `False`)                      |
| `--debug`                    | Show detailed logs                                               |
| `--json`                     | Use a local Iconify JSON instead of API/GitHub                   |
| `--no-prefix`                | Save icons as `name.svg` instead of `prefix-name.svg`            |
| `--by-category`              | Organize icons into folders by category (when available)         |
| `--zip`                      | Zip output directory to this file                                |
| `--dry-run`                  | Show planned actions without downloading                         |

---

## 🧾 Example Output

```go
Downloading fluent: 18973icon [02:19, 136.24icon/s]
Done. 18973 downloaded
Zipped to fluent_icons.zip
```

## ⚙️ Development Notes

- Uses official [Iconify API](https://iconify.design/docs/api/?utm_source=chatgpt.com) and [icon-sets GitHub repo](https://github.com/iconify/icon-sets?utm_source=chatgpt.com).
- Written for **Python 3.11+**, no type-hint imports (`list[str]`, not `List[str]`).
- Compatible with PowerShell 7+, Bash, and macOS/Linux terminals.
- Safe retries: if the API returns a structured collection instead of a flat list, the script automatically falls back to GitHub JSON.
- When `--dry-run` is active, **no network writes or file saves** occur.

## 🪪 License

This script itself is released under the **MIT License**.
 Downloaded icon sets remain under their respective **Iconify / upstream licenses**.
 Always verify licensing terms in the generated `LICENSE.txt` file before redistribution.

---

## 💡 Credits

- **Script author:** João Soares
- **Data sources:** [Iconify](https://iconify.design?utm_source=chatgpt.com) · [Iconify icon-sets GitHub](https://github.com/iconify/icon-sets?utm_source=chatgpt.com)
