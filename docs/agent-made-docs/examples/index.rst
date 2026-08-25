.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

Examples
========

This section provides practical Canary examples and common workflow patterns.

Bundled examples
----------------

Canary includes bundled examples that can be copied into a working directory:

.. code-block:: console

   python3 -m canary fetch examples

After fetching examples, inspect the copied tree and run a small subset:

.. code-block:: console

   python3 -m canary run ./basic
   python3 -m canary status -rA

For exact command syntax, see the command reference pages such as
:doc:`/reference/commands.run` and :doc:`/reference/commands.status`.

Example categories
------------------

Python job definitions
~~~~~~~~~~~~~~~~~~~~~~

Python job definitions are handled by the :doc:`../extensions/pyt/index`
extension. A minimal Python job definition places directives near the top of
the file and keeps execution logic under an entry point:

.. code-block:: python

   import canary
   import canary_pyt

   canary_pyt.directives.keywords("smoke")

   def main():
       instance = canary.get_instance()
       print(f"Running {instance.name}")

   if __name__ == "__main__":
       main()

Parameterized Python jobs
~~~~~~~~~~~~~~~~~~~~~~~~~

Parameterized jobs create multiple concrete Canary jobs from one job-definition
file:

.. code-block:: python

   import canary
   import canary_pyt

   canary_pyt.directives.parameterize("case", ["baseline", "variant1", "variant2"])

   def main():
       instance = canary.get_instance()
       case = instance.parameters.case
       print(f"Running case {case}")

   if __name__ == "__main__":
       main()

For detailed Python job-definition syntax, see
:doc:`../extensions/pyt/parameterization` and
:doc:`../extensions/pyt/directives`.

Assets and artifacts
~~~~~~~~~~~~~~~~~~~~

Input files needed by a job can be copied or linked into the execution
directory. Output files can be marked as reportable artifacts.

.. code-block:: python

   import canary_pyt

   canary_pyt.directives.copy("input.txt")
   canary_pyt.directives.link(src="mesh.dat", dst="mesh.dat")
   canary_pyt.directives.artifact("results.json", save_on="always")

For details, see :doc:`../extensions/pyt/assets` and
:doc:`../extensions/pyt/artifacts`.

Composite analysis
~~~~~~~~~~~~~~~~~~

A parameterized study can generate a composite analysis job that runs after the
parameterized child jobs finish.

.. code-block:: python

   import canary
   import canary_pyt

   canary_pyt.directives.parameterize("resolution", [10, 20, 40])
   canary_pyt.directives.aggregate(flag="--analyze")

   def main():
       instance = canary.get_instance()
       if instance.analyze:
           print("Analyze child results")
       else:
           print(f"Run resolution {instance.parameters.resolution}")

   if __name__ == "__main__":
       main()

For details, see :doc:`../extensions/pyt/composite-analysis`.

CTest and CMake projects
~~~~~~~~~~~~~~~~~~~~~~~~

Existing CMake/CTest projects can be run through the CMake extension. This is
the recommended entry point for projects that already define tests with CTest.

See :doc:`../extensions/cmake/index`.

VVTest compatibility
~~~~~~~~~~~~~~~~~~~~

Legacy VVTest-style ``.vvt`` files are handled by the VVTest compatibility
extension. This is useful for running existing VVTest suites under Canary while
using Canary workspaces, reporting, and execution backends.

See :doc:`../extensions/vvtest/index`.

HPC shell backend
~~~~~~~~~~~~~~~~~

The HPC extension can be demonstrated locally with the shell backend. This is a
static example; real scheduler backends are site-specific.

.. code-block:: console

   python3 -m canary hpc run --backend=shell --batch-spec=count=4 ./basic
   python3 -m canary status -rA

For details, see :doc:`../extensions/hpc/index`.

Reporting
~~~~~~~~~

Reports are generated from completed workspace results:

.. code-block:: console

   python3 -m canary report json -o canary.json
   python3 -m canary report junit -o junit.xml
   python3 -m canary report html -o HTML

For exact command syntax, see the report command reference:
:doc:`/reference/commands.report`.

Where to go next
----------------

- :doc:`../user/running` explains how to run jobs.
- :doc:`../user/selection` explains filtering and selection.
- :doc:`../user/results` explains result inspection.
- :doc:`../user/workflows` gives common workflow patterns.
- :doc:`../extensions/pyt/index` documents Python job definitions.
- :doc:`../extensions/cmake/index` documents CMake/CTest integration.
- :doc:`../extensions/vvtest/index` documents VVTest compatibility.
- :doc:`../extensions/hpc/index` documents HPC execution.
