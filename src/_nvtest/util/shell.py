import difflib
import os
import re
import subprocess
import sys
from typing import Optional
from typing import TextIO

from . import tty
from .filesystem import ancestor

shells: list[str] = []


class shell:
    type: str
    rcfile: str

    def format_env_mods(self, env_mods, file: Optional[TextIO] = None) -> None:
        raise NotImplementedError

    @staticmethod
    def init():
        raise NotImplementedError

    @staticmethod
    def source_file(file: str) -> dict:
        raise NotImplementedError

    @classmethod
    def getsourcediff(cls, file):
        state = cls.source_file(file)
        mods = {"env": [], "function": [], "alias": []}
        for name in state.get("env", {}):
            old, new = state["env"][name]
            if old == new:
                continue
            elif new is None:
                mods["env"].append(("unset", name, old))
                continue
            elif old is None or "://" in old or ":" not in new:
                mods["env"].append(("set", name, new))
                continue
            diff = difflib.SequenceMatcher(None, old, new)
            match = max(diff.get_matching_blocks(), key=lambda x: x[2])
            i, j, k = match
            assert diff.a[i : i + k] == diff.b[j : j + k]
            if i < j:
                p = new[i:j].strip(":")
                mods["env"].append(("prepend-path", name, p))
            else:
                p = new[k:].strip(":")
                mods["env"].append(("append-path", name, p))
        for name in state.get("function", {}):
            old, new = state["function"][name]
            if old == new:
                continue
            elif new is None:
                mods["function"].append(("unset", name, new))
            else:
                mods["function"].append(("set", name, new))
        for name in state.get("alias", {}):
            old, new = state["alias"][name]
            if old == new:
                continue
            elif new is None:
                mods["alias"].append(("unset", name, None))
            else:
                mods["alias"].append(("set", name, new))
        return mods


class bash(shell):
    type = "bash"
    shells.extend(("bash", "sh"))
    rcfile = os.path.expanduser("~/.bash_profile")

    @staticmethod
    def init():
        prefix = ancestor(os.path.dirname(__file__), n=1)
        py_path = f'PYTHONPATH="{prefix}:${{PYTHONPATH}}"'
        with open(bash.rcfile, "a") as fh:
            fh.write("\n\n# >>> modulecmd initialize >>>\n")
            fh.write(
                "# !! Contents within this block are managed by 'module init' !!\n"
            )
            fh.write("# Define the modulecmd shell function\n")
            fh.write("module()\n")
            fh.write("{\n")
            fh.write(
                f'  eval $({py_path} {sys.executable} -B -m modulecmd shell.bash "$@")\n'  # noqa: E501
            )
            fh.write("}\n")
            fh.write("export -f module\n")
            fh.write(
                f"  eval $({py_path} {sys.executable} -B -m modulecmd shell.bash __init__)\n"  # noqa: E501
            )
            fh.write("# <<< modulecmd initialize <<<\n")

    def format_env_mods(self, env_mods, file: Optional[TextIO] = None) -> None:
        file = file or sys.stdout
        for var, value in env_mods.variables.items():
            if value is None:
                file.write(f"unset {var};\n")
            else:
                file.write(f'{var}="{value}"; export {var};\n')
        for name, body in env_mods.aliases.items():
            if body is None:
                file.write(f"unalias {name} 2> /dev/null || true;\n")
            else:
                file.write(f"alias {name}={body!r};\n")
        for name, body in env_mods.shell_functions.items():
            if body is None:
                file.write(f"unset -f {name} 2> /dev/null || true;\n")
            else:
                file.write(f"{name}() {{ {body.rstrip(';')}; }};\n")
        for command in env_mods.raw_shell_commands:
            file.write(f"{command};\n")

    @staticmethod
    def source_file(file: str) -> dict:
        """Source the shell script `file` and return the state before/after

        Parameters
        ----------
        file : str
            The file to source

        Returns
        -------
        state : dict
            Dictionary containing variables, functions, and aliases before and after
            `file` is sourced

        Notes
        -----
        - state['env'][NAME] = [BEFORE, AFTER]
        - state['function'][NAME] = [BEFORE, AFTER]
        - state['alias'][NAME] = [BEFORE, AFTER]

        """
        if not os.path.exists(file):
            raise FileNotFoundError(file)
        cmd = ["bash", "--noprofile", "-c"]
        args = [
            "echo 'env<<<'",
            "export -p",
            "echo '>>>'",
            "echo 'fun<<<'",
            "declare -f",
            "echo '>>>'",
            "echo 'alias<<<'",
            "alias",
            "echo '>>>'",
            "set -a",
            f". {file}",
            "echo 'env<<<'",
            "export -p",
            "echo '>>>'",
            "echo 'fun<<<'",
            "declare -f",
            "echo '>>>'",
            "echo 'alias<<<'",
            "alias",
            "echo '>>>'",
        ]
        cmd.append(" ; ".join(args))
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.wait()
        comm = p.communicate()
        out = comm[0].decode("utf-8")
        state: dict[str, dict] = {"env": {}, "function": {}, "alias": {}}
        skip_vars = ["PWD", "SHLVL"]
        var_groups = re.findall("env<<<(.*?)>>>", out, re.DOTALL)
        var_regex = "declare -x (\w+)=(.*)\n"
        assert len(var_groups) == 2
        for i, var_group in enumerate(var_groups):
            for name, value in re.findall(var_regex, var_group):
                if name.startswith("__MODULECMD_") or name in skip_vars:
                    continue
                state["env"].setdefault(name, [None, None])[i] = value[1:-1]
        fn_regex = "(\w+?) \(\)\s?\n{(.*?)\n}\n"
        fn_groups = re.findall("fun<<<(.*?)>>>", out, re.DOTALL)
        assert len(fn_groups) == 2
        for i, fn_group in enumerate(fn_groups):
            for name, defn in re.findall(fn_regex, fn_group, re.DOTALL):
                state["function"].setdefault(name, [None, None])[i] = defn
        alias_regex = "alias (\w+)=(.*)\n"
        alias_groups = re.findall("alias<<<(.*?)>>>", out, re.DOTALL)
        assert len(alias_groups) == 2
        for i, alias_group in enumerate(alias_groups):
            for name, value in re.findall(alias_regex, alias_group):
                state["alias"].setdefault(name, [None, None])[i] = value[1:-1]
        return state


class csh(shell):
    type = "csh"
    limit = 4000
    shells.extend(("csh", "tcsh"))
    rcfile = os.path.expanduser("~/.tcshrc")

    def format_env_mods(self, env_mods, file: Optional[TextIO] = None) -> None:
        file = file or sys.stdout
        for var, value in env_mods.variables.items():
            if value is None:
                file.write(f"unsetenv {var};\n")
            else:
                # csh barfs on long env vars
                if len(value) > self.limit:
                    if var == "PATH":
                        value = self.truncate_path(value)
                    else:
                        msg = f"{var} exceeds {self.limit} characters, truncating..."
                        tty.warn(msg)
                        value = value[: self.limit]
                file.write(f'setenv {var} "{value}";\n')
        aliases = dict(env_mods.aliases)
        aliases.update(env_mods.shell_functions)
        for name, body in aliases.items():
            if body is None:
                file.write(f"unalias {name} 2> /dev/null || true;\n")
            else:
                body = body.rstrip(";")
                # Convert $n -> \!:n
                body = re.sub(r"\$([0-9]+)", r"\!:\1", body)
                # Convert $* -> \!*
                body = re.sub(r"\$\*", r"\!*", body)
                file.write(f"alias {name} '{body}';\n")
        for command in env_mods.raw_shell_commands:
            file.write(f"{command};\n")

    def truncate_path(self, path):
        tty.warn(f"Truncating PATH because it exceeds {self.limit} characters")
        truncated = ["/usr/bin", "/bin"]
        length = len(truncated[0]) + len(truncated[1]) + 1
        for i, item in enumerate(path.split(os.pathsep)):
            if (len(item) + 1 + length) > self.limit:
                break
            else:
                length += len(item) + 1
                truncated.insert(-2, item)
        return os.pathsep.join(truncated)


class python(shell):
    type = "python"
    shells.append("python")

    @staticmethod
    def init():
        pass

    @staticmethod
    def format_env_mods(env_mods, file: Optional[TextIO] = None) -> None:
        file = file or sys.stdout
        for var, value in env_mods.variables.items():
            if value is None:
                file.write(f"del os.environ[{var!r}]\n")
            else:
                file.write(f"os.environ[{var!r}] = {value!r}\n")
        for name, body in env_mods.aliases.items():
            file.write(f"alias_{name} = {body!r}\n")
        for name, body in env_mods.shell_functions.items():
            file.write(f"shell_function_{name} = {body!r}\n")


def default_shell() -> str:
    shell = os.getenv("SHELL")
    if shell is None:
        raise ValueError("Unable to determine shell from environment")
    return os.path.basename(shell)


def factory(arg: Optional[str] = None) -> shell:
    arg = arg or default_shell()
    if arg in ("bash", "sh"):
        return bash()
    elif arg in ("csh", "tcsh"):
        return csh()
    elif arg in ("py", "python"):
        return python()
    raise NotImplementedError(f"{arg}: shell not implemented in modulecmd")
