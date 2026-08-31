# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from pathlib import Path
from typing import Any

from _canary.generator import AbstractSpecGenerator
from _canary.hookspec import hookimpl
from _canary.util.query_data import load_query_data

from . import directives
from .pyt import PYTAdapter
from .pyt import PYTLoader
from .pyt import PYTLockEmitter
from .pyt import PYTModel

__all__ = ["directives", "FILE_SCANNING"]


# Constant that's True when file scanning, but False here.
FILE_SCANNING = False


def set_file_scanning(value: bool):
    global FILE_SCANNING
    FILE_SCANNING = value


class PYTSpecGenerator(AbstractSpecGenerator):
    file_patterns = ("*.pyt", "canary_*.py")

    def __init__(self, root: str, path: str | None = None) -> None:
        super().__init__(root, path=path)
        self.model = PYTModel(root=self.root, path=self.path)  # whatever context needed
        self.adapter = PYTAdapter(self.model)
        calls = PYTLoader(file=self.file).parse()
        self.adapter.apply(calls)

    def lock(self, on_options=None):
        return PYTLockEmitter().lock(self.model, on_options=on_options)

    def describe(self, on_options: list[str] | None = None) -> str:
        import io
        import os

        from _canary.generate import resolve
        from _canary.jobspec_graph import print_spec_graph
        from _canary.util import logging
        from _canary.util.field import Field
        from _canary.util.string import pluralize

        logger = logging.get_logger(__name__)

        file = io.StringIO()
        file.write(f"--- {self.name} ------------\n")
        file.write(f"File: {self.file}\n")
        file.write(f"Keywords: {', '.join(self.model.get_keywords(on_options=on_options))}\n")
        options = self.model.option_expressions()
        if options:
            file.write(f"Recognized options: {', '.join(options)}\n")

        # Print raw (unsubstituted) source specs if present
        if hasattr(self.model, "sources") and isinstance(getattr(self.model, "sources"), Field):
            src_field = getattr(self.model, "sources")
            if src_field.items:
                file.write("Source files:\n")
                grouped: dict[str, list[tuple[str, str | None]]] = {}
                for c in src_field.items:
                    s = c.value
                    grouped.setdefault(s.action, []).append((s.src, s.dst))
                for action, files in grouped.items():
                    file.write(f"  {action.title()}:\n")
                    for src, dst in files:
                        file.write(f"    {src}")
                        if dst and dst != os.path.basename(src):
                            file.write(f" -> {dst}")
                        file.write("\n")

        try:
            specs = self.lock(on_options=on_options)
            resolved = resolve(specs)
            n = len(specs)
            opts = ", ".join(on_options or [])
            file.write(f"{n} test {pluralize('spec', n)} using on_options={opts}:\n")
            try:
                print_spec_graph(resolved, file=file)
            except Exception:  # nosec B110
                pass
        except Exception:
            logger.warning("Unable to generate dependency graph")
        return file.getvalue()

    def info(self) -> dict[str, Any]:
        info: dict[str, Any] = super().info()
        info["keywords"] = self.model.get_keywords()
        info["options"] = self.model.option_expressions()
        return info


def make_directives_docs(prefix: str) -> None:
    import types

    from _canary.util.rich import set_color_when

    set_color_when("never")
    dest = Path(prefix).resolve() / "directives"
    dest.mkdir(parents=True, exist_ok=True)
    all_directives = []
    for name in dir(directives):
        attr = getattr(directives, name)
        if isinstance(attr, types.FunctionType) and attr.__doc__ and attr not in all_directives:
            all_directives.append(attr)
    names = sorted([fun.__name__ for fun in all_directives])
    with open(dest / "index.rst", "w") as fh:
        fh.write(".. _test-directives:\n\n")
        fh.write("Test Directives\n===============\n\n")
        fh.write(".. automodule:: canary_pyt.directives\n\n")
        fh.write(".. toctree::\n   :maxdepth: 1\n\n")
        for name in names:
            fh.write(f"   {name}<{name}>\n")
    for name in names:
        with open(dest / f"{name}.rst", "w") as fh:
            fh.write(f".. _directive-{name.replace('_', '-')}:\n\n")
            fh.write(f"{name}\n{'=' * len(name)}\n\n")
            fh.write(f".. autofunction:: canary_pyt.directives.{name}\n")


@hookimpl
def canary_collectstart(collector) -> None:
    collector.add_generator(PYTSpecGenerator)


@hookimpl
def canary_capabilities() -> dict[str, Any] | None:
    return load_query_data("canary_pyt.data", "capabilities.json")


@hookimpl
def canary_skills() -> dict[str, Any] | None:
    return load_query_data("canary_pyt.data", "skills.json")
