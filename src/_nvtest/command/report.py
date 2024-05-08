from typing import TYPE_CHECKING

from .. import plugin

if TYPE_CHECKING:
    from argparse import Namespace

    from ..config.argparsing import Parser


description = "Generate test reports"
epilog = "Note: this command must be run from inside of a test session directory."


def setup_parser(parser: "Parser") -> None:
    parent = parser.add_subparsers(dest="parent_command", metavar="")
    for hook in plugin.plugins("report", "setup"):
        type = hook.get_attribute("type")
        if type is None:
            raise ValueError(f"{hook.specname}: no type defined!")
        p = parent.add_parser(type, help=f"Generate {type} report")
        hook(p)


def report(args: "Namespace") -> int:
    for hook in plugin.plugins("report", "create"):
        type = hook.get_attribute("type") or ""
        if type == args.parent_command:
            hook(args)
            break
    else:
        raise ValueError(f"{args.parent_command}: unknown subcommand")
    return 0
