# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse
import importlib.resources as ir
import os
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from ..hookspec import hookimpl
from ..util.filesystem import force_copy
from .base import CanarySubcommand

if TYPE_CHECKING:
    from ..config.argparsing import Parser


SKILLS_PACKAGE = "canary"
SKILLS_DIR = "skills"
SKILL_FILE = "SKILL.md"


@hookimpl
def canary_addcommand(parser: "Parser") -> None:
    parser.add_command(Fetch())


class Fetch(CanarySubcommand):
    name = "fetch"
    description = "Fetch canary assets"

    def setup_parser(self, parser: "Parser") -> None:
        parser.add_argument(
            "what",
            choices=("examples", "canary.cmake", "skills"),
            type=str.lower,
            help="Asset to fetch",
        )
        parser.add_argument(
            "name",
            nargs="?",
            help=(
                "Name of a specific skill to fetch when WHAT is 'skills'. "
                "If omitted, all bundled Canary skills are fetched."
            ),
        )
        parser.add_argument(
            "-d",
            "--dest",
            dest="fetch_dest",
            metavar="DEST",
            help=(
                "Destination path for fetched skills. Applies only to WHAT='skills'. "
                "For a single skill, DEST is the skill directory. For all skills, "
                "DEST is the parent skills directory."
            ),
        )
        parser.add_argument(
            "--list",
            dest="list_skills",
            action="store_true",
            help="List bundled Canary skills instead of fetching them. Applies only to WHAT='skills'.",
        )

    def execute(self, args: argparse.Namespace) -> int:
        name = getattr(args, "name", None)
        fetch_dest = getattr(args, "fetch_dest", None)
        list_skills = getattr(args, "list_skills", False)
        if args.what == "examples":
            if name is not None:
                raise ValueError("canary fetch examples does not accept a NAME argument")
            if fetch_dest is not None:
                raise ValueError("-d/--dest is only valid with 'canary fetch skills'")
            if list_skills:
                raise ValueError("--list is only valid with 'canary fetch skills'")
            path = str(ir.files("canary").joinpath("examples"))
            if os.path.exists("examples"):
                raise ValueError(f"A folder named 'examples' already exists at {os.getcwd()}")
            force_copy(path, os.path.basename(path))

        elif args.what.lower() == "canary.cmake":
            if name is not None:
                raise ValueError("canary fetch canary.cmake does not accept a NAME argument")
            if fetch_dest is not None:
                raise ValueError("-d/--dest is only valid with 'canary fetch skills'")
            if list_skills:
                raise ValueError("--list is only valid with 'canary fetch skills'")
            path = str(ir.files("canary_cmake").joinpath("Canary.cmake"))
            with open(os.path.basename(path), "w") as fh:
                fh.write(open(path).read())

        elif args.what == "skills":
            if list_skills:
                if name is not None:
                    raise ValueError("canary fetch skills --list does not accept a NAME argument")
                if fetch_dest is not None:
                    raise ValueError("canary fetch skills --list does not accept -d/--dest")
                for skill in list_bundled_skills():
                    print(skill)
                return 0

            if name:
                fetch_skill(name, dest=fetch_dest)
            else:
                fetch_all_skills(dest=fetch_dest or SKILLS_DIR)

        else:
            raise ValueError(f"Unknown option to fetch {args.what!r}")

        return 0


def skills_root() -> Any:
    return ir.files(SKILLS_PACKAGE).joinpath(SKILLS_DIR)


def list_bundled_skills() -> list[str]:
    root = skills_root()

    if not root.is_dir():
        return []

    skills: list[str] = []
    for entry in root.iterdir():
        if entry.is_dir() and entry.joinpath(SKILL_FILE).is_file():
            skills.append(entry.name)

    return sorted(skills)


def get_skill_resource(name: str) -> Any:
    if name not in list_bundled_skills():
        raise UnknownSkillError(name, list_bundled_skills())
    return skills_root().joinpath(name)


def fetch_skill(name: str, dest: str | os.PathLike[str] | None = None) -> Path:
    src = get_skill_resource(name)
    target = Path(dest or name)

    if target.exists():
        raise ValueError(f"{target}: already exists")

    copy_traversable(src, target)
    return target


def fetch_all_skills(dest: str | os.PathLike[str] = SKILLS_DIR) -> Path:
    target = Path(dest)

    if target.exists():
        raise ValueError(f"{target}: already exists")

    skill_names = list_bundled_skills()
    if not skill_names:
        raise ValueError("No bundled Canary skills found")

    target.mkdir(parents=True)

    try:
        for name in skill_names:
            copy_traversable(get_skill_resource(name), target / name)
    except Exception:
        # Keep error behavior simple and explicit.  Do not silently leave a partial tree
        # if a resource copy fails.
        import shutil

        shutil.rmtree(target, ignore_errors=True)
        raise

    return target


def copy_traversable(src: Any, dst: Path) -> None:
    """
    Recursively copy an importlib.resources Traversable into the filesystem.

    This works for ordinary source trees and installed wheels without hard-coding
    a development checkout path.
    """
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=False)
        for child in src.iterdir():
            copy_traversable(child, dst / child.name)
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


class UnknownSkillError(ValueError):
    def __init__(self, name: str, available: list[str]) -> None:
        if available:
            message = f"Unknown Canary skill {name!r}. Available skills: {', '.join(available)}"
        else:
            message = f"Unknown Canary skill {name!r}. No bundled Canary skills are available."
        super().__init__(message)
