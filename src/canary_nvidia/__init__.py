import re
import shutil
import subprocess
from typing import Any

import canary

logger = canary.get_logger(__name__)


@canary.hookimpl
def canary_resource_pool_fill(config: "canary.Config", pool: dict[str, dict[str, Any]]) -> None:
    resources: dict[str, list] = pool.setdefault("resources", {})
    if resources.get("gpus"):
        return
    if nvidia_smi := shutil.which("nvidia-smi"):
        gpu_ids: list[str] = []
        try:
            p = subprocess.run([nvidia_smi, "--list-gpus"], stdout=subprocess.PIPE, text=True)
            for line in p.stdout.split("\n"):
                if match := re.search(r"GPU (\d+):", line):
                    gpu_ids.append(match.group(1))
            resources["gpus"] = [{"id": gpu_id, "slots": 1} for gpu_id in gpu_ids]
        except Exception:
            logger.debug(f"Failed to determine GPU counts from '{nvidia_smi} --list-gpus'")
