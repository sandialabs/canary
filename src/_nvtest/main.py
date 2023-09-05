import os
import sys
from typing import Optional

from .error import StopExecution
from .session import ExitCode
from .session import factory
from .util import tty


def main(argv: Optional[list[str]] = None) -> int:
    """Perform an in-process test run.

    :param args:
        List of command line arguments. If `None` or not given, defaults to reading
        arguments directly from the process command line (:data:`sys.argv`).

    :returns: An exit code.
    """
    initstate: int = 0
    session = factory(args=argv or sys.argv[1:], dir=os.getcwd())
    session.exitstatus = ExitCode.OK
    try:
        session.startup()
        initstate = 1
        session.exitstatus = session.run() or 0
    except KeyboardInterrupt:
        session.exitstatus = ExitCode.INTERRUPTED
    except StopExecution as e:
        tty.error(e.message)
        session.exitstatus = e.exit_code
    except TimeoutError as e:
        tty.error(e.args[0])
        session.exitstatus = ExitCode.TIMEOUT
    except SystemExit as ex:
        session.exitstatus = ex.code
    except BaseException as ex:
        session.exitstatus = ExitCode.INTERNAL_ERROR
        error_msg = ", ".join(str(_) for _ in ex.args)
        tty.error(error_msg)
        reraise = False
        if initstate and session.config.debug:
            reraise = True
        elif "--debug" in sys.argv:
            reraise = True
        if reraise:
            raise
    finally:
        os.chdir(session.startdir)
        if initstate >= 1:
            session.teardown()
    return session.exitstatus


def console_main() -> int:
    """The CLI entry point of nvtest.

    This function is not meant for programmable use; use `main()` instead.
    """
    try:
        returncode = main()
        sys.stdout.flush()
        return returncode
    except BrokenPipeError:
        # Python flushes standard streams on exit; redirect remaining output
        # to devnull to avoid another BrokenPipeError at shutdown
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 1  # Python exits with error code 1 on EPIPE
