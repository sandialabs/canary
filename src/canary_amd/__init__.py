# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT
import json
import re
import shutil
import subprocess

import canary


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
def canary_runteststart(case: "canary.TestCase"):
    gpu_ids = [id for id in case.gpu_ids if id.startswith("AMD:")]
    if gpu_ids:
        visible = ",".join(gpu_id.split(":", 2)[2] for gpu_id in gpu_ids)
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
            seen: set[str] = set()
            idxs = [x for x in idxs if not (x in seen or seen.add(x))]
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
