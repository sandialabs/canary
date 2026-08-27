.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-quickstart:

Quickstart: Run Your First Canary Test
=======================================

This quickstart guide will get you running a Canary test in under 5 minutes.

Prerequisites
-------------

1. Python 3.10+ installed
2. Canary installed (``pip install canary-wm``)
3. A terminal or command prompt

Step 1: Create a Simple Test
----------------------------

Create a file named ``hello.pyt`` with the following content:

.. code-block:: python
   :caption: hello.pyt

   import canary
   import canary_pyt

   # Add some keywords for filtering
   canary_pyt.directives.keywords("quickstart", "demo")

   def main():
       instance = canary.get_instance()
       print(f"Hello from {instance.name}!")
       print("This is a Canary test.")

   if __name__ == "__main__":
       main()

This test:
- Imports the Canary Python API
- Adds keywords for filtering
- Defines a simple test function
- Gets the test instance information

Step 2: Run the Test
--------------------

In your terminal, navigate to the directory containing ``hello.pyt`` and run:

.. code-block:: console

   python3 -m canary run hello.pyt

You should see output like:

.. code-block:: console

   [canary] Collecting tests...
   [canary] Found 1 test: hello
   [canary] Running tests...
   Hello from hello!
   This is a Canary test.
   [canary] Tests completed: 1 passed

Step 3: Check the Results
-------------------------

Canary creates a workspace (``.canary/``) and a results view (``TestResults/``):

.. code-block:: console

   # List the workspace contents
   ls -la .canary/

   # View test status
   python3 -m canary status -rA

   # See the test output
   cat TestResults/hello/canary-out.txt

Step 4: Run Multiple Tests
--------------------------

Create another test file ``goodbye.pyt``:

.. code-block:: python
   :caption: goodbye.pyt

   import canary_pyt

   canary_pyt.directives.keywords("quickstart")

   def main():
       print("Goodbye from Canary!")

   if __name__ == "__main__":
       main()

Now run both tests:

.. code-block:: console

   python3 -m canary run .

Step 5: Filter Tests by Keyword
-------------------------------

Use keywords to run specific tests:

.. code-block:: console

   # Run only quickstart tests
   python3 -m canary run . -k quickstart

   # Run only demo tests
   python3 -m canary run . -k demo

Congratulations! 🎉
--------------------

You've successfully:

1. ✅ Created Canary test files
2. ✅ Run tests with Canary
3. ✅ Inspected test results
4. ✅ Used keyword filtering

**Next Steps:**

- Learn about :doc:`test structure <basics/test-structure>`
- Explore :doc:`parameterized tests <intermediate/parameterization>`
- Try the :doc:`complete examples <examples/simple>`

.. tip::

   For more information on any command, use:

   .. code-block:: console

      python3 -m canary COMMAND --help

   Or query the capabilities:

   .. code-block:: console

      python3 -m canary learn capabilities core.overview