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


def module_name(name) -> str | None:
    if not name.endswith(".py"):
        return None
    elif name in ("__init__.py", "_version.py", "__main__.py", "submit_api.py"):
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

            for package in sorted(set(self.packages)):
                index = os.path.join(self.dest, package, "index.rst")
                if os.path.exists(index):
                    fh.write(f"    {package}/index\n")

    @staticmethod
    def dump_text_to_file(text: str, file: str) -> None:
        os.makedirs(os.path.dirname(file), exist_ok=True)
        with open(file, "w") as fh:
            fh.write(text)

    def add_package(
        self,
        pkgname: str,
        source_dir: str,
        skip_dirs: list[str] | None = None,
        skip_modules: list[str] | None = None,
        exclude_members: dict[str, list[str]] | None = None,
        no_index: bool = False,
        no_index_modules: list[str] | None = None,
    ) -> None:
        skip_dirs_set = set(skip_dirs or [])
        skip_dirs_set.update({"__pycache__", ".mypy_cache"})
        skip_modules_set = set(skip_modules or [])
        exclude_members = exclude_members or {}
        no_index_modules_set = set(no_index_modules or [])

        source_dir = os.path.abspath(os.path.normpath(source_dir))

        # First collect only namespaces that actually contain documentable
        # Python modules. Directories containing no Python modules should not
        # appear in generated toctrees.
        modules_by_namespace: dict[str, list[str]] = {}

        for dirname, dirs, files in os.walk(source_dir):
            # Prune hidden and explicitly skipped directories before os.walk
            # descends into them.
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip_dirs_set]

            rel = os.path.normpath(os.path.relpath(dirname, source_dir))
            namespace = "." if rel == "." else rel.replace(os.path.sep, ".")

            modules = sorted(
                module
                for f in files
                if (module := module_name(f)) is not None and module not in skip_modules_set
            )

            if modules:
                modules_by_namespace[namespace] = modules

        # If this package contains no documentable modules anywhere, do not
        # list it in the top-level API index.
        if not modules_by_namespace:
            return

        self.packages.append(pkgname)

        # Generate index pages for namespaces with modules and for all of their
        # ancestors. This handles layouts where the package root has only
        # __init__.py but subpackages contain documentable modules.
        needed_namespaces: set[str] = set(modules_by_namespace)

        for namespace in list(modules_by_namespace):
            if namespace == ".":
                continue

            needed_namespaces.add(".")

            parts = namespace.split(".")
            for i in range(1, len(parts)):
                needed_namespaces.add(".".join(parts[:i]))

        package_data: dict[str, dict[str, list[str]]] = {}

        for namespace in needed_namespaces:
            package_data[namespace] = {
                "modules": modules_by_namespace.get(namespace, []),
                "packages": [],
            }

        # Populate direct child packages, but only with namespaces that will
        # actually get an index.rst.
        for namespace in needed_namespaces:
            children: list[str] = []

            for other in needed_namespaces:
                if other == namespace:
                    continue

                if namespace == ".":
                    if "." not in other:
                        children.append(other)
                else:
                    prefix = f"{namespace}."
                    if other.startswith(prefix):
                        remainder = other[len(prefix) :]
                        if "." not in remainder:
                            children.append(remainder)

            package_data[namespace]["packages"] = sorted(children)

        for namespace in sorted(needed_namespaces):
            data = package_data[namespace]

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

                module_no_index = no_index or name in no_index_modules_set

                automodule_options = ["   :members:", "   :undoc-members:", "   :show-inheritance:"]

                excluded = exclude_members.get(name, [])
                if excluded:
                    automodule_options.append(f"   :exclude-members: {', '.join(excluded)}")

                if module_no_index:
                    automodule_options.append("   :no-index:")

                automodule_options_text = "\n".join(automodule_options)

                fp = io.StringIO()
                fp.write(f"""\
{copyright}

.. _{name.lstrip("_")}:

{title}
{"=" * len(title)}

.. automodule:: {name}
{automodule_options_text}
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
        exclude_members={
            "_canary.select": ["rules"],
            "_canary.expression": ["type"],
            "_canary.reporters.html": ["type"],
            "_canary.reporters.json": ["type"],
            "_canary.reporters.junit": ["type"],
            "_canary.reporters.markdown": ["type"],
            "_canary.reporters.reporter": ["type"],
        },
        no_index_modules=["_canary.resource_pool.rpool", "_canary.plugins.subcommands.status"],
    )

    maker.add_package(
        "canary",
        os.path.join(canary_root, "src/canary"),
        skip_dirs=["examples"],
        skip_modules=["directives"],
    )

    maker.add_package(
        "canary_cmake",
        os.path.join(canary_root, "src/canary_cmake"),
        skip_dirs=["validators", "tests"],
    )

    maker.add_package(
        "canary_amd", os.path.join(canary_root, "src/canary_amd"), skip_dirs=["tests"]
    )

    maker.add_package(
        "canary_dist",
        os.path.join(canary_root, "src/canary_dist"),
        skip_dirs=["tests"],
        no_index_modules=["canary_hpc.batchspec"],
    )

    maker.add_package(
        "canary_nvidia", os.path.join(canary_root, "src/canary_nvidia"), skip_dirs=["tests"]
    )

    maker.add_package(
        "canary_hpc",
        os.path.join(canary_root, "src/canary_hpc"),
        skip_dirs=["tests"],
        exclude_members={"canary_hpc.binpack": ["used", "down", "right"]},
        no_index_modules=["canary_hpc.batchspec"],
    )

    maker.add_package(
        "canary_gitlab",
        os.path.join(canary_root, "src/canary_gitlab"),
        skip_dirs=["tests"],
        exclude_members={"canary_gitlab.reporter": ["type"]},
    )

    maker.add_package(
        "canary_vvtest",
        os.path.join(canary_root, "src/canary_vvtest"),
        skip_dirs=["tests"],
        exclude_members={"canary_vvtest.vvt": ["type"]},
    )

    hpc_connect = str(importlib.resources.files("hpc_connect"))
    hpcc_root = os.path.join(hpc_connect, "../..")

    if os.path.exists(os.path.join(hpcc_root, "pyproject.toml")):
        print("Making hpc_connect api docs")

        maker.add_package(
            "hpc_connect",
            os.path.join(hpcc_root, "src/hpc_connect"),
            skip_dirs=["tests", "templates"],
            no_index=True,
        )

        maker.add_package(
            "hpcc_pbs",
            os.path.join(hpcc_root, "src/hpcc_pbs"),
            skip_dirs=["tests", "templates"],
            no_index=True,
        )

        maker.add_package(
            "hpcc_slurm",
            os.path.join(hpcc_root, "src/hpcc_slurm"),
            skip_dirs=["tests", "templates"],
            no_index=True,
        )

        maker.add_package(
            "hpcc_flux",
            os.path.join(hpcc_root, "src/hpcc_flux"),
            skip_dirs=["tests", "templates"],
            no_index=True,
        )

        maker.add_package(
            "hpcc_remote",
            os.path.join(hpcc_root, "src/hpcc_remote"),
            skip_dirs=["tests", "templates"],
            no_index=True,
        )
    else:
        print("Could not find hpc_connect root")

    maker.finish()
