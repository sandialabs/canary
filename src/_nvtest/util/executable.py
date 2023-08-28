import os
import re
import shlex
import subprocess

from ..error import timeout_exit_status
from ..util import tty

__all__ = ["Executable", "ProcessError"]


class Executable:
    """Class representing a program that can be run on the command line."""

    def __init__(self, name):
        self.exe = shlex.split(str(name))
        self.default_env = {}
        self.returncode = None
        self.cmd_line = None
        self.begin_callback = None

        if not self.exe:
            raise ProcessError("Cannot construct executable for '%s'" % name)

    def add_default_arg(self, *args):
        """Add a default argument to the command."""
        self.exe.extend(args)

    add_default_args = add_default_arg

    def add_default_env(self, *args, **kwargs):
        """Set an environment variable when the command is run.

        Parameters
        ----------
        args : tuple
            args[0] is the environment variable to set
            args[1] is the value to set it to
        kwargs : dict
            Dictionary of key: value environment variables
        """
        if args:
            key, value = args
            kwargs[key] = value
        for key, value in kwargs.items():
            if value is None:
                tty.die(f"The value of {key} must not be None")
            self.default_env[str(key)] = str(value)

    @property
    def command(self):
        """The command-line string.

        Returns:
            str: The executable and default arguments
        """
        return " ".join(self.exe)

    @property
    def name(self):
        """The executable name.

        Returns:
            str: The basename of the executable
        """
        return os.path.basename(self.path)

    @property
    def path(self):
        """The path to the executable.

        Returns:
            str: The path to the executable
        """
        return self.exe[0]

    def add_begin_callback(self, fun) -> None:
        self.begin_callback = fun

    def __call__(self, *args, **kwargs):
        """Run this executable in a subprocess.

        Parameters:
            *args (str): Command-line arguments to the executable to run

        Keyword Arguments:
            _dump_env (dict): Dict to be set to the environment actually
                used (envisaged for testing purposes only)
            env (dict): The environment to run the executable with
            extra_env (dict): Extra items to add to the environment
                (neither requires nor precludes env)
            fail_on_error (bool): Raise an exception if the subprocess returns
                an error. Default is True. The return code is available as
                ``exe.returncode``
            ignore_errors (int or list): A list of error codes to ignore.
                If these codes are returned, this process will not raise
                an exception even if ``fail_on_error`` is set to ``True``
            input: Where to read stdin from
            output: Where to send stdout
            error: Where to send stderr
            verbose: Write the command line to ``output``
            script: write a shell script with the environment and commands

        Accepted values for input, output, and error:

        * python streams, e.g. open Python file objects, or ``os.devnull``
        * filenames, which will be automatically opened for writing
        * ``str``, as in the Python string type. If you set these to ``str``,
          output and error will be written to pipes and returned as a string.
          If both ``output`` and ``error`` are set to ``str``, then one string
          is returned containing output concatenated with error. Not valid
          for ``input``

        By default, the subprocess inherits the parent's file descriptors.

        """
        # Environment
        env_arg = kwargs.get("env", None)
        if env_arg is None:
            env = os.environ.copy()
            env.update(self.default_env)
        else:
            env = self.default_env.copy()
            env.update(env_arg)
        env.update(kwargs.get("extra_env", {}))
        if "_dump_env" in kwargs:
            kwargs["_dump_env"].clear()
            kwargs["_dump_env"].update(env)

        fail_on_error = kwargs.pop("fail_on_error", True)
        ignore_errors = kwargs.pop("ignore_errors", ())
        verbose = kwargs.pop("verbose", False)

        # If they just want to ignore one error code, make it a tuple.
        if isinstance(ignore_errors, int):
            ignore_errors = (ignore_errors,)

        input = kwargs.pop("input", None)
        output = kwargs.pop("output", None)
        error = kwargs.pop("error", None)
        timeout = kwargs.pop("timeout", None)

        if input is str:
            raise ValueError("Cannot use `str` as input stream.")

        def streamify(arg, mode):
            if isinstance(arg, str):
                return open(arg, mode), True
            elif arg is str:
                return subprocess.PIPE, False
            else:
                return arg, False

        ostream, close_ostream = streamify(output, "w")
        estream, close_estream = streamify(error, "w")
        istream, close_istream = streamify(input, "r")

        args = [str(_) for _ in args]
        quoted_args = [arg for arg in args if re.search(r'^"|^\'|"$|\'$', arg)]
        if quoted_args:
            tty.warn(
                "Quotes in command arguments can confuse scripts like" " configure.",
                "The following arguments may cause problems when executed:",
                str("\n".join(["    " + arg for arg in quoted_args])),
                "Quotes aren't needed because a shell is not used.",
                "Consider removing them",
            )

        cmd = self.exe + list(args)

        cmd_line = join_command(cmd)
        self.cmd_line = cmd_line

        if verbose:
            tty.info(f"Command line: {cmd_line}")
        else:
            tty.debug(cmd_line)

        try:
            proc = subprocess.Popen(
                cmd, stdin=istream, stderr=estream, stdout=ostream, env=env
            )
            if self.begin_callback is not None:
                self.begin_callback(proc)
            out, err = proc.communicate(timeout=timeout)

            result = None
            if output is str or error is str:
                result = ""
                if output is str:
                    result += str(out.decode("utf-8"))
                if error is str:
                    result += str(err.decode("utf-8"))

            rc = self.returncode = proc.returncode
            if fail_on_error and rc != 0 and (rc not in ignore_errors):
                long_msg = cmd_line
                if result:
                    # If the output is not captured in the result, it will have
                    # been stored either in the specified files (e.g. if
                    # 'output' specifies a file) or written to the parent's
                    # stdout/stderr (e.g. if 'output' is not specified)
                    long_msg += "\n" + result

                raise ProcessError(
                    "Command exited with status %d: %s" % (proc.returncode, long_msg)
                )

            return result

        except OSError as e:
            msg = f"{self.exe[0]}: {e.strerror}"
            if fail_on_error:
                raise ProcessError(msg) from None
            tty.error(msg)
            self.returncode = proc.returncode

        except subprocess.TimeoutExpired as e:
            msg = f"{e}\nExecution timed out when invoking command: {cmd_line}"
            proc.kill()
            if fail_on_error:
                raise ProcessError(msg) from None
            self.returncode = timeout_exit_status

        except subprocess.CalledProcessError as e:
            rc = proc.returncode
            msg = f"{e}\nExit status {rc} when invoking command: {cmd_line}"
            if fail_on_error:
                raise ProcessError(msg) from None
            tty.error(msg)
            self.returncode = rc

        finally:
            if close_ostream:
                ostream.close()
            if close_estream:
                estream.close()
            if close_istream:
                istream.close()

    def __eq__(self, other):
        return self.exe == other.exe

    def __neq__(self, other):
        return not (self == other)

    def __hash__(self):
        return hash((type(self),) + tuple(self.exe))

    def __repr__(self):
        return "<exe: %s>" % self.exe

    def __str__(self):
        return " ".join(self.exe)


def join_command(args):
    """Join the command `args`.

    `args` should be a sequence of commands to run or else a single string

    """
    if isinstance(args, str):
        args = shlex.split(args)
    args = [str(_) for _ in args]
    quoted_args = [arg for arg in args if re.search(r'^"|^\'|"$|\'$', arg)]
    if quoted_args:
        tty.warn(
            "Quotes in command arguments can confuse scripts like configure.",
            "The following arguments may cause problems when executed:",
            "    " + "\n".join(["    " + arg for arg in quoted_args]),
            "Quotes aren't needed because a shell is not used.  Consider removing them",
        )
    cmd = list(args)
    return "'%s'" % "' '".join(map(lambda arg: arg.replace("'", "'\"'\"'"), cmd))


class ProcessError(Exception):
    """ProcessErrors are raised when Executables exit with an error code."""
