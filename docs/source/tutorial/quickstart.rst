.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-quickstart:

Quickstart: Run Your First Canary Test
=======================================

.. note::
   
   This tutorial uses **real execution** - all examples are actually run during 
   documentation build using the ``doc-run`` directive. This ensures the examples 
   stay up-to-date and actually work!

This quickstart guide will get you running a Canary test in under 5 minutes.

Prerequisites
-------------

1. Python 3.10+ installed
2. Canary installed (``pip install canary-wm``)
3. A terminal or command prompt

Step 1: Create a Simple Test
----------------------------

Let's create a simple test file. Here's the content:

.. literalinclude:: hello.pyt
   :language: python
   :caption: hello.pyt

This test:
- Imports the Canary Python API
- Adds keywords for filtering
- Defines a simple test function
- Gets the test instance information

Step 2: Run the Test
--------------------

Let's run the test using Canary:

.. doc-run::
   :before_script: ['cp ${doc_source_dir}/hello.pyt .', 'python3 -m canary init']
   :script: ['python3 -m canary run hello.pyt']
   :display: command, stdout, stderr

Step 3: Check the Results
-------------------------

Canary creates a workspace (``.canary/``) and a results view (``TestResults/``). Let's explore what was created:

.. doc-run::
   :before_script: ['cp ${doc_source_dir}/hello.pyt .', 'python3 -m canary run hello.pyt']
   :script: ['ls -la .canary/', 'python3 -m canary status -rA', 'cat TestResults/hello/canary-out.txt']
   :display: command, stdout, stderr

Step 4: Run Multiple Tests
--------------------------

Let's create another test file:

.. literalinclude:: goodbye.pyt
   :language: python
   :caption: goodbye.pyt

Now run both tests:

.. doc-run::
   :before_script: ['cp ${doc_source_dir}/hello.pyt .', 'python3 -m canary init']
   :script: ['python3 -m canary run hello.pyt', 'python3 -m canary status -rA', 'cat TestResults/hello/canary-out.txt']
   :display: command, stdout, stderr

Step 5: Filter Tests by Keyword
--------------------------------

Use keywords to run specific tests:

.. doc-run::
   :before_script: ['cp ${doc_source_dir}/hello.pyt .', 'cp ${doc_source_dir}/goodbye.pyt .', 'python3 -m canary init']
   :script: ['python3 -m canary run -k quickstart .']
   :display: command, stdout, stderr

You can also run only the demo tests:

.. doc-run::
   :before_script: ['cp ${doc_source_dir}/hello.pyt .', 'cp ${doc_source_dir}/goodbye.pyt .', 'python3 -m canary init']
   :script: ['python3 -m canary run .']
   :display: command, stdout, stderr

Congratulations! 🎉
--------------------

You've successfully:

1. ✅ Created Canary test files
2. ✅ Run tests with Canary
3. ✅ Inspected test results
4. ✅ Used keyword filtering

**Next Steps:**

- Learn about :doc:`../user/index`
- Explore :doc:`../examples/index`
- Read the :doc:`../reference/index`

.. tip::

   For more information on any command, use:

   .. code-block:: console

      python3 -m canary COMMAND --help

   Or query the capabilities:

   .. code-block:: console

      python3 -m canary learn capabilities core.overview
