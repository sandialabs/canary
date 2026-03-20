# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import re
import shutil
import subprocess
from typing import Any

import canary

logger = canary.get_logger(__name__)


@canary.hookimpl
def canary_addoption(parser: "canary.Parser") -> None:
    parser.add_argument(
        "--gpu-backend",
        group="resource control",
        choices=("nvidia", "cuda", "amd", "rocm", "none", "auto"),
        default="auto",
        help="Use this GPU backend [default: auto]",
    )


@canary.hookimpl
def canary_configure(config: "canary.Config") -> None:
    hint: str = config.getoption("gpu_backend") or "auto"
    backend = validate_backend(hint)
    setattr(config.options, "gpu_backend", backend)
    config.set("scratch:gpu:backend", backend)


@canary.hookimpl
def canary_runteststart(case: "canary.TestCase"):
    backend = canary.config.get("scratch:gpu:backend")
    gpu_ids = [id for id in case.gpu_ids if id.startswith(f"{backend}:")]
    if gpu_ids:
        visible = ",".join(gpu_id.split(":", 2)[2] for gpu_id in gpu_ids)
        if backend == "NVIDIA":
            case.variables["CUDA_VISIBLE_DEVICES"] = visible
        elif backend == "AMD":
            case.variables["ROCR_VISIBLE_DEVICES"] = visible
            case.variables["HIP_VISIBLE_DEVICES"] = visible


def validate_backend(hint: str) -> str | None:
    if hint == "none":
        return None
    if hint == "auto":
        if shutil.which("nvidia-smi"):
            return "NVIDIA"
        if shutil.which("amd-smi"):
            return "AMD"
        return None
    if hint in ("nvidia", "cuda"):
        if not shutil.which("nvidia-smi"):
            raise ValueError("gpu_backend=nvidia requires nvidia-smi be on PATH")
        return "NVIDIA"
    if hint == ("amd", "rocm"):
        if not (shutil.which("amd-smi") or shutil.which("rocm-smi")):
            raise ValueError("gpu_backend=amd requires amd-smi or rocm-smi be on PATH")
        return "AMD"
    raise ValueError(f"Unknown gpu backend: {hint}")


@canary.hookimpl
def canary_resource_pool_fill(config: "canary.Config", pool: dict[str, dict[str, Any]]) -> None:
    resources: dict[str, list] = pool.setdefault("resources", {})
    if resources.get("gpus"):
        return
    backend = config.get("scratch:gpu:backend")
    if backend == "NVIDIA":
        _fill_nvidia(resources)
    elif backend == "AMD":
        _fill_amd(resources)


def _fill_nvidia(resources: dict[str, list]) -> None:
    if nvidia_smi := shutil.which("nvidia-smi"):
        gpu_ids: list[str] = []
        args = [nvidia_smi, "--query-gpu=index,uuid,name", "--format=csv,noheader,nounits"]
        try:
            txt = subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True)
            for line in txt.splitlines():
                id, uuid, _ = [_.strip() for _ in line.split(",", 2)]
                gpu_ids.append(f"NVIDIA:{id}:{uuid}")
            resources["gpus"] = [{"id": gpu_id, "slots": 1} for gpu_id in gpu_ids]
        except Exception:
            logger.debug(f"Failed to determine GPU counts from '{' '.join(args)}'")


def _fill_amd(resources: dict[str, list]) -> None:
    if _fill_amd_smi(resources):
        return
    _fill_rocm_smi(resources)


def _fill_amd_smi(resources: dict[str, list]) -> bool:
    if not (amd_smi := shutil.which("amd-smi")):
        return False
    args = [amd_smi, "list", "--json"]
    try:
        txt = subprocess.check_output(args, stderr=subprocess.DEVNULL, text=True)
        data = json.loads(txt)
        gpu_ids: list[str] = []
        for entry in data:
            id = entry["gpu"]
            uuid = entry["uuid"]
            if not uuid.startswith("GPU-"):
                uuid = f"GPU-{uuid}"
            gpu_ids.append(f"AMD:{id}:{uuid}")
        if gpu_ids:
            resources["gpus"] = [{"id": gpu_id, "slots": 1} for gpu_id in gpu_ids]
        return True
    except Exception:
        logger.debug(f"Failed to determine GPU counts from '{' '.join(args)}'")
    return False


def _fill_rocm_smi(resources: dict[str, list]) -> bool:
    if not (rocm_smi := shutil.which("rocm-smi")):
        return False

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
        seen: set[str] = set()
        idxs = [x for x in idxs if not (x in seen or seen.add(x))]

        # rocm-smi typically doesn't provide a stable UUID in this output.
        # Store the index as both ID and "uuid" position to keep formatting consistent.
        # (If you can get a UUID from your rocm-smi version, replace this.)
        if idxs:
            resources["gpus"] = [{"id": f"AMD:{i}:{i}", "slots": 1} for i in idxs]
            return True
    except Exception:
        logger.debug(f"Failed to determine GPU counts from '{' '.join(args)}'")

    return False
