# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import TYPE_CHECKING
from typing import Any

from schema import Optional
from schema import Or
from schema import Schema

import canary

from ..config.argparsing import Parser
from ..hookspec import hookimpl
from ..hookspec import hookspec

if TYPE_CHECKING:
    from ..resource_pool.rpool import ResourcePool


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

    # Persist selection for later phases.
    config.set("gpu_select:.runtime:backend", selected)


@hookimpl(specname="canary_resource_pool_update")
def canary_fill_gpu(config: "canary.Config", pool: "ResourcePool") -> None:
    """Fill local-node GPU resources from the selected GPU backend.

    GPU backend discovery is local-node discovery, so this hook populates the
    first node's resources. Multi-node/HPC plugins can replace or populate nodes
    separately.
    """
    node = pool.first_node()

    if node.has_resource("gpus") and node.get_resource("gpus"):
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
        node.set_resource("gpus", [_gpu_resource_spec(spec) for spec in gpu_specs])


def _gpu_resource_spec(spec: dict[str, Any]) -> dict[str, Any]:
    vendor = str(spec.get("vendor", "UNKNOWN")).upper()

    properties: dict[str, Any] = {"vendor": vendor}

    if "uuid" in spec:
        properties["uuid"] = spec["uuid"]

    if "name" in spec:
        properties["name"] = spec["name"]

    if "model" in spec:
        properties["model"] = spec["model"]

    return {
        # Node-local runtime device ID. This is what CUDA_VISIBLE_DEVICES,
        # HIP_VISIBLE_DEVICES, etc. should use.
        "id": str(spec["id"]),
        "slots": spec.get("slots", 1),
        "properties": properties,
    }


def _select_backend(config: "canary.Config", candidates: dict[str, str]) -> dict[str, str] | None:
    requested = (config.getoption("gpu_backend") or "none").lower()

    if requested == "none":
        return None

    if requested == "auto":
        if len(candidates) == 0:
            return None
        if len(candidates) == 1:
            backend_name, plugin_name = next(iter(candidates.items()))
            return {"name": backend_name, "plugin": plugin_name}

        keys = sorted(candidates.keys())
        raise ValueError(
            f"Multiple GPU backends detected: {', '.join(keys)}. "
            "Choose one with --gpu-backend=BACKEND."
        )

    # Allow selecting by backend key OR by plugin registered name.
    for backend_name, plugin_name in candidates.items():
        if requested in {backend_name, plugin_name.lower()}:
            return {"name": backend_name, "plugin": plugin_name}

    keys = sorted(candidates.keys())
    raise ValueError(f"GPU backend '{requested}' not detected. Choose from {', '.join(keys)}.")


def get_plugin_name(plugin: Any) -> str:
    if name := getattr(plugin, "plugin_name", None):
        return name
    if name := getattr(plugin, "pluginname", None):
        return name
    return plugin.__class__.__name__


gpu_select_schema = Schema(
    {
        Optional("backend", default={"default": None}): {
            Optional("default", default=None): Or(str, None)  # type: ignore[arg-type]
        },
        Optional(".runtime"): {Optional("backend", default=None): object},
    },
    ignore_extra_keys=True,
)
