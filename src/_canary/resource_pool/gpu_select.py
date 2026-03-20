# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Any

import canary

from ..config import Config
from ..config.argparsing import Parser
from ..hookspec import hookimpl
from ..hookspec import hookspec


class GPUSelect:
    @hookspec
    def canary_gpu_backend_detect(self, config: Config) -> str | None:
        raise NotImplementedError

    @hookspec
    def canary_gpu_list_gpus(self, config: Config) -> list[dict] | None:
        raise NotImplementedError


@hookimpl
def canary_addoption(parser: Parser) -> None:
    parser.add_argument(
        "--gpu-backend",
        group="resource control",
        default="auto",
        help="Use this GPU backend [default: auto]",
    )


@hookimpl
def canary_addhooks(pluginmanager: "canary.CanaryPluginManager") -> None:
    pluginmanager.add_hookspecs(GPUSelect)


@hookimpl(specname="canary_configure")
def detect_gpu_backend(config: "canary.Config") -> None:
    pm = config.pluginmanager
    requested = config.getoption("gpu_backend") or "auto"
    candidates: list[tuple[str, str]] = []
    for impl in pm.hook.canary_gpu_backend_detect.get_hookimpls():
        plugin = impl.plugin
        plugin_name = (
            getattr(impl, "plugin_name", None) or getattr(impl, "pluginname", None) or "<unknown>"
        )
        backend = getattr(plugin, "canary_gpu_backend_detect")(config=config)
        if backend:
            candidates.append((str(backend).lower(), str(plugin_name)))
    selected = _select_backend(requested, candidates)
    # Persist selection for later phases:
    if selected is None:
        config.set("scratch:gpu:selected_plugin", None)
    else:
        key, name = selected
        config.set("scratch:gpu:backend", key)
        config.set("scratch:gpu:selected_plugin", name)


@hookimpl(specname="canary_resource_pool_fill")
def canary_fill_gpu(config: Config, pool: dict[str, dict[str, Any]]) -> None:
    resources = pool.setdefault("resources", {})
    if resources.get("gpus"):
        return
    plugin_name = config.get("scratch:gpu:selected_plugin")
    if not plugin_name:
        return
    pm = config.pluginmanager
    plugin = pm.get_plugin(plugin_name)
    if plugin is None:
        raise RuntimeError(f"Selected GPU plugin '{plugin_name}' is not registered")
    gpu_specs = plugin.canary_gpu_list_gpus(config=config)
    if gpu_specs:
        gpus = [
            {"id": f"{spec['vendor'].upper()}:{spec['id']}:{spec['uuid']}", "slots": spec["slots"]}
            for spec in gpu_specs
        ]
        resources["gpus"] = gpus


def _select_backend(requested: str, candidates: list[tuple[str, str]]) -> tuple[str, str] | None:
    requested = (requested or "auto").lower()

    if requested == "none":
        return None

    if requested == "auto":
        if len(candidates) == 0:
            return None
        if len(candidates) == 1:
            return candidates[0]
        # ambiguous: force user to choose
        keys = sorted({k for (k, _) in candidates})
        names = sorted({n for (_, n) in candidates})
        raise ValueError(
            f"Multiple GPU backends detected: keys={keys}, plugins={names}. Use --gpu-backend=<key>."
        )

    # allow selecting by backend key OR by plugin registered name
    for key, plugin_name in candidates:
        if requested == key or requested == plugin_name.lower():
            return (key, plugin_name)

    keys = sorted({k for (k, _) in candidates})
    names = sorted({n for (_, n) in candidates})
    raise ValueError(
        f"Requested GPU backend '{requested}' not found. Detected keys={keys}, plugins={names}."
    )
