# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os
import shutil
import subprocess
from typing import Any

import canary


@canary.hookimpl
def canary_gpu_backend_detect(config: canary.Config) -> str | None:
    return "nvidia" if shutil.which("nvidia-smi") else None


@canary.hookimpl
def canary_gpu_list_gpus(config: canary.Config) -> list[dict] | None:
    return _nvidia_smi_list_gpus(config)


@canary.hookimpl
def canary_runteststart(case: "canary.Job") -> None:
    if "CUDA_VISIBLE_DEVICES" in os.environ or "CUDA_VISIBLE_DEVICES" in case.variables:
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
                gpu_specs.append({"vendor": "nvidia", "id": id, "uuid": uuid, "slots": 1})
            return gpu_specs
        except Exception:
            logger = canary.get_logger(__name__)
            logger.debug(f"Failed to determine GPU counts from '{' '.join(args)}'")
    return None
