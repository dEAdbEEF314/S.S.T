# CLI Implementation TODO List (Act-10)

## 1. Core UX
- [ ] Implement `Rich` based multi-progress bars.
- [ ] Create a final result summary table.
- [ ] Implement interactive approval prompt for LLM results.

## 2. Command Line Interface
- [ ] Switch to `Click` or `Typer` for subcommands.
- [ ] Implement `scout review list`.
- [ ] Implement `scout review inspect <AppID>`.

## 3. Data Flow & Integrity
- [ ] Complete removal of S3 upload logic from `processor.py`.
- [ ] Refine ZIP packaging to include ALL necessary logs.
- [ ] Ensure `output/` structure is consistent (`archive/` vs `review/`).

## 4. Maintenance
- [ ] Deprecate `ui/` directory and related Docker services.
- [ ] Update `AGENT_GUIDE.md` to reflect the CLI-first workflow.
