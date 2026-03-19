# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json
import os
import re
import shutil
import subprocess
from typing import Any

import canary

logger = canary.get_logger(__name__)


class CanaryGPUResourceSelector:
    backend: str | None = None

    def __init__(self) -> None:
        if "CANARY_GPU_BACKEND" in os.environ:
            self.backend = os.environ["CANARY_GPU_BACKEND"]

    @canary.hookimpl
    def canary_addoption(self, parser: "canary.Parser") -> None:
        parser.add_argument(
            "--gpu-backend",
            group="resource control",
            choices=("nvidia", "cuda", "amd", "rocm", "none", "auto"),
            default="auto",
            help="Use this GPU backend [default: auto]",
        )

    @canary.hookimpl
    def canary_configure(self, config: "canary.Config") -> None:
        hint: str = config.getoption("gpu_backend") or "auto"
        self.backend = self.determine_backend(hint)
        if self.backend:
            os.environ["CANARY_GPU_BACKEND"] = self.backend

    def determine_backend(self, hint: str) -> str | None:
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
    def canary_resource_pool_fill(
        self, config: "canary.Config", pool: dict[str, dict[str, Any]]
    ) -> None:
        resources: dict[str, list] = pool.setdefault("resources", {})
        if resources.get("gpus"):
            # GPU resources already filled
            return
        if self.backend == "NVIDIA":
            self._fill_nvidia(resources)
        elif self.backend == "AMD": self._fill_amd(resources)

    def _fill_nvidia(self, resources: dict[str, list]) -> None:
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

    def _fill_amd(self, resources: dict[str, list]) -> None:
        if self._fill_amd_smi(resources):
            return
        self._fill_rocm_smi(resources)

    def _fill_amd_smi(self, resources: dict[str, list]) -> bool:
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

    def _fill_rocm_smi(self, resources: dict[str, list]) -> bool:
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

    @canary.hookimpl
    def canary_runteststart(self, case: "canary.TestCase"):
        if self.backend and case.gpu_ids:
            gpu_ids = [id for id in case.gpu_ids if id.startswith(f"{self.backend}:")]
            if gpu_ids:
                visible = ",".join(gpu_id.split(":", 2)[2] for gpu_id in gpu_ids)
                if self.backend == "NVIDIA":
                    case.variables["CUDA_VISIBLE_DEVICES"] = visible
                elif self.backend == "AMD":
                    case.variables["ROCR_VISIBLE_DEVICES"] = visible
                    case.variables["HIP_VISIBLE_DEVICES"] = visible


gpu_selector = CanaryGPUResourceSelector()
