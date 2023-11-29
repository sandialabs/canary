import argparse
import code
import os
import platform
import sys

from ..config.argparsing import Parser

description = "launch an interpreter as nvtest would launch a command"


def setup_parser(subparser: Parser):
    subparser.add_argument("-c", dest="python_command", help="command to execute")
    subparser.add_argument(
        "python_args", nargs=argparse.REMAINDER, help="file to run plus arguments"
    )


def python(args: argparse.Namespace):
    import nvtest

    # Fake a main python shell by setting __name__ to __main__.
    python_args = args.python_args
    python_command = args.python_command
    env = {"__name__": "__main__", "nvtest": nvtest}
    if not python_command and python_args:
        env["__file__"] = python_args[0]
    console = code.InteractiveConsole(env)

    if "PYTHONSTARTUP" in os.environ:
        startup_file = os.environ["PYTHONSTARTUP"]
        if os.path.isfile(startup_file):
            with open(startup_file) as startup:
                console.runsource(startup.read(), startup_file, "exec")

    sys.path.insert(0, os.getcwd())

    if python_command:
        console.runsource(python_command)
    elif python_args:
        sys.argv = python_args
        python_file = python_args[0]
        sys.path.insert(0, os.path.dirname(python_file))
        with open(python_file) as file:
            console.runsource(file.read(), python_file, "exec")
    else:
        # Provides readline support, allowing user to use arrow keys
        console.push("import readline")
        console.interact(
            "nvtest version %s\nPython %s, %s %s"
            ""
            % (
                nvtest.version,
                platform.python_version(),
                platform.system(),
                platform.machine(),
            )
        )
