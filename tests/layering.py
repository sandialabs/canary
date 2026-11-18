# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

"""Guard rail for the package layering of ``_canary``.

Higher layers may import lower ones, never the reverse::

    cli, tui, api, reporters  ->  app  ->  controller  ->  execution, view, workspace
                                                        ->  persistence  ->  core, util

``execution``, ``view`` and ``workspace`` are siblings that must not import each
other.  ``config`` may import only ``workspace.locator`` (plus ``util`` and the free
packages).  ``events`` may import only ``core`` and ``util``.  Free packages
(``events``, ``config``, ``plugins``, ``error``, ``version``, ``third_party``) may be
imported from anywhere.

``KNOWN_VIOLATIONS`` records the violations that exist today, keyed by
``(importer_module, imported_module)`` with the import kind (``module``, ``function``
or ``type``, for ``TYPE_CHECKING`` blocks) as value.  The test fails on a new
violation and on an entry that no longer occurs, so the set can only shrink.

Run ``python tests/layering.py`` to print the current violations in that format.
"""

import ast
import pathlib

ROOT = pathlib.Path(__file__).parent.parent / "src" / "_canary"

# Rank of each top-level package.  A module may import a package of lower rank, or of
# equal rank unless the rank is in ISOLATED.  Packages the plan does not name are
# placed by role: agent/main are edges; generation, select, scanpaths, rerun, testinst,
# history and resource_pool are domain services between core and the data layers.
RANK = {
    "cli": 6,
    "tui": 6,
    "api": 6,
    "reporters": 6,
    "agent": 6,
    "main": 6,
    "<root>": 6,
    "app": 5,
    "controller": 4,
    "execution": 3,
    "view": 3,
    "workspace": 3,
    "persistence": 2,
    "generation": 2,
    "select": 2,
    "scanpaths": 2,
    "rerun": 2,
    "testinst": 2,
    "history": 2,
    "resource_pool": 2,
    "core": 1,
    "util": 1,
}
ISOLATED = {3}
# Importable from anywhere; their own imports are limited by OUTGOING (if listed).
FREE = {"events", "config", "plugins", "error", "version", "third_party"}
# Allowed targets for restricted packages: a package name or an exact module.
OUTGOING = {
    "config": {"util", "_canary.workspace.locator"} | FREE,
    "events": {"core", "util"} | FREE,
}
KIND_ORDER = {"module": 0, "function": 1, "type": 2}


def _module_name(path: pathlib.Path) -> str:
    parts = list(path.relative_to(ROOT.parent).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package(module: str) -> str:
    parts = module.split(".")
    return parts[1] if len(parts) > 1 else "<root>"


def _is_module(name: str) -> bool:
    path = ROOT.parent.joinpath(*name.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _imports(path: pathlib.Path):
    """Yield ``(imported_module, kind)`` for every ``_canary`` import in ``path``."""
    module = _module_name(path)
    package = module.split(".") if path.name == "__init__.py" else module.split(".")[:-1]

    def targets(node):
        if isinstance(node, ast.Import):
            return [alias.name for alias in node.names]
        if node.level == 0:
            source = node.module
        else:
            base = package[: len(package) - (node.level - 1)]
            source = ".".join(base + ([node.module] if node.module else []))
        # ``from pkg import name`` imports the submodule ``pkg.name`` when one exists.
        return [
            f"{source}.{alias.name}" if _is_module(f"{source}.{alias.name}") else source
            for alias in node.names
        ]

    def visit(node, kind):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                for target in targets(child):
                    if target and target.split(".")[0] == "_canary":
                        yield target, kind
            elif isinstance(child, ast.If) and _is_type_checking(child.test):
                for stmt in child.body:
                    yield from visit(ast.Module(body=[stmt], type_ignores=[]), "type")
                for stmt in child.orelse:
                    yield from visit(ast.Module(body=[stmt], type_ignores=[]), kind)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                yield from visit(child, "type" if kind == "type" else "function")
            else:
                yield from visit(child, kind)

    yield from visit(ast.parse(path.read_text(), str(path)), "module")


def _allowed(importer: str, imported: str) -> bool:
    src, dst = _package(importer), _package(imported)
    if src == dst:
        return True
    if src in OUTGOING:
        allowed = OUTGOING[src]
        return dst in allowed or any(
            imported == m or imported.startswith(m + ".") for m in allowed if "." in m
        )
    if dst in FREE or src in FREE:
        return True
    if src not in RANK or dst not in RANK:
        raise ValueError(f"unranked package in {importer} -> {imported}; add it to RANK")
    if RANK[dst] < RANK[src]:
        return True
    return RANK[dst] == RANK[src] and RANK[src] not in ISOLATED


def find_violations() -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    for path in sorted(ROOT.rglob("*.py")):
        if "third_party" in path.parts:
            continue
        importer = _module_name(path)
        for imported, kind in _imports(path):
            if _allowed(importer, imported):
                continue
            key = (importer, imported)
            if key not in found or KIND_ORDER[kind] < KIND_ORDER[found[key]]:
                found[key] = kind
    return found


KNOWN_VIOLATIONS: dict[tuple[str, str], str] = {
    ("_canary.config.argparsing", "_canary.cli"): "function",
    ("_canary.config.argparsing", "_canary.cli.base"): "type",
    ("_canary.config.config", "_canary.resource_pool.manager"): "module",
    ("_canary.core.job", "_canary.execution.launcher"): "type",
    ("_canary.core.job", "_canary.resource_pool.rpool"): "function",
    ("_canary.core.rules", "_canary.rerun"): "function",
    ("_canary.core.rules", "_canary.resource_pool.rpool"): "type",
    ("_canary.execution.runtest", "_canary.workspace.workspace"): "type",
    ("_canary.util.testing", "_canary.generation.collect"): "function",
    ("_canary.util.testing", "_canary.generation.generate"): "function",
    ("_canary.view", "_canary.workspace.session"): "type",
    ("_canary.view", "_canary.workspace.workspace"): "type",
    ("_canary.workspace.runner", "_canary.execution.queue_executor"): "type",
    ("_canary.workspace.runner", "_canary.view"): "module",
    ("_canary.workspace.session", "_canary.execution.runtest"): "module",
    ("_canary.workspace.workspace", "_canary.execution.queue_executor"): "type",
    ("_canary.workspace.workspace", "_canary.view"): "module",
}


def test_no_new_layering_violations():
    found = find_violations()
    new = {k: v for k, v in found.items() if KNOWN_VIOLATIONS.get(k) != v}
    assert not new, "new or changed layering violations:\n" + "\n".join(
        f"    {k!r}: {v!r}," for k, v in sorted(new.items())
    )


def test_known_violations_still_occur():
    found = find_violations()
    gone = {k: v for k, v in KNOWN_VIOLATIONS.items() if found.get(k) != v}
    assert not gone, "remove fixed entries from KNOWN_VIOLATIONS:\n" + "\n".join(
        f"    {k!r}: {v!r}," for k, v in sorted(gone.items())
    )


def test_locator_imports_only_util():
    """``config`` imports ``workspace.locator``, so the locator must stay a leaf."""
    imported = {target for target, _ in _imports(ROOT / "workspace" / "locator.py")}
    assert all(_package(target) == "util" for target in imported), imported


def test_checker_sees_type_checking_and_function_imports():
    kinds = {kind for _, kind in _imports(ROOT / "core" / "job.py")}
    assert kinds == {"module", "function", "type"}


if __name__ == "__main__":
    for key, kind in sorted(find_violations().items()):
        importer, imported = key
        print(f'    ("{importer}", "{imported}"): "{kind}",')
