"""Installer for Git pre-commit hooks in enabiz-ai.

Installs a pre-commit hook that validates:
1. Version synchronization
2. English release notes updates
3. Dual-language documentation parity (README.md & README.tr.md)
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
GIT_HOOKS_DIR = REPO_ROOT / ".git" / "hooks"
PRE_COMMIT_FILE = GIT_HOOKS_DIR / "pre-commit"

HOOK_CONTENT = """#!/bin/sh
# Git pre-commit hook for enabiz-ai
# Enforces versioning, release notes, and documentation parity.

if [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON=".venv/Scripts/python.exe"
elif [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="python"
fi

"$PYTHON" scripts/check_docs_sync.py --pre-commit
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "❌ Pre-commit hook failed! Please fix the errors above before committing."
    echo "Tip: update both README.md and README.tr.md, ensure RELEASE_NOTES.md has the current version,"
    echo "and verify pyproject.toml matches src/enabiz_ai/__init__.py."
    exit $EXIT_CODE
fi

exit 0
"""


def install_hook() -> int:
    if not GIT_HOOKS_DIR.exists():
        print(f"❌ Git hooks directory not found at {GIT_HOOKS_DIR}. Is this a git repo?")
        return 1

    try:
        # Write pre-commit hook with LF line endings
        PRE_COMMIT_FILE.write_bytes(HOOK_CONTENT.replace("\r\n", "\n").encode("utf-8"))
        # Set executable permissions where supported
        try:
            PRE_COMMIT_FILE.chmod(0o755)
        except Exception:
            pass

        print(f"✅ Successfully installed Git pre-commit hook to:")
        print(f"   {PRE_COMMIT_FILE.relative_to(REPO_ROOT)}")
        return 0
    except Exception as e:
        print(f"❌ Failed to install hook: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(install_hook())
