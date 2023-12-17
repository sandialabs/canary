import argparse
import os
import re
import sys

import _nvtest.command

from ..config.argparsing import cmd_name
from ..config.argparsing import make_argument_parser
from ..third_party import argparsewriter as aw
from ..util import tty
from ..util.tty.colify import colify

description = "list available nvtest subcommands"
section = "developer"
level = "long"


section_descriptions = {
    "user": "user",
    "build": "build",
    "developer": "developer",
    "help": "more help",
    "spack": "spack integration",
}


#: list of command formatters
formatters = {}


def formatter(func):
    """Decorator used to register formatters"""
    formatters[func.__name__] = func
    return func


def setup_parser(subparser):
    subparser.add_argument(
        "-a",
        "--aliases",
        action="store_true",
        default=False,
        help="include command aliases",
    )
    subparser.add_argument(
        "--format",
        default="names",
        choices=formatters,
        help="format to be used to print the output (default: names)",
    )
    subparser.add_argument(
        "--header",
        metavar="FILE",
        default=None,
        action="store",
        help="prepend contents of FILE to the output (useful for rst format)",
    )
    subparser.add_argument(
        "--update",
        metavar="FILE",
        default=None,
        action="store",
        help="write output to the specified file, if any command is newer",
    )
    subparser.add_argument(
        "rst_files",
        nargs=argparse.REMAINDER,
        help="list of rst files to search for `_cmd-nvtest-<cmd>` cross-refs",
    )


class ArgparseRstWriter(aw.ArgparseRstWriter):
    """RST writer tailored for nevada documentation."""

    def __init__(
        self,
        prog,
        out=sys.stdout,
        aliases=False,
        documented_commands=[],
        rst_levels=["-", "-", "^", "~", ":", "`"],
    ):
        super(ArgparseRstWriter, self).__init__(prog, out, aliases, rst_levels)
        self.documented = documented_commands

    def usage(self, *args):
        string = super(ArgparseRstWriter, self).usage(*args)

        cmd = self.parser.prog.replace(" ", "-")
        if cmd in self.documented:
            string += "\n:ref:`More documentation <cmd-{0}>`\n".format(cmd)

        return string


class SubcommandWriter(aw.ArgparseWriter):
    def format(self, cmd):
        return "    " * self.level + cmd.prog + "\n"


_positional_to_subroutine = {
    "package": "_all_packages",
    "spec": "_all_packages",
    "filter": "_all_packages",
    "installed": "_installed_packages",
    "compiler": "_installed_compilers",
    "section": "_config_sections",
    "env": "_environments",
    "extendable": "_extensions",
    "keys": "_keys",
    "help_command": "_subcommands",
    "mirror": "_mirrors",
    "virtual": "_providers",
    "namespace": "_repos",
    "hash": "_all_resource_hashes",
    "pytest": "_tests",
}


class BashCompletionWriter(aw.ArgparseCompletionWriter):
    """Write argparse output as bash programmable tab completion."""

    def body(self, positionals, optionals, subcommands):
        if positionals:
            return """
    if $list_options
    then
        {0}
    else
        {1}
    fi
""".format(
                self.optionals(optionals), self.positionals(positionals)
            )
        elif subcommands:
            return """
    if $list_options
    then
        {0}
    else
        {1}
    fi
""".format(
                self.optionals(optionals), self.subcommands(subcommands)
            )
        else:
            return """
    {0}
""".format(
                self.optionals(optionals)
            )

    def positionals(self, positionals):
        # If match found, return function name
        for positional in positionals:
            for key, value in _positional_to_subroutine.items():
                if positional.startswith(key):
                    return value

        # If no matches found, return empty list
        return 'NEVADA_COMPREPLY=""'

    def optionals(self, optionals):
        return 'NEVADA_COMPREPLY="{0}"'.format(" ".join(optionals))

    def subcommands(self, subcommands):
        return 'NEVADA_COMPREPLY="{0}"'.format(" ".join(subcommands))


@formatter
def subcommands(args, out):
    parser = make_argument_parser()
    _nvtest.command.add_commands(parser)
    writer = SubcommandWriter(parser.prog, out, args.aliases)
    writer.write(parser)


def index_commands():
    """create an index of commands by section for this help level"""
    index = {}
    for cmd_module in _nvtest.command.all_commands():
        # make sure command modules have required properties
        cmd = cmd_name(cmd_module)
        for p in ("description",):
            prop = getattr(cmd_module, p, None)
            if not prop:
                tty.die("Command doesn't define a property {0!r}: {1}".format(p, cmd))

        # add commands to lists for their level and higher levels
        level_sections = index.setdefault("all", {})
        commands = level_sections.setdefault("user", [])
        commands.append(cmd)
    return index


def rst_index(out):
    out.write("\n")
    out.write("\n===============\nNVTest Commands\n===============\n")
    out.write("\n.. hlist::\n   :columns: 2\n\n")
    for cmd_module in _nvtest.command.all_commands():
        command = cmd_name(cmd_module)
        out.write("   * :ref:`%s <nvtest-%s>`\n" % (command, command))


@formatter
def rst(args, out):
    # create a parser with all commands
    tty.color.set_color_when("never")
    parser = make_argument_parser()
    _nvtest.command.add_commands(parser)

    # extract cross-refs of the form `_cmd-nvtest-<cmd>:` from rst files
    documented_commands = set()
    for filename in args.rst_files:
        with open(filename) as f:
            for line in f:
                match = re.match(r"\.\. _cmd-(nvtest-.*):", line)
                if match:
                    documented_commands.add(match.group(1).strip())

    # print an index to each command
    rst_index(out)
    out.write("\n")

    # print sections for each command and subcommand
    writer = ArgparseRstWriter(parser.prog, out, args.aliases, documented_commands)
    writer.write(parser)


@formatter
def names(args, out):
    commands = [cmd_name(cmd_module) for cmd_module in _nvtest.command.all_commands()]
    colify(commands, output=out)


@formatter
def bash(args, out):
    parser = make_argument_parser()
    _nvtest.command.add_commands(parser)

    writer = BashCompletionWriter(parser.prog, out, args.aliases)
    writer.write(parser)


def prepend_header(args, out):
    if not args.header:
        return

    with open(args.header) as header:
        out.write(header.read())


def commands(args: argparse.Namespace) -> int:
    """This is the 'regular' command, which can be called multiple times.

    See ``commands()`` below for ``--update-completion`` handling.
    """
    formatter = formatters[args.format]

    # check header first so we don't open out files unnecessarily
    if args.header and not os.path.exists(args.header):
        tty.die("No such file: '%s'" % args.header)

    # if we're updating an existing file, only write output if a command
    # or the header is newer than the file.
    if args.update:
        if os.path.exists(args.update):
            files = [
                cmd_module.__file__.rstrip("c")  # pyc -> py
                for cmd_module in _nvtest.command.all_commands()
            ]
            if args.header:
                files.append(args.header)
            last_update = os.path.getmtime(args.update)
            if not any(os.path.getmtime(f) > last_update for f in files):
                tty.emit("File is up to date: %s\n" % args.update)
                return 0

        tty.emit("Updating file: %s\n" % args.update)
        with open(args.update, "w") as f:
            prepend_header(args, f)
            formatter(args, f)

    else:
        prepend_header(args, sys.stdout)
        formatter(args, sys.stdout)

    return 0
