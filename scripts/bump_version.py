"""Version management script for enabiz-ai.

Ensures pyproject.toml and src/enabiz_ai/__init__.py stay in sync,
and provides commands to increment minor version for each release/change.

Usage:
    python scripts/bump_version.py --current
    python scripts/bump_version.py --bump minor
    python scripts/bump_version.py --bump patch
    python scripts/bump_version.py --set 0.0.1
    python scripts/bump_version.py --check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
INIT_PY_PATH = REPO_ROOT / "src" / "enabiz_ai" / "__init__.py"
RELEASE_NOTES_PATH = REPO_ROOT / "RELEASE_NOTES.md"


def get_pyproject_version() -> str:
    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise ValueError(f"Could not find version string in {PYPROJECT_PATH}")
    return match.group(1)


def get_init_version() -> str:
    content = INIT_PY_PATH.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        raise ValueError(f"Could not find __version__ string in {INIT_PY_PATH}")
    return match.group(1)


def set_version(new_version: str) -> None:
    # Validate semver format
    if not re.match(r"^\d+\.\d+\.\d+$", new_version):
        raise ValueError(f"Invalid semver version format: {new_version}. Expected X.Y.Z")

    # Update pyproject.toml
    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    new_content, count = re.subn(
        r'^(version\s*=\s*)"[^"]+"',
        rf'\g<1>"{new_version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise ValueError("Failed to update version in pyproject.toml")
    PYPROJECT_PATH.write_text(new_content, encoding="utf-8")

    # Update src/enabiz_ai/__init__.py
    init_content = INIT_PY_PATH.read_text(encoding="utf-8")
    new_init_content, count = re.subn(
        r'^(__version__\s*=\s*)"[^"]+"',
        rf'\g<1>"{new_version}"',
        init_content,
        count=1,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise ValueError("Failed to update __version__ in src/enabiz_ai/__init__.py")
    INIT_PY_PATH.write_text(new_init_content, encoding="utf-8")

    print(f"✅ Successfully updated version to {new_version} in:")
    print(f"   - {PYPROJECT_PATH.relative_to(REPO_ROOT)}")
    print(f"   - {INIT_PY_PATH.relative_to(REPO_ROOT)}")


def parse_semver(version_str: str) -> tuple[int, int, int]:
    parts = version_str.strip().lstrip("v").split(".")
    if len(parts) != 3:
        raise ValueError(f"Cannot parse semver: {version_str}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def bump_version(part: str = "minor") -> str:
    curr = get_pyproject_version()
    major, minor, patch = parse_semver(curr)

    if part == "major":
        new_version = f"{major + 1}.0.0"
    elif part == "minor":
        new_version = f"{major}.{minor + 1}.0"
    elif part == "patch":
        new_version = f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f"Unknown bump part: {part}")

    set_version(new_version)
    return new_version


def check_consistency() -> bool:
    pyproject_v = get_pyproject_version()
    init_v = get_init_version()
    if pyproject_v != init_v:
        print(f"❌ Version mismatch! pyproject.toml={pyproject_v} != __init__.py={init_v}")
        return False
    print(f"✅ Versions are in sync: {pyproject_v}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="enabiz-ai Version Management")
    parser.add_argument("--current", action="store_true", help="Print current version")
    parser.add_argument("--check", action="store_true", help="Check version consistency")
    parser.add_argument(
        "--bump",
        choices=["major", "minor", "patch"],
        help="Increment version part (defaults to minor as per project policy)",
    )
    parser.add_argument("--set", dest="set_version", help="Set explicit version (e.g. 0.0.1)")

    args = parser.parse_args()

    if args.current:
        print(get_pyproject_version())
        return 0

    if args.check:
        return 0 if check_consistency() else 1

    if args.set_version:
        set_version(args.set_version)
        return 0

    if args.bump:
        bump_version(args.bump)
        return 0

    # Default if no arguments
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
