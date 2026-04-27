# CLI Reconstruction Plan

SST is transitioning from a Web-based dashboard to a powerful, interactive Command Line Interface (CLI). This ensures maximum efficiency for edge processing and eliminates the need for separate UI containers.

## 1. Vision: "Rich Edge CLI"
The new CLI will use the `Rich` library to provide a modern terminal experience, featuring:
- **Live Progress**: Multi-task progress bars using the `Rich` library:
    - **Overall Progress**: Fixed at the bottom showing the total queue status.
    - **Per-Album Progress**: Dynamic bars for each active parallel worker, showing track-level completion.
    - **History Persistence**: Finished albums leave a clean result line (✓) in the scrollback history.
- **Localized Tables**: Summary of review-required items formatted in clean, localized (ja/en) tables.

## 2. Command Structure (Planned)

### `scout run` (The main pipeline)
- `--interactive`: Wait for user input after LLM consolidation.
- `--limit N`: Process only N albums.
- `--force`: Ignore the local database and re-process.

### `scout review` (Review Queue Management)
- `list`: Show all albums in the `output/review/` directory.
- `inspect <AppID>`: Show the LLM log and raw metadata for a specific album in the terminal.
- `approve <AppID>`: Move an album from `review/` to `archive/` (after manual tagging).

### `scout log`
- Show the last N processing logs.
- Stream live logs from a running process.

## 3. UI to CLI Mapping (Migration)

| Web UI Feature | CLI Equivalent |
| :--- | :--- |
| Dashboard Album List | `scout review list` / Post-run summary table |
| Metadata Inspector | `scout review inspect` (Rich Table/JSON output) |
| LLM Log View | `scout review inspect` (Markdown output) |
| Reprocess Button | `scout run --force --app-id <ID>` |
| Bulk Delete | Standard shell commands (`rm -rf output/review/*`) |

## 4. Technical Tasks

### UX/UI
- [ ] Implement `rich.progress` for the `LocalProcessor` loop.
- [ ] Implement `rich.table` for the final summary.
- [ ] Add a CLI prompt (using `rich.console` or `questionary`) for interactive metadata approval.

### Logic
- [ ] Refactor `main.py` to use `click` or `typer` for robust command-line argument handling.
- [ ] Expand the SQLite database to track "Manual Review" status more accurately.
- [ ] Implement a simple pager for viewing long LLM logs in the terminal.
