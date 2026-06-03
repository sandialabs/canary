# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Any

from schema import Optional
from schema import Or
from schema import Schema

import canary

from ..config.argparsing import Parser
from ..hookspec import hookimpl
from ..hookspec import hookspec


class GPUSelect:
    @hookspec
    def canary_gpu_backend_detect(self, config: "canary.Config") -> str | None:
        raise NotImplementedError

    @hookspec
    def canary_gpu_list_gpus(self, config: "canary.Config") -> list[dict] | None:
        raise NotImplementedError


@hookimpl
def canary_addoption(parser: Parser) -> None:
    parser.add_argument(
        "--gpu-backend",
        group="resource control",
        default="none",
        help="Use this GPU backend [default: none]",
    )


@hookimpl
def canary_addhooks(pluginmanager: "canary.CanaryPluginManager") -> None:
    pluginmanager.add_hookspecs(GPUSelect)


@hookimpl
def canary_addconfig(config: "canary.Config") -> None:
    config.add_section(name="gpu_select", schema=gpu_select_schema)


@hookimpl(specname="canary_configure")
def detect_gpu_backend(config: "canary.Config") -> None:
    pm = config.pluginmanager
    requested = config.getoption("gpu_backend") or "none"
    if requested == "none":
        return
    candidates: dict[str, str] = {}
    for impl in pm.hook.canary_gpu_backend_detect.get_hookimpls():
        plugin = impl.plugin
        plugin_name = get_plugin_name(impl)
        fun = getattr(plugin, "canary_gpu_backend_detect")
        backend = fun(config=config)
        if backend:
            key = str(backend).lower()
            if key in candidates:
                raise ValueError(f"Duplicate GPU backends detected for {key!r}")
            candidates[key] = plugin_name
    selected = _select_backend(config, candidates)
    # Persist selection for later phases:
    config.set("gpu_select:.runtime:backend", selected)


@hookimpl(specname="canary_resource_pool_fill")
def canary_fill_gpu(config: "canary.Config", pool: dict[str, dict[str, Any]]) -> None:
    resources = pool.setdefault("resources", {})
    if resources.get("gpus"):
        return
    backend = config.get("gpu_select:.runtime:backend")
    if backend is None:
        return
    pm = config.pluginmanager
    plugin = pm.get_plugin(backend["plugin"])
    if plugin is None:
        raise RuntimeError(f"Selected GPU plugin {backend['plugin']!r} is not registered")
    gpu_specs = plugin.canary_gpu_list_gpus(config=config)
    if gpu_specs:
        gpus = [
            {"id": f"{spec['vendor'].upper()}:{spec['id']}:{spec['uuid']}", "slots": spec["slots"]}
            for spec in gpu_specs
        ]
        resources["gpus"] = gpus


def _select_backend(config: "canary.Config", candidates: dict[str, str]) -> dict[str, str] | None:
    requested = (config.getoption("gpu_backend") or "none").lower()
    if requested == "none":
        return None
    if requested == "auto":
        if len(candidates) == 0:
            return None
        if len(candidates) == 1:
            return candidates
        keys = sorted(candidates.keys())
        raise ValueError(
            f"Multiple GPU backends detected: {', '.join(keys)}. Choose one with --gpu-backend=BACKEND."
        )
    # allow selecting by backend key OR by plugin registered name
    for backend_name, plugin_name in candidates.items():
        if requested.lower() in {backend_name, plugin_name.lower()}:
            return {"name": backend_name, "plugin": plugin_name}
    keys = sorted(candidates.keys())
    raise ValueError(f"GPU backend '{requested}' not detected. Choose from {', '.join(keys)}.")


def get_plugin_name(plugin: Any) -> str:
    if name := getattr(plugin, "plugin_name", None):
        return name
    elif name := getattr(plugin, "pluginname", None):
        return name
    return plugin.__class__.__name__


# default_backend = os.getenv("CANARY_GPU_BACKEND")
gpu_select_schema = Schema(
    {
        Optional("backend", default={"default": None}): {
            Optional("default", default=None): Or(str, None),  # type: ignore
        },
        Optional(".runtime"): {"backend": {"name": str, "plugin": str}},
    },
    ignore_extra_keys=True,
)
