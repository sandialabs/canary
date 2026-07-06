# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os
import json
import re
import shutil
import subprocess
from typing import Iterable
from typing import TypeVar

import canary

T = TypeVar("T")


@canary.hookimpl
def canary_gpu_backend_detect(config: canary.Config) -> str | None:
    return "amd" if (shutil.which("amd-smi") or shutil.which("rocm-smi")) else None


@canary.hookimpl
def canary_gpu_list_gpus(config: canary.Config) -> list[dict] | None:
    if gpu_specs := _amd_smi_list_gpus(config):
        return gpu_specs
    elif gpu_specs := _rocm_smi_list_gpus(config):
        return gpu_specs
    return None


@canary.hookimpl
def canary_runteststart(case: "canary.Job"):

    gpu_ids = list(case.gpu_ids)
    if not gpu_ids:
        return

    visible_device_vars = ("HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES", "CUDA_VISIBLE_DEVICES")
    env = os.environ | case.variables
    if any(var in env for var in visible_device_vars):
        # User already set an AMD-compatible visible-devices variable, so don't
        # override. These variables can interact, so avoid creating an
        # inconsistent mask.
        return

    visible: str | None = None

    # Handle Canary AMD-qualified IDs, e.g. NVIDIA:h100:0 or NVIDIA:GPU-uuid:0
    if all(gpu_id.startswith("AMD:") for gpu_id in gpu_ids):
        visible = ",".join(gpu_id.rsplit(":", 1)[-1] for gpu_id in gpu_ids)

    # Handle integer GPU IDs, e.g. "0", "1", "2", "3"
    elif all(re.fullmatch(r"[0-9]+", gpu_id) for gpu_id in gpu_ids):
        visible = ",".join(gpu_ids)

    # Handle canary_hpc resource spec, e.g. "hpc:0:0"
    elif all(re.fullmatch(r"hpc:[0-9]+:[0-9]+", gpu_id) for gpu_id in gpu_ids):
        local_ids = [gpu_id.rsplit(":", 1)[-1] for gpu_id in gpu_ids]
        visible = ",".join(dict.fromkeys(local_ids))

    if visible is not None:
        case.variables["CUDA_VISIBLE_DEVICES"] = visible
        case.variables["ROCR_VISIBLE_DEVICES"] = visible
        case.variables["HIP_VISIBLE_DEVICES"] = visible


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
                gpu_specs.append({"vendor": "amd", "id": id, "uuid": uuid, "slots": 1})
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
            # (If you can get a UUID from your rocm-smi version, replace this.)
            if idxs:
                gpu_specs = [{"vendor": "amd", "id": i, "uuid": i, "slots": 1} for i in idxs]
                return gpu_specs
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
