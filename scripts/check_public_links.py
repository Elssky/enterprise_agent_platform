#!/usr/bin/env python3
"""Check public README and MkDocs links after repository renames."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_BASE = "https://datagallery-lab.github.io/enterprise_agent_platform/"
LEGACY_BASE = "https://datagallery-lab.github.io/enterprise_agent_platform_engineering/"

FILES = [
    "README.md",
    "README_en.md",
    "README_zh.md",
    "mkdocs.yml",
    "mkdocs.en.yml",
]


def main() -> int:
    failed = False
    for rel_path in FILES:
        path = ROOT / rel_path
        text = path.read_text(encoding="utf-8")

        if LEGACY_BASE in text:
            print(f"{rel_path}: contains legacy Pages URL {LEGACY_BASE}")
            failed = True

        if PUBLIC_BASE not in text:
            print(f"{rel_path}: missing current Pages URL {PUBLIC_BASE}")
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
