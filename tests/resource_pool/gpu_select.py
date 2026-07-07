# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

from typing import Any

import pytest

from _canary.resource_pool import ResourcePool
from _canary.resource_pool import gpu_select


class FakeGPUPlugin:
    def __init__(self, gpu_specs: list[dict[str, Any]] | None = None) -> None:
        self.gpu_specs = gpu_specs or []
        self.called = False

    def canary_gpu_list_gpus(self, config) -> list[dict[str, Any]]:
        self.called = True
        return self.gpu_specs


class RaisingGPUPlugin:
    def canary_gpu_list_gpus(self, config):
        raise AssertionError("GPU discovery should not have been called")


class FakePluginManager:
    def __init__(self, plugins: dict[str, Any]) -> None:
        self.plugins = plugins

    def get_plugin(self, name: str) -> Any:
        return self.plugins.get(name)


class FakeConfig:
    def __init__(
        self,
        *,
        backend: dict[str, str] | None = None,
        plugin: Any | None = None,
        plugin_name: str = "fake_gpu_plugin",
    ) -> None:
        self.backend = backend
        self.pluginmanager = FakePluginManager({plugin_name: plugin} if plugin else {})

    def get(self, path: str, default: Any = None) -> Any:
        if path == "gpu_select:.runtime:backend":
            return self.backend
        return default


def make_pool() -> ResourcePool:
    return ResourcePool(
        {
            "nodes": [
                {
                    "id": "local",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 1}],
                        "gpus": [],
                    },
                }
            ]
        }
    )


def test_gpu_select_adds_gpus_to_first_node():
    plugin = FakeGPUPlugin(
        [
            {
                "id": "0",
                "slots": 1,
                "vendor": "nvidia",
                "uuid": "GPU-0000",
                "name": "NVIDIA H100",
            },
            {
                "id": "1",
                "slots": 1,
                "vendor": "nvidia",
                "uuid": "GPU-1111",
                "name": "NVIDIA H100",
            },
        ]
    )
    config = FakeConfig(
        backend={"name": "nvidia", "plugin": "fake_gpu_plugin"},
        plugin=plugin,
    )
    pool = make_pool()

    gpu_select.canary_fill_gpu(config=config, pool=pool)

    assert plugin.called
    assert pool.first_node().resources["gpus"] == [
        {
            "id": "0",
            "slots": 1,
            "properties": {
                "vendor": "NVIDIA",
                "uuid": "GPU-0000",
                "name": "NVIDIA H100",
            },
        },
        {
            "id": "1",
            "slots": 1,
            "properties": {
                "vendor": "NVIDIA",
                "uuid": "GPU-1111",
                "name": "NVIDIA H100",
            },
        },
    ]


def test_gpu_select_does_not_override_existing_gpus():
    config = FakeConfig(
        backend={"name": "nvidia", "plugin": "fake_gpu_plugin"},
        plugin=RaisingGPUPlugin(),
    )
    pool = ResourcePool(
        {
            "nodes": [
                {
                    "id": "local",
                    "resources": {
                        "cpus": [{"id": "0", "slots": 1}],
                        "gpus": [
                            {
                                "id": "7",
                                "slots": 1,
                                "properties": {"vendor": "UNKNOWN"},
                            }
                        ],
                    },
                }
            ]
        }
    )

    gpu_select.canary_fill_gpu(config=config, pool=pool)

    assert pool.first_node().resources["gpus"] == [
        {
            "id": "7",
            "slots": 1,
            "properties": {"vendor": "UNKNOWN"},
        }
    ]


def test_gpu_select_no_backend_does_nothing():
    config = FakeConfig(backend=None)
    pool = make_pool()

    gpu_select.canary_fill_gpu(config=config, pool=pool)

    assert pool.first_node().resources["gpus"] == []


def test_gpu_select_missing_plugin_raises():
    config = FakeConfig(
        backend={"name": "nvidia", "plugin": "missing_plugin"},
        plugin=None,
    )
    pool = make_pool()

    with pytest.raises(RuntimeError, match="Selected GPU plugin"):
        gpu_select.canary_fill_gpu(config=config, pool=pool)


def test_gpu_resource_spec_defaults_vendor_to_unknown():
    spec = gpu_select._gpu_resource_spec({"id": 0, "slots": 1})

    assert spec == {
        "id": "0",
        "slots": 1,
        "properties": {
            "vendor": "UNKNOWN",
        },
    }


def test_select_backend_auto_none():
    config = type("Config", (), {"getoption": lambda self, name: "auto"})()

    selected = gpu_select._select_backend(config, {})

    assert selected is None


def test_select_backend_auto_single():
    config = type("Config", (), {"getoption": lambda self, name: "auto"})()

    selected = gpu_select._select_backend(config, {"nvidia": "canary_nvidia"})

    assert selected == {"name": "nvidia", "plugin": "canary_nvidia"}


def test_select_backend_auto_multiple_raises():
    config = type("Config", (), {"getoption": lambda self, name: "auto"})()

    with pytest.raises(ValueError, match="Multiple GPU backends detected"):
        gpu_select._select_backend(
            config,
            {
                "nvidia": "canary_nvidia",
                "amd": "canary_amd",
            },
        )


def test_select_backend_explicit_backend_name():
    config = type("Config", (), {"getoption": lambda self, name: "nvidia"})()

    selected = gpu_select._select_backend(
        config,
        {
            "nvidia": "canary_nvidia",
            "amd": "canary_amd",
        },
    )

    assert selected == {"name": "nvidia", "plugin": "canary_nvidia"}


def test_select_backend_explicit_plugin_name():
    config = type("Config", (), {"getoption": lambda self, name: "canary_nvidia"})()

    selected = gpu_select._select_backend(
        config,
        {
            "nvidia": "canary_nvidia",
            "amd": "canary_amd",
        },
    )

    assert selected == {"name": "nvidia", "plugin": "canary_nvidia"}


def test_select_backend_missing_explicit_raises():
    config = type("Config", (), {"getoption": lambda self, name: "intel"})()

    with pytest.raises(ValueError, match="GPU backend 'intel' not detected"):
        gpu_select._select_backend(
            config,
            {
                "nvidia": "canary_nvidia",
                "amd": "canary_amd",
            },
        )
