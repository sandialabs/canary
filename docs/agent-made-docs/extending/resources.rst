.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _extending-resources:

Resources
=========

Extensions can customize resource management by adding custom resource types, modifying resource pool behavior, and integrating with external resource managers.

Resource Pool Hooks
-------------------

**canary_resource_pool_fill**: Create resource pool

.. code-block:: python

   @canary.hookimpl
   def canary_resource_pool_fill(config):
       return {
           "nodes": [
               {
                   "id": "node1",
                   "resources": {
                       "cpus": [{"id": "0", "slots": 8}],
                       "custom_resource": [{"id": "accel0", "slots": 4}]
                   }
               }
           ]
       }

**canary_resource_pool_update**: Modify resource pool

.. code-block:: python

   @canary.hookimpl
   def canary_resource_pool_update(config, pool):
       # Add custom resources to existing pool
       for node in pool["nodes"]:
           if "custom_resource" not in node["resources"]:
               node["resources"]["custom_resource"] = []

**canary_resource_pool_accommodates**: Check resource availability

.. code-block:: python

   @canary.hookimpl
   def canary_resource_pool_accommodates(pool, request):
       # Custom accommodation logic
       return check_custom_resources(pool, request)

Topology-Aware Pool Specs
--------------------------

Create multi-node resource pools:

.. code-block:: python

   @canary.hookimpl
   def canary_resource_pool_fill(config):
       return {
           "allow_multinode": True,
           "nodes": [
               {
                   "id": "gpu-node-1",
                   "resources": {
                       "cpus": [{"id": "0", "slots": 16}],
                       "gpus": [{"id": "0", "slots": 4}]
                   }
               },
               {
                   "id": "gpu-node-2",
                   "resources": {
                       "cpus": [{"id": "0", "slots": 16}],
                       "gpus": [{"id": "0", "slots": 4}]
                   }
               }
           ]
       }

Custom Resources
----------------

Add non-standard resource types:

.. code-block:: python

   @canary.hookimpl
   def canary_resource_pool_fill(config):
       pool = {
           "nodes": [{
               "id": "special-node",
               "resources": {
                   "cpus": [{"id": "0", "slots": 8}],
                   "fpgas": [{"id": "fpga0", "slots": 2}],
                   "accelerators": [{"id": "accel0", "slots": 1}]
               }
           }]
       }
       return pool

GPU/Scheduler Extensions
------------------------

Integrate with GPU managers:

.. code-block:: python

   @canary.hookimpl
   def canary_resource_pool_fill(config):
       # Query GPU manager for available devices
       gpu_devices = query_gpu_manager()

       return {
           "nodes": [{
               "id": "gpu-host",
               "resources": {
                   "cpus": [{"id": str(i), "slots": 1} for i in range(32)],
                   "gpus": [{"id": str(dev.id), "slots": 1} for dev in gpu_devices]
               }
           }]
       }

Resource Count/Type Hooks
-------------------------

**canary_resource_pool_count**: Report resource counts

.. code-block:: python

   @canary.hookimpl
   def canary_resource_pool_count(pool, resource_type):
       if resource_type == "custom":
           return count_custom_resources(pool)
       return None

**canary_resource_pool_describe**: Describe resource pool

.. code-block:: python

   @canary.hookimpl
   def canary_resource_pool_describe(pool):
       description = []
       for node in pool["nodes"]:
           for rtype, resources in node["resources"].items():
               count = sum(r["slots"] for r in resources)
               description.append(f"Node {node['id']}: {count} {rtype}")
       return "\n".join(description)

Resource Management Best Practices
----------------------------------

**Discovery**:

- Query hardware accurately
- Handle discovery failures gracefully
- Cache discovery results

**Allocation**:

- Implement fair allocation strategies
- Prevent resource starvation
- Handle allocation conflicts

**Monitoring**:

- Track resource usage
- Detect resource leaks
- Monitor allocation patterns

Resource Extension Examples
---------------------------

**FPGA Resource Plugin**:

.. code-block:: python

   import canary

   @canary.hookimpl
   def canary_resource_pool_fill(config):
       # Detect FPGA devices
       fpgas = detect_fpga_devices()

       return {
           "nodes": [{
               "id": "fpga-host",
               "resources": {
                   "cpus": [{"id": "0", "slots": 8}],
                   "fpgas": [{"id": f"fpga{i}", "slots": 1} for i in range(len(fpgas))]
               }
           }]
       }

**Specialized Accelerator Plugin**:

.. code-block:: python

   import canary

   @canary.hookimpl
   def canary_resource_pool_fill(config):
       accelerators = discover_accelerators()

       pool = {
           "nodes": [{
               "id": "accel-node",
               "resources": {
                   "cpus": [{"id": "0", "slots": 16}],
                   "accelerators": []
               }
           }]
       }

       for accel in accelerators:
           pool["nodes"][0]["resources"]["accelerators"].append({
               "id": accel.id,
               "slots": accel.capacity,
               "type": accel.type
           })

       return pool

Resource Integration
--------------------

**Environment Variables**:

.. code-block:: python

   @canary.hookimpl
   def canary_runtest_setup(job):
       # Set environment variables for allocated resources
       if "fpgas" in job.resources:
           job.environment["FPGA_DEVICES"] = ",".join(job.resources["fpgas"])

**Resource Validation**:

.. code-block:: python

   @canary.hookimpl
   def canary_select_modifyitems(selector):
       for spec in selector.specs:
           if requires_special_resources(spec):
               if not resources_available(spec):
                   spec.mask = canary.Mask.masked("Required resources unavailable")

Resource Troubleshooting
------------------------

**Resource Detection Failures**:

- Verify hardware detection logic
- Check permissions for hardware access
- Test with simulated resources

**Allocation Issues**:

- Check resource pool configuration
- Verify accommodation logic
- Test with different resource requests

**Performance Problems**:

- Profile resource discovery
- Optimize allocation algorithms
- Monitor resource contention

See Also
--------

- :doc:`plugins`: Plugin registration
- :doc:`hooks`: Resource-related hooks
- :doc:`../user/resources`: Core resource management
- :doc:`/reference/commands.config`: Resource configuration