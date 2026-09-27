"""Documentation and Release Synchronization Validator.

Enforces:
1. Version synchronization between pyproject.toml and src/enabiz_ai/__init__.py.
2. English release notes (RELEASE_NOTES.md) contain entries for the current active version.
3. Dual-language documentation parity: README.md (EN) and README.tr.md (TR).
4. When invoked in git pre-commit mode, verifies that code updates include release notes
   and that changes to one language README are mirrored in the other.

Usage:
    python scripts/check_docs_sync.py               # Full health check
    python scripts/check_docs_sync.py --pre-commit  # Run as git pre-commit hook
    python scripts/check_docs_sync.py --warn-only   # Exit 0 even on warnings (for advisory hooks)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
INIT_PY_PATH = REPO_ROOT / "src" / "enabiz_ai" / "__init__.py"
RELEASE_NOTES_PATH = REPO_ROOT / "RELEASE_NOTES.md"
README_EN_PATH = REPO_ROOT / "README.md"
README_TR_PATH = REPO_ROOT / "README.tr.md"


def get_version(path: Path, pattern: str) -> str | None:
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    match = re.search(pattern, content, re.MULTILINE)
    return match.group(1) if match else None


def get_staged_files() -> list[str]:
    try:
        res = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        return [line.strip().replace("\\", "/") for line in res.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def check_version_sync(errors: list[str]) -> str | None:
    pyproject_v = get_version(PYPROJECT_PATH, r'^version\s*=\s*"([^"]+)"')
    init_v = get_version(INIT_PY_PATH, r'^__version__\s*=\s*"([^"]+)"')

    if not pyproject_v:
        errors.append(f"Could not read version from {PYPROJECT_PATH}")
        return None
    if not init_v:
        errors.append(f"Could not read __version__ from {INIT_PY_PATH}")
        return None

    if pyproject_v != init_v:
        errors.append(
            f"Version mismatch: pyproject.toml ({pyproject_v}) != __init__.py ({init_v})"
        )
        return None

    return pyproject_v


def check_release_notes(current_version: str | None, errors: list[str]) -> None:
    if not RELEASE_NOTES_PATH.exists():
        errors.append(f"Missing release notes file: {RELEASE_NOTES_PATH}")
        return

    content = RELEASE_NOTES_PATH.read_text(encoding="utf-8")
    if current_version:
        pattern = rf"^##\s*\[{re.escape(current_version)}\]"
        if not re.search(pattern, content, re.MULTILINE):
            errors.append(
                f"RELEASE_NOTES.md missing section for current version [{current_version}]"
            )


def check_readme_parity(errors: list[str], warnings: list[str]) -> None:
    if not README_EN_PATH.exists():
        errors.append("Missing English documentation: README.md")
    if not README_TR_PATH.exists():
        errors.append("Missing Turkish documentation: README.tr.md")


def check_git_staged(errors: list[str], warnings: list[str], strict: bool = False) -> None:
    staged = get_staged_files()
    if not staged:
        return

    has_code_changes = any(f.startswith("src/enabiz_ai/") for f in staged)
    readme_en_staged = "README.md" in staged
    readme_tr_staged = "README.tr.md" in staged
    release_notes_staged = "RELEASE_NOTES.md" in staged

    # Check 1: If one README is modified, the other should also be modified
    if readme_en_staged and not readme_tr_staged:
        msg = "README.md (English) was modified, but README.tr.md (Turkish) was not staged!"
        if strict:
            errors.append(msg)
        else:
            warnings.append(msg)
    elif readme_tr_staged and not readme_en_staged:
        msg = "README.tr.md (Turkish) was modified, but README.md (English) was not staged!"
        if strict:
            errors.append(msg)
        else:
            warnings.append(msg)

    # Check 2: If code in src/enabiz_ai/ is modified, check release notes
    if has_code_changes and not release_notes_staged:
        msg = "Source code in src/enabiz_ai/ modified, but RELEASE_NOTES.md was not updated/staged."
        warnings.append(msg)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check documentation and release sync")
    parser.add_argument(
        "--pre-commit", action="store_true", help="Run in git pre-commit mode (checks staged files)"
    )
    parser.add_argument(
        "--warn-only", action="store_true", help="Do not exit with non-zero on errors, only print"
    )
    parser.add_argument(
        "--strict", action="store_true", help="Treat documentation parity warnings as errors"
    )

    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    current_version = check_version_sync(errors)
    check_release_notes(current_version, errors)
    check_readme_parity(errors, warnings)

    if args.pre_commit:
        check_git_staged(errors, warnings, strict=args.strict)

    # Print results
    print("=" * 60)
    print(" e-Nabız AI — Documentation & Version Synchronization Check")
    print("=" * 60)

    if current_version:
        print(f"📦 Active Version: v{current_version}")

    if not errors and not warnings:
        print("✅ All documentation, release notes, and version checks PASSED!")
        return 0

    if warnings:
        print("\n⚠️  Warnings:")
        for w in warnings:
            print(f"   - {w}")

    if errors:
        print("\n❌ Errors:")
        for e in errors:
            print(f"   - {e}")
        if not args.warn_only:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
