# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import os
import re
import shutil
import subprocess

import canary


@canary.hookimpl
def canary_gpu_backend_detect(config: canary.Config) -> str | None:
    return "nvidia" if shutil.which("nvidia-smi") else None


@canary.hookimpl
def canary_gpu_list_gpus(config: canary.Config) -> list[dict] | None:
    return _nvidia_smi_list_gpus(config)


@canary.hookimpl
def canary_runteststart(case: "canary.Job"):

    gpu_ids = list(case.gpu_ids)
    if not gpu_ids:
        return

    if "CUDA_VISIBLE_DEVICES" in os.environ or "CUDA_VISIBLE_DEVICES" in case.variables:
        # User already set visible devices: don't override
        return

    visible: str | None = None

    # Handle Canary NVIDIA-qualified IDs, e.g. NVIDIA:h100:0 or NVIDIA:GPU-uuid:0
    if all(gpu_id.startswith("NVIDIA:") for gpu_id in gpu_ids):
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
