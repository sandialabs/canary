# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT


from _canary.queue import ResourceQueue
from _canary.queue_executor import ResourceQueueExecutor
from _canary.reporter import ReporterExecutorProtocol
from _canary.resource_pool import ResourcePool


def test_resource_queue_executor_satisfies_reporter_protocol():
    pool = ResourcePool(
        {"nodes": [{"id": "local", "resources": {"cpus": [{"id": "0", "slots": 1}], "gpus": []}}]}
    )
    queue = ResourceQueue(__import__("threading").Lock(), resource_pool=pool)

    executor = ResourceQueueExecutor(queue, executor=lambda *args, **kwargs: None, max_workers=1)

    protocol_obj: ReporterExecutorProtocol = executor

    assert protocol_obj.queue is queue
    assert protocol_obj.started_on == executor.started_on
