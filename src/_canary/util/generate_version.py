import os
import subprocess
from typing import TextIO


def version_components_from_git(full: bool = False) -> tuple[int, int, int, str]:
    try:
        save_cwd = os.getcwd()
        os.chdir(os.path.join(os.path.dirname(__file__), "../../.."))
        args = ["git", "log", "-1", "--pretty=format:%ad %h", "--date=short"]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()
        out, _ = [_.decode("utf-8") for _ in proc.communicate()]
        date, local, *_ = out.split()
        major, minor, micro = [int(_) for _ in date.split("-")]
        if full:
            proc = subprocess.Popen(["git", "diff", "--quiet"])
            proc.wait()
            if proc.returncode:
                local += "-dirty"
        return major - 2000, minor, micro, local
    finally:
        os.chdir(save_cwd)


def write_version_file(file: TextIO, major: int, minor: int, micro: int, local: str) -> None:
    file.write("# Version file automatically generated\n")
    file.write(f'__version__ = version = "{major}.{minor}.{micro}+{local}"\n')
    file.write(f'__version_tuple__ = version_tuple = ({major}, {minor}, {micro}, "{local}")\n')


def __getattr__(name):
    if name == "__generate_dynamic_version__":
        major, minor, micro, local = version_components_from_git()
        return f"{major}.{minor}.{micro}+{local}"
    raise AttributeError(name)
