#!/usr/bin/env python3
import io
import os


def module_name(name) -> str:
    if not name.endswith(".py"):
        return None
    elif name in ("__init__.py", "_version.py", "__main__.py"):
        return None
    return os.path.splitext(name)[0]


def dump(text: str, file: str) -> None:
    os.makedirs(os.path.dirname(file), exist_ok=True)
    with open(file, "w") as fh:
        fh.write(text)


def make_api_docs(source_dir: str, dest_dir: str, skip_dirs: list[str] | None = None) -> None:

    skip_dirs = skip_dirs or []
    skip_dirs.append("__pycache__")

    source_dir = os.path.normpath(source_dir)
    pkgname = os.path.basename(source_dir)

    package_data: dict[str, dict[str, set[str]]] = {}
    for dirname, dirs, files in os.walk(os.path.abspath(source_dir)):
        if dirname.endswith(tuple(skip_dirs)):
            del dirs[:]
            continue
        if not [f for f in files if f.endswith(".py")]:
            continue
        p = os.path.normpath(os.path.relpath(dirname, source_dir)).split(os.path.sep)
        namespace = ".".join(p)
        data = package_data.setdefault(namespace, {})
        data["modules"] = [module_name(f) for f in files if module_name(f)]
        data["packages"] = [d for d in dirs if d not in ("__pycache__", "third_party", "validators")]

    for namespace, data in package_data.items():
        dest = os.path.join(dest_dir, namespace.replace(".", os.path.sep).lstrip(os.path.sep))
        title = pkgname if namespace == "." else namespace
        fp = io.StringIO()
        fp.write(f"{title}\n{'=' * len(title)}\n\n.. toctree::\n   :maxdepth: 1\n\n")
        items = data["modules"] + [f"{p}/index" for p in data["packages"]]
        for item in sorted(items):
            fp.write(f"   {item}\n")
        file = os.path.join(dest, "index.rst")
        dump(fp.getvalue(), file)
        for module in data["modules"]:
            file = os.path.join(dest, f"{module}.rst")
            title = module
            name = f"{pkgname}.{module}" if namespace == "." else f"{pkgname}.{namespace}.{module}"
            fp = io.StringIO()
            fp.write(f"""\
{module}
{'=' * len(module)}

.. automodule:: {name}
   :members:
   :undoc-members:
   :show-inheritance:
"""
            )
            dump(fp.getvalue(), file)


if __name__ == "__main__":
    start = os.path.dirname(__file__)
    while True:
        if os.path.exists(os.path.join(start, "pyproject.toml")):
            make_api_docs(
                os.path.join(start, "src/_canary"),
                os.path.join(start, "docs/source/api-docs/canary"),
                skip_dirs=["third_party", "cdash/validators"]
            )
            make_api_docs(
                os.path.join(start, "../hpc-connect/src/hpc_connect"),
                os.path.join(start, "docs/source/api-docs/hpc_connect"),
            )
            make_api_docs(
                os.path.join(start, "../hpc-connect/src/hpc_connect"),
                os.path.join(start, "docs/source/api-docs/hpc_connect/hpc_connect"),
            )
            make_api_docs(
                os.path.join(start, "../hpcc-slurm/src/hpcc_slurm"),
                os.path.join(start, "docs/source/api-docs/hpc_connect/hpcc_slurm"),
            )
            make_api_docs(
                os.path.join(start, "../hpcc-pbs/src/hpcc_pbs"),
                os.path.join(start, "docs/source/api-docs/hpc_connect/hpcc_pbs"),
            )
            break
        start = os.path.dirname(start)
        if start == os.path.sep:
            break
