# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Any

# Adjust this import to the actual plugin module path.
#
# Examples:
#   import canary_amd as amd
#   from _canary.plugins import canary_amd as amd
#   from _canary.resource_pool import amd
#
import canary_amd as amd


class FakeJob:
    def __init__(self, resources: dict[str, list[dict[str, Any]]]) -> None:
        self.resources = resources
        self.variables: dict[str, str] = {}


def test_amd_sets_visible_devices_for_amd_gpus(monkeypatch):
    for var in amd._AMD_VISIBLE_DEVICES_VARIABLES:
        monkeypatch.delenv(var, raising=False)

    job = FakeJob(
        {
            "gpus": [
                {"node": "local", "id": "0", "slots": 1, "properties": {"vendor": "AMD"}},
                {"node": "local", "id": "1", "slots": 1, "properties": {"vendor": "AMD"}},
            ]
        }
    )

    amd.canary_runteststart(job)

    assert job.variables["HIP_VISIBLE_DEVICES"] == "0,1"
    assert job.variables["ROCR_VISIBLE_DEVICES"] == "0,1"
    assert job.variables["CUDA_VISIBLE_DEVICES"] == "0,1"


def test_amd_sets_visible_devices_for_rocm_vendor(monkeypatch):
    for var in amd._AMD_VISIBLE_DEVICES_VARIABLES:
        monkeypatch.delenv(var, raising=False)

    job = FakeJob(
        {"gpus": [{"node": "local", "id": "0", "slots": 1, "properties": {"vendor": "ROCM"}}]}
    )

    amd.canary_runteststart(job)

    assert job.variables["HIP_VISIBLE_DEVICES"] == "0"
    assert job.variables["ROCR_VISIBLE_DEVICES"] == "0"
    assert job.variables["CUDA_VISIBLE_DEVICES"] == "0"


def test_amd_deduplicates_local_ids_for_multinode(monkeypatch):
    for var in amd._AMD_VISIBLE_DEVICES_VARIABLES:
        monkeypatch.delenv(var, raising=False)

    job = FakeJob(
        {
            "gpus": [
                {"node": "0", "id": "0", "slots": 1, "properties": {"vendor": "AMD"}},
                {"node": "1", "id": "0", "slots": 1, "properties": {"vendor": "AMD"}},
            ]
        }
    )

    amd.canary_runteststart(job)

    assert job.variables["HIP_VISIBLE_DEVICES"] == "0"
    assert job.variables["ROCR_VISIBLE_DEVICES"] == "0"
    assert job.variables["CUDA_VISIBLE_DEVICES"] == "0"


def test_amd_does_not_claim_unknown_vendor(monkeypatch):
    for var in amd._AMD_VISIBLE_DEVICES_VARIABLES:
        monkeypatch.delenv(var, raising=False)

    job = FakeJob(
        {"gpus": [{"node": "local", "id": "0", "slots": 1, "properties": {"vendor": "UNKNOWN"}}]}
    )

    amd.canary_runteststart(job)

    assert "HIP_VISIBLE_DEVICES" not in job.variables
    assert "ROCR_VISIBLE_DEVICES" not in job.variables
    assert "CUDA_VISIBLE_DEVICES" not in job.variables


def test_amd_does_not_claim_missing_vendor(monkeypatch):
    for var in amd._AMD_VISIBLE_DEVICES_VARIABLES:
        monkeypatch.delenv(var, raising=False)

    job = FakeJob({"gpus": [{"node": "local", "id": "0", "slots": 1, "properties": {}}]})

    amd.canary_runteststart(job)

    assert "HIP_VISIBLE_DEVICES" not in job.variables
    assert "ROCR_VISIBLE_DEVICES" not in job.variables
    assert "CUDA_VISIBLE_DEVICES" not in job.variables


def test_amd_does_not_claim_nvidia_vendor(monkeypatch):
    for var in amd._AMD_VISIBLE_DEVICES_VARIABLES:
        monkeypatch.delenv(var, raising=False)

    job = FakeJob(
        {"gpus": [{"node": "local", "id": "0", "slots": 1, "properties": {"vendor": "NVIDIA"}}]}
    )

    amd.canary_runteststart(job)

    assert "HIP_VISIBLE_DEVICES" not in job.variables
    assert "ROCR_VISIBLE_DEVICES" not in job.variables
    assert "CUDA_VISIBLE_DEVICES" not in job.variables


def test_amd_does_not_override_existing_env_visible_device(monkeypatch):
    for var in amd._AMD_VISIBLE_DEVICES_VARIABLES:
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("HIP_VISIBLE_DEVICES", "7")

    job = FakeJob(
        {"gpus": [{"node": "local", "id": "0", "slots": 1, "properties": {"vendor": "AMD"}}]}
    )

    amd.canary_runteststart(job)

    assert "HIP_VISIBLE_DEVICES" not in job.variables
    assert "ROCR_VISIBLE_DEVICES" not in job.variables
    assert "CUDA_VISIBLE_DEVICES" not in job.variables


def test_amd_does_not_override_existing_case_variable(monkeypatch):
    for var in amd._AMD_VISIBLE_DEVICES_VARIABLES:
        monkeypatch.delenv(var, raising=False)

    job = FakeJob(
        {"gpus": [{"node": "local", "id": "0", "slots": 1, "properties": {"vendor": "AMD"}}]}
    )
    job.variables["ROCR_VISIBLE_DEVICES"] = "7"

    amd.canary_runteststart(job)

    assert job.variables == {"ROCR_VISIBLE_DEVICES": "7"}


def test_amd_no_gpus_noop(monkeypatch):
    for var in amd._AMD_VISIBLE_DEVICES_VARIABLES:
        monkeypatch.delenv(var, raising=False)

    job = FakeJob({})

    amd.canary_runteststart(job)

    assert "HIP_VISIBLE_DEVICES" not in job.variables
    assert "ROCR_VISIBLE_DEVICES" not in job.variables
    assert "CUDA_VISIBLE_DEVICES" not in job.variables
