# Documentation, Versioning & Release Notes Rules

## 1. Dual-Language Documentation Parity
- The repository maintains two parallel primary documentation files:
  - `README.md` (English)
  - `README.tr.md` (Turkish)
- **Rule:** Whenever any feature, CLI command, configuration, or architectural component is added or modified, BOTH `README.md` and `README.tr.md` **MUST** be updated in tandem.
- Never update only one language file. Keep code snippets, architecture diagrams, and command examples identical in structure across both files.

## 2. Versioning Policy
- Current baseline version started at `0.0.1`.
- **Rule:** For each notable feature set or release, increment the **minor** version (e.g. `0.0.1` -> `0.1.0` -> `0.2.0`).
- Always keep `pyproject.toml` (`version = "..."`) and `src/enabiz_ai/__init__.py` (`__version__ = "..."`) strictly identical.
- Use `python scripts/bump_version.py --bump minor` (or `--check`) to automate or verify version consistency.

## 3. English Release Notes
- The repository maintains `RELEASE_NOTES.md` in English following the [Keep a Changelog](https://keepachangelog.com/) standard.
- **Rule:** For every minor version increment or notable code update, update `RELEASE_NOTES.md` with:
  - The version and date (e.g. `## [0.1.0] - 2026-09-27`)
  - Subsections: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`, and `Tests`.

## 4. Pre-Commit & Verification
- Run `python scripts/check_docs_sync.py` to verify documentation, release notes, and version consistency before finishing any task or committing changes.
