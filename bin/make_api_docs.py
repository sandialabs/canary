#!/usr/bin/env python3
# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import importlib.resources
import io
import os
import shutil

copyright = """\
.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

"""


def module_name(name) -> str:
    if not name.endswith(".py"):
        return None
    elif name in ("__init__.py", "_version.py", "__main__.py", "flux_api.py"):
        return None
    return os.path.splitext(name)[0]


class APIDocsMaker:
    def __init__(self, dest: str, wipe: bool = False) -> None:
        self.packages: list[str] = []
        self.dest = os.path.abspath(dest)
        if wipe and os.path.exists(self.dest):
            shutil.rmtree(self.dest)

    def init(self) -> None:
        os.makedirs(self.dest, exist_ok=True)

    def finish(self) -> None:
        f = os.path.join(self.dest, "index.rst")
        with open(f, "w") as fh:
            fh.write(copyright)
            fh.write("\n")
            fh.write("API reference\n=============\n\n.. toctree::\n    :maxdepth: 1\n\n")
            for package in sorted(self.packages):
                fh.write(f"    {package}/index\n")

    @staticmethod
    def dump_text_to_file(text: str, file: str) -> None:
        os.makedirs(os.path.dirname(file), exist_ok=True)
        with open(file, "w") as fh:
            fh.write(text)

    def add_package(
        self, pkgname: str, source_dir: str, skip_dirs: list[str] | None = None
    ) -> None:
        skip_dirs = skip_dirs or []
        skip_dirs.append("__pycache__")
        skip_dirs.append(".mypy_cache")

        source_dir = os.path.normpath(source_dir)
        self.packages.append(pkgname)

        package_data: dict[str, dict[str, set[str]]] = {}
        for dirname, dirs, files in os.walk(os.path.abspath(source_dir)):
            if os.path.basename(dirname).startswith("."):
                del dirs[:]
                continue
            if dirname.endswith(tuple(skip_dirs)):
                del dirs[:]
                continue
            if not [f for f in files if f.endswith(".py")]:
                continue
            p = os.path.normpath(os.path.relpath(dirname, source_dir)).split(os.path.sep)
            namespace = ".".join(p)
            data = package_data.setdefault(namespace, {})
            data["modules"] = [module_name(f) for f in files if module_name(f)]
            data["packages"] = [d for d in dirs if not d.endswith(tuple(skip_dirs))]
        for namespace, data in package_data.items():
            dest = os.path.join(
                self.dest, pkgname, namespace.replace(".", os.path.sep).lstrip(os.path.sep)
            )
            title = pkgname if namespace == "." else namespace
            fp = io.StringIO()
            fp.write(copyright)
            fp.write(f"{title}\n{'=' * len(title)}\n\n.. toctree::\n   :maxdepth: 1\n\n")
            items = data["modules"] + [f"{p}/index" for p in data["packages"]]
            for item in sorted(items):
                fp.write(f"   {item}\n")
            file = os.path.join(dest, "index.rst")
            self.dump_text_to_file(fp.getvalue(), file)
            for module in data["modules"]:
                file = os.path.join(dest, f"{module}.rst")
                title = module
                name = (
                    f"{pkgname}.{module}" if namespace == "." else f"{pkgname}.{namespace}.{module}"
                )
                fp = io.StringIO()
                fp.write(f"""\
{copyright}
{module}
{"=" * len(module)}

.. automodule:: {name}
   :members:
   :undoc-members:
   :show-inheritance:
""")
                self.dump_text_to_file(fp.getvalue(), file)


if __name__ == "__main__":
    canary = str(importlib.resources.files("canary"))
    canary_root = os.path.join(canary, "../..")
    if not os.path.exists(os.path.join(canary_root, "pyproject.toml")):
        raise ValueError("make_api_docs.py must be run with canary source checkout")
    maker = APIDocsMaker(os.path.join(canary_root, "docs/source/api-docs"), wipe=True)
    maker.init()
    print("Making canary api docs")
    maker.add_package(
        "_canary",
        os.path.join(canary_root, "src/_canary"),
        skip_dirs=["third_party"],
    )
    maker.add_package(
        "canary_cmake",
        os.path.join(canary_root, "src/canary_cmake"),
        skip_dirs=["validators", "tests"],
    )
    maker.add_package(
        "canary_hpc",
        os.path.join(canary_root, "src/canary_hpc"),
        skip_dirs=["tests"],
    )
    maker.add_package(
        "canary_gitlab",
        os.path.join(canary_root, "src/canary_gitlab"),
        skip_dirs=["tests"],
    )
    maker.add_package(
        "canary_vvtest",
        os.path.join(canary_root, "src/canary_vvtest"),
        skip_dirs=["tests"],
    )

    hpc_connect = str(importlib.resources.files("hpc_connect"))
    hpcc_root = os.path.join(hpc_connect, "../..")
    if os.path.exists(os.path.join(hpcc_root, "pyproject.toml")):
        print("Making hpc_connect api docs")
        maker.add_package(
            "hpc_connect",
            os.path.join(hpcc_root, "src/hpc_connect"),
            skip_dirs=["tests", "templates"],
        )
        maker.add_package(
            "hpcc_pbs",
            os.path.join(hpcc_root, "src/hpcc_pbs"),
            skip_dirs=["tests", "templates"],
        )
        maker.add_package(
            "hpcc_slurm",
            os.path.join(hpcc_root, "src/hpcc_slurm"),
            skip_dirs=["tests", "templates"],
        )
        maker.add_package(
            "hpcc_flux",
            os.path.join(hpcc_root, "src/hpcc_flux"),
            skip_dirs=["tests", "templates"],
        )
        maker.add_package(
            "hpcc_subprocess",
            os.path.join(hpcc_root, "src/hpcc_subprocess"),
            skip_dirs=["tests", "templates"],
        )
    else:
        print("Could not find hpc_connect root")
    maker.finish()
