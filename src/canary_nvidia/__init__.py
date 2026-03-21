# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
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
def canary_runteststart(case: "canary.TestCase"):
    gpu_ids = [id for id in case.gpu_ids if id.startswith("NVIDIA:")]
    if gpu_ids:
        visible = ",".join(gpu_id.split(":", 2)[2] for gpu_id in gpu_ids)
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
