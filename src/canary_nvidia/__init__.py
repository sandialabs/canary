# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import shutil
import subprocess
from typing import Any

import canary


@canary.hookimpl
def canary_configure(config: canary.Config) -> str | None:
    if shutil.which("nvidia-smi") is None:
        raise ValueError("canary_nvidia plugin requires nvidia-smi on PATH")


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
    gpu_specs = _nvidia_smi_list_gpus(config)
    if gpu_specs:
        node.set_resource("gpus", gpu_specs)


@canary.hookimpl
def canary_runteststart(case: "canary.Job") -> None:
    if "CUDA_VISIBLE_DEVICES" in case.variables:
        # User already set visible devices: don't override.
        return

    gpus = _nvidia_gpus(case)
    if not gpus:
        return

    # GPU resource IDs are node-local runtime device IDs in the topology-aware
    # resource model.
    local_ids = [str(gpu["id"]) for gpu in gpus]

    # Preserve order while removing duplicates. This matters for multi-node
    # allocations where each node may contribute local GPU id "0".
    visible = ",".join(dict.fromkeys(local_ids))

    if visible:
        case.variables["CUDA_VISIBLE_DEVICES"] = visible


def _nvidia_gpus(case: "canary.Job") -> list[dict[str, Any]]:
    resources = getattr(case, "resources", None)
    if not isinstance(resources, dict):
        return []

    gpus = resources.get("gpus", [])
    if not isinstance(gpus, list):
        return []

    nvidia_gpus: list[dict[str, Any]] = []

    for gpu in gpus:
        if not isinstance(gpu, dict):
            return []

        properties = gpu.get("properties", {})
        if not isinstance(properties, dict):
            return []

        vendor = str(properties.get("vendor", "")).upper()
        if vendor not in {"NVIDIA", "UNKNOWN", ""}:
            return []

        if "id" not in gpu:
            return []

        nvidia_gpus.append(gpu)

    return nvidia_gpus


def _nvidia_smi_list_gpus(config: canary.Config) -> list[dict] | None:
    if nvidia_smi := shutil.which("nvidia-smi"):
        gpu_specs: list[dict] = []
        args = [nvidia_smi, "--query-gpu=index,uuid,name", "--format=csv,noheader,nounits"]
        try:
            txt = subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True)
            for line in txt.splitlines():
                id, uuid, _ = [_.strip() for _ in line.split(",", 2)]
                properties = {"vendor": "nvidia", "uuid": uuid}
                gpu_specs.append({"id": id, "slots": 1, "properties": properties})
            return gpu_specs
        except Exception:
            logger = canary.get_logger(__name__)
            logger.debug(f"Failed to determine GPU counts from '{' '.join(args)}'")
    return None
