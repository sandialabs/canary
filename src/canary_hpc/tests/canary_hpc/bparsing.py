# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import argparse

import pytest

from canary_hpc.argparsing import CanaryHPCBatchExec
from canary_hpc.argparsing import CanaryHPCBatchSpec
from canary_hpc.argparsing import CanaryHPCResourceSetter
from canary_hpc.argparsing import CanaryHPCSchedulerArgs
from canary_hpc.batching import MAX_COUNT
from canary_hpc.batching import BatchingSpec
from canary_hpc.batching import CountTarget
from canary_hpc.batching import DurationTarget


def test_scheduler_args_parse() -> None:
    assert CanaryHPCSchedulerArgs.parse("--queue=foo,--account=bar") == [
        "--queue=foo",
        "--account=bar",
    ]


def test_batch_exec_parse() -> None:
    spec = CanaryHPCBatchExec.parse("backend=slurm,batch=sbatch,job=srun")

    assert spec == {"backend": "slurm", "batch": "sbatch", "job": "srun"}


def test_batch_exec_parse_requires_backend() -> None:
    with pytest.raises(ValueError, match="backend"):
        CanaryHPCBatchExec.parse("batch=sbatch")


def test_batch_exec_parse_requires_batch() -> None:
    with pytest.raises(ValueError, match="batch"):
        CanaryHPCBatchExec.parse("backend=slurm")


def test_batch_spec_parse_duration() -> None:
    spec = CanaryHPCBatchSpec.parse("layout=flat,nodes=same,duration=30m")

    assert spec == {"layout": "flat", "nodes": "same", "duration": 1800.0}


def test_batch_spec_parse_count() -> None:
    spec = CanaryHPCBatchSpec.parse("layout=flat,nodes=any,count=4")

    assert spec == {"layout": "flat", "nodes": "any", "count": 4}


def test_batch_spec_parse_count_max() -> None:
    spec = CanaryHPCBatchSpec.parse("layout=atomic,nodes=any,count=max")

    assert spec == {"layout": "atomic", "nodes": "any", "count": MAX_COUNT}


def test_batch_spec_parse_rejects_count_auto() -> None:
    with pytest.raises(ValueError, match="count=auto"):
        CanaryHPCBatchSpec.parse("count=auto")


def test_batch_spec_parse_rejects_nonpositive_count() -> None:
    with pytest.raises(ValueError, match="count <= 0"):
        CanaryHPCBatchSpec.parse("count=0")


def test_batch_spec_parse_rejects_nonpositive_duration() -> None:
    with pytest.raises(ValueError, match="duration"):
        CanaryHPCBatchSpec.parse("duration=0")


def test_batch_spec_parse_rejects_unknown_arg() -> None:
    with pytest.raises(ValueError, match="invalid batch spec arg"):
        CanaryHPCBatchSpec.parse("spam=eggs")


def test_batch_spec_validate_defaults_flat() -> None:
    spec = CanaryHPCBatchSpec.validate_and_set_defaults(None)

    assert isinstance(spec, BatchingSpec)
    assert spec.layout == "flat"
    assert spec.node_policy == "same"
    assert isinstance(spec.target, DurationTarget)
    assert spec.duration == 30 * 60.0
    assert spec.count is None


def test_batch_spec_validate_defaults_atomic() -> None:
    raw = {"layout": "atomic", "nodes": None, "count": None, "duration": None}

    spec = CanaryHPCBatchSpec.validate_and_set_defaults(raw)

    assert isinstance(spec, BatchingSpec)
    assert spec.layout == "atomic"
    assert spec.node_policy == "any"
    assert isinstance(spec.target, CountTarget)
    assert spec.count == MAX_COUNT
    assert spec.duration is None


def test_batch_spec_validate_duration_target() -> None:
    raw = {"layout": "flat", "nodes": "same", "count": None, "duration": 120.0}

    spec = CanaryHPCBatchSpec.validate_and_set_defaults(raw)

    assert spec.layout == "flat"
    assert spec.node_policy == "same"
    assert isinstance(spec.target, DurationTarget)
    assert spec.duration == 120.0
    assert spec.count is None


def test_batch_spec_validate_count_target() -> None:
    raw = {"layout": "flat", "nodes": "any", "count": 3, "duration": None}

    spec = CanaryHPCBatchSpec.validate_and_set_defaults(raw)

    assert spec.layout == "flat"
    assert spec.node_policy == "any"
    assert isinstance(spec.target, CountTarget)
    assert spec.count == 3
    assert spec.duration is None


def test_batch_spec_validate_count_max_target() -> None:
    raw = {"layout": "atomic", "nodes": "any", "count": "max", "duration": None}

    spec = CanaryHPCBatchSpec.validate_and_set_defaults(raw)

    assert spec.layout == "atomic"
    assert spec.node_policy == "any"
    assert isinstance(spec.target, CountTarget)
    assert spec.count == MAX_COUNT


def test_batch_spec_validate_rejects_duration_and_count() -> None:
    raw = {"layout": "flat", "nodes": "same", "count": 2, "duration": 120.0}

    with pytest.raises(ValueError, match="duration.*count|count.*duration"):
        CanaryHPCBatchSpec.validate_and_set_defaults(raw)


def test_batch_spec_validate_rejects_atomic_nodes_same() -> None:
    raw = {"layout": "atomic", "nodes": "same", "count": "max", "duration": None}

    with pytest.raises(ValueError, match="layout=atomic requires nodes=any"):
        CanaryHPCBatchSpec.validate_and_set_defaults(raw)


def test_batch_spec_validate_rejects_atomic_duration() -> None:
    raw = {"layout": "atomic", "nodes": "any", "count": None, "duration": 120.0}

    with pytest.raises(ValueError, match="duration-targeted atomic"):
        CanaryHPCBatchSpec.validate_and_set_defaults(raw)


def test_hpc_resource_setter_workers() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", action=CanaryHPCResourceSetter, dest="hpc_resource")

    ns = parser.parse_args(["-b", "workers=7"])

    assert ns.hpc_batch_workers == 7


def test_hpc_resource_setter_rejects_nonpositive_workers() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", action=CanaryHPCResourceSetter, dest="hpc_resource")

    with pytest.raises(ValueError, match="workers"):
        parser.parse_args(["-b", "workers=0"])


def test_batch_spec_argparse_action_stores_raw_batchspec_dict() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", action=CanaryHPCBatchSpec, dest="hpc_batchspec")

    ns = parser.parse_args(["--batch", "layout=flat,nodes=any,duration=10m"])

    assert ns.hpc_batchspec == {"nodes": "any", "layout": "flat", "count": None, "duration": 600.0}

    spec = CanaryHPCBatchSpec.validate_and_set_defaults(ns.hpc_batchspec)

    assert isinstance(spec, BatchingSpec)
    assert spec.layout == "flat"
    assert spec.node_policy == "any"
    assert isinstance(spec.target, DurationTarget)
    assert spec.duration == 600.0
    assert spec.count is None


def test_batch_spec_argparse_action_merges_repeated_values() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", action=CanaryHPCBatchSpec, dest="hpc_batchspec")

    ns = parser.parse_args(["--batch", "layout=flat,nodes=same", "--batch", "count=2"])

    assert ns.hpc_batchspec == {"nodes": "same", "layout": "flat", "count": 2, "duration": None}

    spec = CanaryHPCBatchSpec.validate_and_set_defaults(ns.hpc_batchspec)

    assert isinstance(spec, BatchingSpec)
    assert spec.layout == "flat"
    assert spec.node_policy == "same"
    assert isinstance(spec.target, CountTarget)
    assert spec.count == 2
    assert spec.duration is None


def test_hpc_resource_setter_spec_stores_raw_batchspec_dict() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", action=CanaryHPCResourceSetter, dest="hpc_resource")

    ns = parser.parse_args(["-b", "spec=layout=flat,nodes=any,count=3"])

    assert ns.hpc_batchspec == {"nodes": "any", "layout": "flat", "count": 3, "duration": None}

    spec = CanaryHPCBatchSpec.validate_and_set_defaults(ns.hpc_batchspec)

    assert isinstance(spec, BatchingSpec)
    assert spec.layout == "flat"
    assert spec.node_policy == "any"
    assert isinstance(spec.target, CountTarget)
    assert spec.count == 3
    assert spec.duration is None
