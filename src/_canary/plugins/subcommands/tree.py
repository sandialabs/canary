import argparse
import os
import sys

from ...config.argparsing import Parser
from ..hookspec import hookimpl
from ..types import CanarySubcommand


@hookimpl
def canary_subcommand() -> CanarySubcommand:
    return CanarySubcommand(
        name="tree",
        add_help=False,
        description="list contents of directories in a tree-like format",
        setup_parser=setup_parser,
        execute=tree,
    )


def setup_parser(parser: "Parser") -> None:
    parser.add_argument(
        "-a",
        action="store_true",
        default=False,
        help="All files are printed. By default, hidden files are not printed",
    )
    parser.add_argument("-d", action="store_true", default=False, help="List directories only")
    parser.add_argument("-i", action="append", help="Ignore pattern")
    parser.add_argument(
        "--exclude-results",
        default=False,
        action="store_true",
        help="Exclude test result directories",
    )
    parser.add_argument("directory")


def tree(args: "argparse.Namespace") -> int:
    _tree(
        args.directory,
        limit_to_directories=args.d,
        skip_hidden=not args.a,
        exclude_results=args.exclude_results,
    )
    return 0


def _tree(
    directory: str,
    level: int = -1,
    limit_to_directories: bool = False,
    skip_hidden: bool = True,
    dont_descend=None,
    exclude_results: bool = False,
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
    always_exclude = ("__pycache__", ".git", ".canary")

    def is_results_dir(p):
        return os.path.exists(os.path.join(p, ".canary/SESSION.TAG"))

    def inner(dir_path: Path, prefix: str = "", level=-1):
        nonlocal files, directories
        if not level:
            return  # 0, stop iterating
        contents: list[Path]
        if os.path.basename(dir_path) in always_exclude:
            contents = []
        elif exclude_results and is_results_dir(dir_path):
            contents = []
        elif limit_to_directories:
            contents = [d for d in dir_path.iterdir() if d.is_dir()]
        else:
            contents = sorted(dir_path.iterdir())
        if skip_hidden:
            contents = [_ for _ in contents if not _.name.startswith(".")]
        if exclude_results:
            contents = [_ for _ in contents if not is_results_dir(_)]
        contents = [_ for _ in contents if os.path.basename(_) not in always_exclude]
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
                name = path.name
                if path.is_symlink():
                    name += "@"
                yield prefix + pointer + name
                files += 1

    stream.write(f"{indent}{dir_path}\n")
    iterator = inner(dir_path, level=level)
    for line in iterator:
        stream.write(f"{indent}{line}\n")
