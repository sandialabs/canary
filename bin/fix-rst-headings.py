#!/usr/bin/env python3
"""Fix reStructuredText heading underline lengths.

This script walks one or more files/directories, finds .rst files, detects
simple section titles, and rewrites adornment lines so their visible length is
at least the title length.

It handles:

    Title
    =====

and:

    =====
    Title
    =====

It intentionally avoids changing adornment lines that do not look like section
title underlines/overlines.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ADORNMENT_CHARS = set("=-~^\"'`:#*+_")


def is_adornment_line(line: str) -> bool:
    """Return True if line is an RST section adornment line."""
    stripped = line.rstrip("\n")
    content = stripped.strip()
    if len(content) < 2:
        return False
    chars = set(content)
    return len(chars) == 1 and next(iter(chars)) in ADORNMENT_CHARS


def adornment_char(line: str) -> str:
    return line.strip()[0]


def indentation(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def visible_title_length(line: str) -> int:
    """Return title length excluding surrounding whitespace and newline."""
    return len(line.strip())


def fixed_adornment(line: str, title_line: str) -> str:
    """Return an adornment line with length matching title length."""
    indent = indentation(line)
    ch = adornment_char(line)
    n = max(len(line.strip()), visible_title_length(title_line))
    return f"{indent}{ch * n}\n"


def looks_like_title(line: str) -> bool:
    """Heuristic: a title is nonblank and not an adornment line."""
    if not line.strip():
        return False
    if is_adornment_line(line):
        return False
    return True


def fix_lines(lines: list[str]) -> tuple[list[str], int]:
    """Fix heading adornments in a list of lines."""
    out = list(lines)
    changed = 0
    i = 0
    n = len(out)

    while i < n:
        # Overline + title + underline:
        #
        #   =====
        #   Title
        #   =====
        if (
            i + 2 < n
            and is_adornment_line(out[i])
            and looks_like_title(out[i + 1])
            and is_adornment_line(out[i + 2])
            and adornment_char(out[i]) == adornment_char(out[i + 2])
        ):
            fixed_top = fixed_adornment(out[i], out[i + 1])
            fixed_bottom = fixed_adornment(out[i + 2], out[i + 1])

            if out[i] != fixed_top:
                out[i] = fixed_top
                changed += 1
            if out[i + 2] != fixed_bottom:
                out[i + 2] = fixed_bottom
                changed += 1

            i += 3
            continue

        # Title + underline:
        #
        #   Title
        #   =====
        if (
            i + 1 < n
            and looks_like_title(out[i])
            and is_adornment_line(out[i + 1])
        ):
            fixed = fixed_adornment(out[i + 1], out[i])
            if out[i + 1] != fixed:
                out[i + 1] = fixed
                changed += 1
            i += 2
            continue

        i += 1

    return out, changed


def iter_rst_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.rst")))
        elif path.is_file() and path.suffix == ".rst":
            files.append(path)
    return sorted(set(files))


def fix_file(path: Path, *, check: bool = False) -> int:
    original = path.read_text(encoding="utf-8").splitlines(keepends=True)
    fixed, changed = fix_lines(original)

    if changed and not check:
        path.write_text("".join(fixed), encoding="utf-8")

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fix reStructuredText heading underline lengths."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["doc/source"],
        help="Files or directories to scan [default: doc/source]",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not modify files; report files that would change.",
    )
    args = parser.parse_args()

    paths = [Path(p) for p in args.paths]
    files = iter_rst_files(paths)

    total_files = 0
    total_changes = 0

    for file in files:
        changes = fix_file(file, check=args.check)
        if changes:
            total_files += 1
            total_changes += changes
            action = "would fix" if args.check else "fixed"
            print(f"{action}: {file} ({changes} adornment line changes)")

    if args.check and total_changes:
        print(f"{total_changes} heading adornment changes needed in {total_files} files")
        return 1

    print(f"Done. {total_changes} heading adornment changes in {total_files} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
