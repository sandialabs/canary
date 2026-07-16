# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Any

# Adjust this import to the actual plugin module path.
#
# Examples:
#   import canary_nvidia as nvidia
#   from _canary.plugins import canary_nvidia as nvidia
#   from _canary.resource_pool import nvidia
#
import canary_nvidia as nvidia


class FakeJob:
    def __init__(self, resources: dict[str, list[dict[str, Any]]]) -> None:
        self.resources = resources
        self.variables: dict[str, str] = {}


def test_nvidia_sets_cuda_visible_devices_for_nvidia_gpus(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)

    job = FakeJob(
        {
            "gpus": [
                {"node": "local", "id": "0", "slots": 1, "properties": {"vendor": "NVIDIA"}},
                {"node": "local", "id": "1", "slots": 1, "properties": {"vendor": "NVIDIA"}},
            ]
        }
    )

    nvidia.canary_runteststart(job)

    assert job.variables["CUDA_VISIBLE_DEVICES"] == "0,1"


def test_nvidia_sets_cuda_visible_devices_for_unknown_vendor(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)

    job = FakeJob(
        {
            "gpus": [
                {"node": "local", "id": "0", "slots": 1, "properties": {"vendor": "UNKNOWN"}},
                {"node": "local", "id": "1", "slots": 1, "properties": {"vendor": "UNKNOWN"}},
            ]
        }
    )

    nvidia.canary_runteststart(job)

    assert job.variables["CUDA_VISIBLE_DEVICES"] == "0,1"


def test_nvidia_treats_missing_vendor_as_unknown(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)

    job = FakeJob({"gpus": [{"node": "local", "id": "0", "slots": 1, "properties": {}}]})

    nvidia.canary_runteststart(job)

    assert job.variables["CUDA_VISIBLE_DEVICES"] == "0"


def test_nvidia_treats_missing_properties_as_unknown(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)

    job = FakeJob({"gpus": [{"node": "local", "id": "0", "slots": 1}]})

    nvidia.canary_runteststart(job)

    assert job.variables["CUDA_VISIBLE_DEVICES"] == "0"


def test_nvidia_deduplicates_local_ids_for_multinode(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)

    job = FakeJob(
        {
            "gpus": [
                {"node": "0", "id": "0", "slots": 1, "properties": {"vendor": "NVIDIA"}},
                {"node": "1", "id": "0", "slots": 1, "properties": {"vendor": "NVIDIA"}},
            ]
        }
    )

    nvidia.canary_runteststart(job)

    assert job.variables["CUDA_VISIBLE_DEVICES"] == "0"


def test_nvidia_does_not_claim_explicit_amd_gpus(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)

    job = FakeJob(
        {"gpus": [{"node": "local", "id": "0", "slots": 1, "properties": {"vendor": "AMD"}}]}
    )

    nvidia.canary_runteststart(job)

    assert "CUDA_VISIBLE_DEVICES" not in job.variables


def test_nvidia_does_not_override_case_variable(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)

    job = FakeJob(
        {"gpus": [{"node": "local", "id": "0", "slots": 1, "properties": {"vendor": "NVIDIA"}}]}
    )
    job.variables["CUDA_VISIBLE_DEVICES"] = "7"

    nvidia.canary_runteststart(job)

    assert job.variables["CUDA_VISIBLE_DEVICES"] == "7"


def test_nvidia_no_gpus_noop(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)

    job = FakeJob({})

    nvidia.canary_runteststart(job)

    assert "CUDA_VISIBLE_DEVICES" not in job.variables
