# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import json


def test_executor_resource_pool_fill_returns_batch_local_pool(tmp_path):
    workspace = tmp_path / "batch"
    workspace.mkdir()

    resource_pool = {
        "allow_multinode": False,
        "additional_properties": {
            "source": "distributed-checkout",
            "hostname": "host-a",
            "transaction_id": "tx-1",
        },
        "nodes": [{"id": "host-a", "resources": {"cpus": [{"id": "0", "slots": 1}]}}],
    }

    config = {
        "id": "batch-1",
        "session": "session-1",
        "workspace": str(workspace),
        "jobs": ["job-1"],
    }

    (workspace / "batch.lock").write_text(json.dumps(config))
    (workspace / "resource_pool.json").write_text(json.dumps({"resource_pool": resource_pool}))
