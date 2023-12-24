import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config.argparsing import Parser

description = "list contents of directories in a tree-like format"


def setup_parser(parser: "Parser"):
    parser.add_argument(
        "-a",
        action="store_true",
        default=False,
        help="All files are printed. By default, hidden files are not printed",
    )
    parser.add_argument(
        "-d", action="store_true", default=False, help="List directories only"
    )
    parser.add_argument("-i", action="append", help="Ignore pattern")
    parser.add_argument("directory")


def tree(args: "argparse.Namespace") -> int:
    _tree(args.directory, limit_to_directories=args.d, skip_hidden=not args.a)
    return 0


def _tree(
    directory: str,
    level: int = -1,
    limit_to_directories: bool = False,
    skip_hidden: bool = True,
    dont_descend=None,
    indent="",
):
    """Given a directory Path object print a visual tree structure"""
    from pathlib import Path

    dont_descend = dont_descend or []
    stream = sys.stdout
    space = "    "
    branch = "│   "
    tee = "├── "
    last = "└── "
    dir_path = Path(directory)
    files = 0
    directories = 0

    def inner(dir_path: Path, prefix: str = "", level=-1):
        nonlocal files, directories
        if not level:
            return  # 0, stop iterating
        if limit_to_directories:
            contents = [d for d in dir_path.iterdir() if d.is_dir()]
        else:
            contents = sorted(dir_path.iterdir())
        if skip_hidden:
            contents = [_ for _ in contents if not _.name.startswith(".")]
        pointers = [tee] * (len(contents) - 1) + [last]
        for pointer, path in zip(pointers, contents):
            if skip_hidden and path.name.startswith("."):
                continue
            if path.is_dir():
                yield prefix + pointer + path.name
                directories += 1
                extension = branch if pointer == tee else space
                if path.name in dont_descend:
                    break
                yield from inner(path, prefix=prefix + extension, level=level - 1)
            elif not limit_to_directories:
                yield prefix + pointer + path.name
                files += 1

    stream.write(f"{indent}{dir_path}\n")
    iterator = inner(dir_path, level=level)
    for line in iterator:
        stream.write(f"{indent}{line}\n")
