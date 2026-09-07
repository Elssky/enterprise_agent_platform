#!/usr/bin/env python3
"""Check public README and deployed MkDocs links."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_BASE = "https://elssky.github.io/enterprise_agent_platform/"
LEGACY_BASES = [
    "https://datagallery-lab.github.io/enterprise_agent_platform/",
    "https://datagallery-lab.github.io/enterprise_agent_platform_engineering/",
]

FILES = [
    "README.md",
    "README_en.md",
    "README_zh.md",
    "mkdocs.optimized.yml",
]


def main() -> int:
    failed = False
    for rel_path in FILES:
        path = ROOT / rel_path
        text = path.read_text(encoding="utf-8")

        for legacy_base in LEGACY_BASES:
            if legacy_base in text:
                print(f"{rel_path}: contains legacy Pages URL {legacy_base}")
                failed = True

        if PUBLIC_BASE not in text:
            print(f"{rel_path}: missing current Pages URL {PUBLIC_BASE}")
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
