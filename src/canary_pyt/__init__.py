# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Any

from _canary.generator import AbstractSpecGenerator
from _canary.hookspec import hookimpl

from .pyt import PYTAdapter
from .pyt import PYTLoader
from .pyt import PYTLockEmitter
from .pyt import PYTModel


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
        from _canary.util import graph
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
                graph.print(resolved, file=file)
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


@hookimpl
def canary_collectstart(collector) -> None:
    collector.add_generator(PYTSpecGenerator)
