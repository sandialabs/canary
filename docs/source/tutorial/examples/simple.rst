.. Copyright NTESS. See COPYRIGHT file for details.

   SPDX-License-Identifier: MIT

.. _tutorial-example-simple:

Simple Test Example
===================

This example demonstrates a minimal but complete Canary test that you can use as
a template for your own tests.

Complete Example Code
---------------------

.. literalinclude:: tutorial_simple.pyt
   :language: python
   :caption: tutorial_simple.pyt

How to Use This Example
-----------------------

Let's run this example using doc-run to see the actual execution:

.. doc-run::
   :before_script: ['cp ${doc_source_dir}/tutorial_simple.pyt .', 'python3 -m canary init']
   :script: ['python3 -m canary run tutorial_simple.pyt']
   :display: command, stdout, stderr

The output shows the test being discovered, executed, and completed successfully.

Let's also check the results:

.. doc-run::
   :before_script: ['cp ${doc_source_dir}/tutorial_simple.pyt .', 'python3 -m canary run tutorial_simple.pyt']
   :script: ['python3 -m canary status -rA', 'cat TestResults/tutorial_simple/canary-out.txt']
   :display: command, stdout, stderr

Key Features Demonstrated
-------------------------

1. **Basic Structure**: Shows the fundamental test anatomy
2. **Directives**: Uses ``keywords()`` for test categorization
3. **Instance Access**: Demonstrates accessing test metadata
4. **Simple Validation**: Includes basic result checking
5. **Clean Output**: Shows proper test reporting

Customizing This Example
------------------------

To adapt this example for your needs:

1. **Change the test name**: Rename the file and update content
2. **Add keywords**: Modify the ``keywords()`` directive
3. **Update logic**: Replace the calculation with your test code
4. **Add validation**: Include appropriate result checking
5. **Add directives**: Include resource requirements, timeouts, etc.

Example Variations
------------------

**Data Processing Version**

.. literalinclude:: tutorial_data.pyt
   :language: python
   :caption: tutorial_data.pyt

Let's run this data processing example:

.. doc-run::
   :before_script:
       - cp ${doc_source_dir}/tutorial_data.pyt .
       - cp ${doc_source_dir}/input.txt .
   :script:
       - python3 -m canary run tutorial_data.pyt
   :display: command, stdout, stderr

**Parameterized Version**

.. literalinclude:: tutorial_param.pyt
   :language: python
   :caption: tutorial_param.pyt

Let's run this parameterized example:

.. doc-run::
   :before_script:
       - cp ${doc_source_dir}/tutorial_param.pyt .
   :script:
       - python3 -m canary run tutorial_param.pyt
   :display: command, stdout, stderr

.. tip::

    For more complete examples, see:

    - :doc:`parameterized`: Parameterized test patterns
    - :doc:`with-assets`: Asset and artifact management
    - :doc:`composite`: Composite analysis workflows

.. seealso::

   - :doc:`../quickstart`: Quickstart guide
   - :doc:`../basics/first-test`: First test tutorial
   - :doc:`parameterized`: Parameterized example
   - :doc:`/extensions/pyt/directives`: All available directives