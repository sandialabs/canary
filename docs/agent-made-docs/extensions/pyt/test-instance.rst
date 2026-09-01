.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Test Instance
=============

Access test instance data at runtime using ``canary.get_instance()``. The test instance provides information about the current job execution.

Accessing the Instance
----------------------

.. code-block:: python

   import canary

   def main():
       instance = canary.get_instance()
       print(f"Test name: {instance.name}")

Attributes
----------

### Core Attributes

**file_root**:
   Root directory of the test file.

.. code-block:: python

   print(f"File root: {instance.file_root}")

**file_path**:
   Full path to the test file.

.. code-block:: python

   print(f"File path: {instance.file_path}")

**name**:
   Test name (with parameters if parameterized).

.. code-block:: python

   print(f"Test name: {instance.name}")

**file**:
   Base filename of the test.

.. code-block:: python

   print(f"File: {instance.file}")

### Resource Attributes

**cpu_ids**:
   List of CPU IDs allocated to the job.

.. code-block:: python

   print(f"CPU IDs: {instance.cpu_ids}")
   print(f"CPU count: {len(instance.cpu_ids)}")

**gpu_ids**:
   List of GPU IDs allocated to the job.

.. code-block:: python

   print(f"GPU IDs: {instance.gpu_ids}")
   print(f"GPU count: {len(instance.gpu_ids)}")

### Metadata Attributes

**family**:
   Test family or group.

.. code-block:: python

   print(f"Family: {instance.family}")

**keywords**:
   List of test keywords.

.. code-block:: python

   print(f"Keywords: {instance.keywords}")
   if "smoke" in instance.keywords:
       print("Smoke test")

**parameters**:
   Dictionary of parameter values.

.. code-block:: python

   print(f"Parameters: {instance.parameters}")
   size = instance.parameters.get("size", 10)

**timeout**:
   Timeout in seconds.

.. code-block:: python

   print(f"Timeout: {instance.timeout}s")

**runtime**:
   Runtime duration in seconds.

.. code-block:: python

   print(f"Runtime: {instance.runtime}s")

### Workspace Attributes

**work_tree**:
   Work tree directory.

.. code-block:: python

   print(f"Work tree: {instance.work_tree}")

**working_directory**:
   Current working directory.

.. code-block:: python

   print(f"Working directory: {instance.working_directory}")

### State Attributes

**state**:
   Current state of the job.

.. code-block:: python

   print(f"State: {instance.state}")

**status**:
   Current status of the job.

.. code-block:: python

   print(f"Status: {instance.status}")

**id**:
   Job ID.

.. code-block:: python

   print(f"ID: {instance.id}")

**returncode**:
   Return code of the job.

.. code-block:: python

   print(f"Return code: {instance.returncode}")

### Dependency Attributes

**dependencies**:
   List of job dependencies.

.. code-block:: python

   for dep in instance.dependencies:
       print(f"Dependency: {dep.name}, status: {dep.status}")

### Custom Attributes

**variables**:
   Custom variables.

.. code-block:: python

   print(f"Variables: {instance.variables}")

**attributes**:
   Custom attributes set via ``set_attribute``.

.. code-block:: python

   print(f"Attributes: {instance.attributes}")
   priority = instance.attributes.get("priority", "normal")

Methods
-------

### get_dependency

Get a specific dependency:

.. code-block:: python

   child = instance.get_dependency("test1")
   print(f"Child status: {child.status}")

### output

Get job output:

.. code-block:: python

   output = instance.output()
   print(f"Output: {output}")

### logfile

Get job log file:

.. code-block:: python

   logfile = instance.logfile()
   print(f"Log file: {logfile}")

### set_attribute

Set custom attributes:

.. code-block:: python

   instance.set_attribute(priority="high", category="performance")

TestMultiInstance
-----------------

Access multi-instance data:

.. code-block:: python

   from _canary.testinst import TestMultiInstance

   def main():
       instance = canary.get_instance()
       multi = TestMultiInstance(instance)

       # Access child instances
       for child in multi.children:
           print(f"Child: {child.name}")

Examples
--------

**Access Parameters**:

.. code-block:: python

   import canary
   import canary_pyt

   canary_pyt.directives.parameterize("size", [10, 20, 30])

   def main():
       instance = canary.get_instance()
       size = instance.parameters.size
       print(f"Running with size={size}")

**Access Resources**:

.. code-block:: python

   import canary
   import canary_pyt

   canary_pyt.directives.cpus(4)
   canary_pyt.directives.gpus(1)

   def main():
       instance = canary.get_instance()
       print(f"CPUs: {instance.cpu_ids}")
       print(f"GPUs: {instance.gpu_ids}")

**Access Dependencies**:

.. code-block:: python

   import canary
   import canary_pyt

   canary_pyt.directives.depends_on("setup_test")

   def main():
       instance = canary.get_instance()
       for dep in instance.dependencies:
           print(f"Depends on: {dep.name}")

**Composite Analysis**:

.. code-block:: python

   import canary
   import canary_pyt

   canary_pyt.directives.aggregate(
       "analyze",
       ["test1", "test2"]
   )

   def main():
       instance = canary.get_instance()

       # Access child results
       child1 = instance.get_dependency("test1")
       child2 = instance.get_dependency("test2")

       results = [child1.returncode, child2.returncode]
       print(f"Results: {results}")

Best Practices
--------------

1. **Access Parameters**:

   .. code-block:: python

      size = instance.parameters.get("size", 10)

2. **Check Keywords**:

   .. code-block:: python

      if "smoke" in instance.keywords:
          # Smoke test logic

3. **Access Resources**:

   .. code-block:: python

      cpus = len(instance.cpu_ids)
      gpus = len(instance.gpu_ids)

4. **Access Dependencies**:

   .. code-block:: python

      for dep in instance.dependencies:
          if dep.status != "PASSED":
              # Handle failed dependency

See Also
--------

- :doc:`directive-reference/set_attribute`: Set attribute directive
- :doc:`directive-reference/depends_on`: Dependencies directive
- :doc:`directive-reference/parameterize`: Parameterization directive
- :doc:`composite-analysis`: Composite analysis overview
