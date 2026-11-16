# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import json
import re
import shutil
import subprocess
from typing import Any
from typing import Iterable
from typing import TypeVar

import canary

T = TypeVar("T")


_AMD_VISIBLE_DEVICES_VARIABLES = (
    "HIP_VISIBLE_DEVICES",
    "ROCR_VISIBLE_DEVICES",
    "CUDA_VISIBLE_DEVICES",
)

_AMD_COMPATIBLE_VENDORS = {"AMD", "ROCM"}


@canary.hookimpl
def canary_resource_pool_update(config: "canary.Config", pool: "canary.ResourcePool") -> None:
    """Fill local-node GPU resources from the selected GPU backend.

    GPU backend discovery is local-node discovery, so this hook populates the
    first node's resources. Multi-node/HPC plugins can replace or populate nodes
    separately.
    """
    node = pool.first_node()
    if node.has_resource("gpus") and node.get_resource("gpus"):
        return
    gpu_specs = _amd_smi_list_gpus(config)
    if gpu_specs:
        node.set_resource("gpus", gpu_specs)


@canary.hookimpl
def canary_configure(config: canary.Config) -> str | None:
    if shutil.which("amd-smi") is None and shutil.which("rocm-smi") is None:
        raise ValueError("canary_amd plugin requires amd-smi or rocm-smi on PATH")


@canary.hookimpl
def canary_gpu_list_gpus(config: canary.Config) -> list[dict] | None:
    if gpu_specs := _amd_smi_list_gpus(config):
        return gpu_specs
    elif gpu_specs := _rocm_smi_list_gpus(config):
        return gpu_specs
    return None


@canary.hookimpl
def canary_runteststart(case: "canary.Job") -> None:
    if any(var in case.variables for var in _AMD_VISIBLE_DEVICES_VARIABLES):
        # User already set a visible-devices variable: don't override.
        return

    gpus = _amd_gpus(case)
    if not gpus:
        return

    # In the topology-aware resource model, GPU resource IDs are node-local
    # runtime device IDs.
    local_ids = [str(gpu["id"]) for gpu in gpus]

    # Preserve order while removing duplicates. This matters for multi-node
    # allocations where multiple nodes may contribute local GPU id "0".
    visible = ",".join(dict.fromkeys(local_ids))

    if visible:
        case.variables["HIP_VISIBLE_DEVICES"] = visible
        case.variables["ROCR_VISIBLE_DEVICES"] = visible
        case.variables["CUDA_VISIBLE_DEVICES"] = visible


def _amd_gpus(case: "canary.Job") -> list[dict[str, Any]]:
    resources = getattr(case, "resources", None)
    if not isinstance(resources, dict):
        return []

    gpus = resources.get("gpus", [])
    if not isinstance(gpus, list):
        return []

    amd_gpus: list[dict[str, Any]] = []

    for gpu in gpus:
        if not isinstance(gpu, dict):
            return []

        if "id" not in gpu:
            return []

        properties = gpu.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}

        vendor = str(properties.get("vendor", "")).upper()

        # Unlike the NVIDIA/CUDA hook, do not claim UNKNOWN devices here.
        # UNKNOWN resources are allowed to fall through to CUDA handling.
        if vendor not in _AMD_COMPATIBLE_VENDORS:
            return []

        amd_gpus.append(gpu)

    return amd_gpus


def _amd_smi_list_gpus(config: canary.Config) -> list[dict] | None:
    if amd_smi := shutil.which("amd-smi"):
        args = [amd_smi, "list", "--json"]
        try:
            txt = subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True)
            data = json.loads(txt)
            gpu_specs: list[dict] = []
            for entry in data:
                id = entry["gpu"]
                uuid = entry["uuid"]
                if not uuid.startswith("GPU-"):
                    uuid = f"GPU-{uuid}"
                properties = {"vendor": "amd", "uuid": uuid}
                gpu_specs.append({"id": id, "slots": 1, "properties": properties})
            return gpu_specs
        except Exception:
            logger = canary.get_logger(__name__)
            logger.debug(f"Failed to determine GPU counts from '{' '.join(args)}'")
    return None


def _rocm_smi_list_gpus(config: canary.Config) -> list[dict] | None:
    if rocm_smi := shutil.which("rocm-smi"):
        # rocm-smi output is not as structured; this is a best-effort fallback.
        # It usually contains lines with GPU indices like "GPU[0]" etc.
        rx = re.compile(r"\bGPU\[(\d+)\]\b")
        args = [rocm_smi]
        try:
            txt = subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True)
            idxs: list[str] = []
            for line in txt.splitlines():
                if m := rx.search(line):
                    idxs.append(m.group(1))
            # de-dup while preserving order
            idxs = dedup(idxs)
            # rocm-smi typically doesn't provide a stable UUID in this output.
            # Store the index as both ID and "uuid" position to keep formatting consistent.
            if idxs:
                return [
                    {"properties": {"vendor": "amd", "uuid": i}, "id": i, "slots": 1} for i in idxs
                ]
        except Exception:
            logger = canary.get_logger(__name__)
            logger.debug(f"Failed to determine GPU counts from '{' '.join(args)}'")
    return None


def dedup(xs: Iterable[T]) -> list[T]:
    seen: set[T] = set()
    out: list[T] = []
    for x in xs:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out
